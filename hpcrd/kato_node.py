"""In-process stand-in for one KATO node, built on KATO's own classes.

Nothing here re-implements matching or scoring. A prediction is produced by the
same calls KATO's request path makes, in the same order:

    similarity   kato.searches.pattern_search._lcs_ratio_scorer   (token level, 2*LCS/(P+L))
    extraction   InformationExtractor.extract_prediction_info      (matching blocks, alignment)
    prediction   kato.representations.prediction.Prediction        (past/present/future/missing/extras)
    scores       kato.informatics.prediction_metrics.score_ensemble (potential, future_potentials, ends_here)
    ranking      kato.representations.prediction.rank_predictions
    names        kato.representations.pattern.Pattern              (sha1 of the pattern data)

What is mirrored by hand, from kato/informatics/knowledge_base.py and
kato/storage/redis_writer.py: frequency counting and the node counters, the
"fewer than two symbols is not learned" rule, the observe order (append,
predict, auto-learn), ROLLING/CLEAR, and the single-symbol candidate path. Also, from
kato/api/endpoints/sessions.py, retiring a pattern: a tombstone that every read path skips,
reversible. The retire mirror has not been checked against a running KATO.

Not mirrored: storage, sessions, emotives, metadata, vectors, retirement, and
the metrics that describe one prediction at a time (entropy, tf-idf, ...).

KATO_REPO must point at a checkout of https://github.com/sevakavakians/kato.
"""
import os
import sys
from collections import Counter
from itertools import chain

if not os.environ.get('KATO_REPO'):
    raise RuntimeError("Set KATO_REPO to a checkout of https://github.com/sevakavakians/kato")
sys.path.insert(0, os.environ['KATO_REPO'])

from kato.informatics.prediction_metrics import NodeStatistics, Observation, score_ensemble  # noqa: E402
from kato.representations.pattern import Pattern  # noqa: E402
from kato.representations.prediction import Prediction, rank_predictions, refine_alignment_by_events  # noqa: E402
from kato.searches.pattern_search import InformationExtractor, _lcs_ratio_scorer  # noqa: E402

PREFIX = 'PTRN|'


def bare(name):
    return name[len(PREFIX):] if name.startswith(PREFIX) else name


class InProcessNode:
    def __init__(self, name, recall_threshold=0.1, max_predictions=100,
                 max_pattern_length=0, stm_mode='CLEAR', rank_sort_algo='potential'):
        self.name = name
        self.recall_threshold = recall_threshold
        self.max_predictions = max_predictions
        self.max_pattern_length = max_pattern_length
        self.stm_mode = stm_mode
        self.rank_sort_algo = rank_sort_algo
        self.patterns = {}            # bare sha1 -> {'name','pattern_data','length','frequency','emotives'}
        self.retired = set()          # bare sha1 of tombstoned patterns: stored, and skipped by every read
        self.learn_order = []         # bare sha1, in order of first learn
        self.symbol_freq = Counter()  # symbols:freq
        self.symbol_pmf = Counter()   # symbols:pmf
        self.total_symbols = 0        # total_symbols_in_patterns_frequencies
        self.total_pattern_frequency = 0
        self.stm = []
        self.learns = 0
        self.predicts = 0
        self._extractor = InformationExtractor(use_fast_matcher=True, use_token_matching=True)

    # -- learning ---------------------------------------------------------
    def learn(self, events=None):
        """Learn `events` (default: the STM, which is then cleared). Returns 'PTRN|<sha1>' or None."""
        own_stm = events is None
        events = [list(e) for e in (self.stm if own_stm else events)]
        if own_stm:
            self.stm = []
        pattern = Pattern(events)
        if len(pattern) <= 1:
            return None
        self.learns += 1
        counts = Counter(chain(*pattern.pattern_data))
        new = pattern.name not in self.patterns
        if new:
            self.patterns[pattern.name] = {
                'name': pattern.name, 'pattern_data': pattern.pattern_data,
                'length': pattern.length, 'frequency': 1, 'emotives': {},
            }
            self.learn_order.append(pattern.name)
        else:
            self.patterns[pattern.name]['frequency'] += 1
        for symbol, count in counts.items():
            self.symbol_freq[symbol] += count
            if new:
                self.symbol_pmf[symbol] += 1
        self.total_symbols += pattern.length
        self.total_pattern_frequency += 1
        return PREFIX + pattern.name

    def frequency(self, name):
        entry = self.patterns.get(bare(name))
        return entry['frequency'] if entry and bare(name) not in self.retired else 0

    def retire(self, names):
        """KATO: POST /sessions/{id}/patterns/retire. The patterns stay stored; reads skip them."""
        self.retired.update(bare(n) for n in names if bare(n) in self.patterns)

    def unretire(self, names):
        """KATO: POST /sessions/{id}/patterns/un-retire."""
        self.retired.difference_update(bare(n) for n in names)

    def pattern(self, name):
        return self.patterns[bare(name)]['pattern_data']

    # -- observing --------------------------------------------------------
    def observe(self, symbols, predict=True):
        """One event. Order as in ObservationProcessor.process_observation:
        append, predict, then auto-learn when the STM has reached max_pattern_length."""
        self.stm.append(sorted(symbols))
        result = self.predict() if predict else {'predictions': [], 'future_potentials': [], 'ends_here': None}
        result['stm'] = [list(e) for e in self.stm]
        result['auto_learned_pattern'] = None
        if self.max_pattern_length > 0 and len(self.stm) >= self.max_pattern_length:
            result['auto_learned_pattern'] = self.learn(self.stm)
            if self.stm_mode == 'ROLLING' and len(self.stm) > 1:
                keep = self.max_pattern_length - 1
                self.stm = self.stm[-keep:] if len(self.stm) > keep else self.stm[1:]
            else:
                self.stm = []
        return result

    def clear_stm(self):
        self.stm = []

    # -- predicting -------------------------------------------------------
    def predict(self, stm_events=None):
        self.predicts += 1
        stm_events = [list(e) for e in (self.stm if stm_events is None else stm_events)]
        state = list(chain(*stm_events))
        empty = {'predictions': [], 'future_potentials': [], 'ends_here': None, 'chance_posterior': 1.0}
        if not state:
            return empty
        built = []
        if len(state) == 1:   # single-symbol path: every pattern holding the symbol, no threshold
            for name in sorted(self.patterns):
                if name in self.retired:
                    continue
                entry = self.patterns[name]
                flat = list(chain(*entry['pattern_data']))
                if state[0] not in flat:
                    continue
                info = self._extractor.extract_prediction_info(flat, state, cutoff=0.0, fuzzy_token_threshold=0.0)
                if info:
                    built.append((entry, info))
        else:
            cutoff = self.recall_threshold * 100 - 1e-6
            for name in sorted(self.patterns):
                if name in self.retired:
                    continue
                entry = self.patterns[name]
                flat = list(chain(*entry['pattern_data']))
                score = _lcs_ratio_scorer(state, flat)
                if score < cutoff:
                    continue
                similarity = score / 100.0
                if similarity < self.recall_threshold:
                    continue
                info = self._extractor.extract_prediction_info(
                    flat, state, self.recall_threshold, 0.0, precomputed_similarity=similarity)
                if info:
                    built.append((entry, info))
        predictions = []
        for entry, info in built:
            (_p, matching, past, present, missing, extras, similarity, blocks, anomalies, weighted, alignment) = info[:11]
            prediction = Prediction(dict(entry), matching, past, present, missing, extras, similarity, blocks,
                                    fuzzy_matches=anomalies, stm_events=stm_events,
                                    weighted_similarity=weighted, alignment=alignment)
            prediction['frequency'] = entry['frequency']
            # Kept for checks only. KATO computes this alignment and does not return it.
            prediction['_alignment'] = tuple(
                list(x) for x in refine_alignment_by_events(entry['pattern_data'], stm_events, *alignment)
            ) if alignment is not None else None
            predictions.append(prediction)
        if not predictions:
            return empty
        table = {s: {'frequency': self.symbol_freq[s], 'pattern_member_frequency': self.symbol_pmf[s]}
                 for s in self.symbol_freq}
        node = NodeStatistics(table, self.total_symbols, self.total_pattern_frequency, len(self.patterns))
        scores = score_ensemble(predictions, Observation(stm_events, node), node)
        ranked = rank_predictions(predictions, self.rank_sort_algo, self.max_predictions)
        for prediction in ranked:
            prediction.pop('pattern_data', None)
        return {'predictions': ranked, 'future_potentials': scores.future_potentials,
                'ends_here': scores.ends_here, 'chance_posterior': scores.chance_posterior}


# KATO_API=http://host:port puts every node in a running KATO service instead (kato_api_node.py).
if os.environ.get('KATO_API'):
    from .kato_api_node import ApiNode as Node  # noqa: E402,F401
else:
    Node = InProcessNode
