"""One KATO node, reached through KATO's REST API. Same interface as kato_node.Node.

Set KATO_API (for example http://127.0.0.1:8000) and every node of the module
lives in a running KATO service: learning, predicting, frequencies and pattern
reads all go through the API. Used to check that the in-process stand-in and
the service say the same thing.

Calls used:
    POST /sessions                                  one session per job, all on the node's node_id
    POST /sessions/{id}/observe                     the stream (ROLLING auto-learn)
    GET  /sessions/{id}/cognition-data              the predictions computed during that observe,
                                                    for the full window, before it was learned
    POST /sessions/{id}/observe-sequence            an explicit learn (learn_at_end), or a sequence to ask about
    GET  /sessions/{id}/predictions                 predictions, future_potentials, ends_here
    POST /sessions/{id}/clear-stm, /clear-all
    GET  /pattern/{name}?node_id=...                a pattern's data and frequency
    POST /sessions/{id}/patterns/retire             a tombstone: the pattern stays stored, predictions skip it
    POST /sessions/{id}/patterns/un-retire          and back
    POST /sessions/{id}/learn                       only to ask why a learn was not confirmed (409: retired)

What KATO at f32bac0 does with a retired pattern, as seen on a running service (24 Nov 2026):
predictions skip it; GET /pattern/{name} still returns it, frequency included; learning it again is
refused (409 RETIRED_PATTERN from /learn; from observe-sequence with learn_at_end a 200 with no
final_learned_pattern, the sequence left in the session's STM) until it is un-retired; an id the node
does not hold is tombstoned all the same; a malformed id is a 422.
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request

PREFIX = 'PTRN|'
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def bare(name):
    return name[len(PREFIX):] if name.startswith(PREFIX) else name


class RetiredPattern(Exception):
    """KATO refuses to learn a pattern whose hash is retired on the node (RetiredPatternError,
    HTTP 409). Un-retire it first if it should exist again."""


class ApiNode:
    made = 0
    calls = 0

    def __init__(self, name, recall_threshold=0.1, max_predictions=100,
                 max_pattern_length=0, stm_mode='CLEAR', rank_sort_algo='potential'):
        ApiNode.made += 1
        self.base = os.environ['KATO_API'].rstrip('/')
        self.name = name
        self.node_id = f"rules_{os.environ.get('KATO_API_TAG', 'run')}_{ApiNode.made}_{name}"
        self.recall_threshold = recall_threshold
        self.max_predictions = max_predictions
        self.max_pattern_length = max_pattern_length
        self.stm_mode = stm_mode
        self.rank_sort_algo = rank_sort_algo
        shared = {'recall_threshold': recall_threshold, 'max_predictions': max_predictions,
                  'rank_sort_algo': rank_sort_algo}
        self.stream = self._session({**shared, 'max_pattern_length': max_pattern_length, 'stm_mode': stm_mode})
        self.learner = self._session({**shared, 'max_pattern_length': 0, 'process_predictions': False})
        self.asker = self._session({**shared, 'max_pattern_length': 0, 'process_predictions': False})
        self._call('POST', f"/sessions/{self.stream}/clear-all")
        self.learn_order = []
        self.retired = set()          # bare sha1 of the patterns this client retired on the node
        self.stm = []
        self.learns = 0
        self.predicts = 0
        self._cache = None

    # -- HTTP -------------------------------------------------------------
    def _call(self, method, path, body=None, missing_ok=False):
        ApiNode.calls += 1
        data = json.dumps(body).encode() if body is not None else (b'' if method == 'POST' else None)
        request = urllib.request.Request(self.base + path, data=data, method=method,
                                         headers={'Content-Type': 'application/json'})
        try:
            with _opener.open(request, timeout=120) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as error:
            if missing_ok and error.code == 404:
                return None
            text = error.read()[:400]
            if error.code == 409 and b'RETIRED_PATTERN' in text:
                raise RetiredPattern(text.decode(errors='replace')) from error
            raise RuntimeError(f"{method} {path}: {error.code} {text!r}") from error

    def _session(self, config):
        return self._call('POST', '/sessions', {'node_id': self.node_id, 'config': config})['session_id']

    def _register(self, name):
        if name and bare(name) not in self.learn_order:
            self.learn_order.append(bare(name))
        self._cache = None

    # -- the interface of kato_node.Node ------------------------------------
    def learn(self, events=None):
        events = [list(e) for e in (self.stm if events is None else events)]
        if sum(len(e) for e in events) <= 1:
            return None
        out = self._call('POST', f"/sessions/{self.learner}/observe-sequence",
                         {'observations': [{'strings': e} for e in events], 'learn_at_end': True})
        name = out['final_learned_pattern']
        if not name:
            # A learn that fails at the end of observe-sequence is a 200 with no name, and the session
            # keeps the sequence in its STM. The explicit learn says why: 409 for a retired pattern.
            try:
                self._call('POST', f"/sessions/{self.learner}/learn")
            finally:
                self._call('POST', f"/sessions/{self.learner}/clear-stm")
            raise RuntimeError(f"KATO did not confirm the learn of {events!r}")
        self.learns += 1
        self._register(name)
        return name

    def _read(self, name):
        quoted = urllib.parse.quote(PREFIX + bare(name), safe='')
        out = self._call('GET', f"/pattern/{quoted}?node_id={self.node_id}", missing_ok=True)
        # Found: {"pattern": {"status": "okay", "pattern": {...}}}. Not learned: status "error", HTTP 200.
        inner = out.get('pattern') if out else None
        if not inner or inner.get('status') != 'okay':
            return None
        return inner['pattern']

    def frequency(self, name):
        pattern = self._read(name)
        return pattern['frequency'] if pattern else 0

    def pattern(self, name):
        return self._read(name)['pattern_data']

    def retire(self, names):
        """POST /sessions/{id}/patterns/retire. Node-scoped and durable; the rows stay."""
        ids = [bare(n) for n in names]
        out = self._call('POST', f"/sessions/{self.learner}/patterns/retire", {'pattern_ids': ids})
        if sorted(out['retired'] + out['already_retired']) != sorted(set(ids)):
            raise RuntimeError(f"KATO retired {out['retired']} of {ids}")
        self.retired.update(ids)
        self._cache = None

    def unretire(self, names):
        """POST /sessions/{id}/patterns/un-retire."""
        ids = [bare(n) for n in names]
        self._call('POST', f"/sessions/{self.learner}/patterns/un-retire", {'pattern_ids': ids})
        self.retired.difference_update(ids)
        self._cache = None

    @property
    def patterns(self):
        """Every pattern this client taught the node, read back from KATO, the retired ones too."""
        if self._cache is None:
            self._cache = {}
            for name in self.learn_order:
                pattern = self._read(name)
                self._cache[name] = {'name': name, 'pattern_data': pattern['pattern_data'],
                                     'length': pattern.get('length'), 'frequency': pattern['frequency']}
        return self._cache

    def observe(self, symbols, predict=True):
        self.stm.append(sorted(symbols))
        out = self._call('POST', f"/sessions/{self.stream}/observe", {'strings': list(symbols)})
        result = {'predictions': [], 'future_potentials': [], 'ends_here': None}
        if predict:
            self.predicts += 1
            result['predictions'] = self._call('GET', f"/sessions/{self.stream}/cognition-data")['cognition_data']['predictions']
        result['stm'] = [list(e) for e in self.stm]
        result['auto_learned_pattern'] = out.get('auto_learned_pattern')
        if self.max_pattern_length > 0 and len(self.stm) >= self.max_pattern_length:
            if result['auto_learned_pattern']:
                self.learns += 1
                self._register(result['auto_learned_pattern'])
            if self.stm_mode == 'ROLLING' and len(self.stm) > 1:
                keep = self.max_pattern_length - 1
                self.stm = self.stm[-keep:] if len(self.stm) > keep else self.stm[1:]
            else:
                self.stm = []
        if out.get('stm_length') != len(self.stm):
            raise RuntimeError(f"STM mirror out of step: KATO holds {out.get('stm_length')} events, mirror {len(self.stm)}")
        return result

    def clear_stm(self):
        self.stm = []
        self._call('POST', f"/sessions/{self.stream}/clear-stm")

    def predict(self, stm_events=None):
        self.predicts += 1
        events = [list(e) for e in (self.stm if stm_events is None else stm_events)]
        empty = {'predictions': [], 'future_potentials': [], 'ends_here': None, 'chance_posterior': 1.0}
        if not any(events):
            return empty
        self._call('POST', f"/sessions/{self.asker}/clear-stm")
        self._call('POST', f"/sessions/{self.asker}/observe-sequence", {'observations': [{'strings': e} for e in events]})
        out = self._call('GET', f"/sessions/{self.asker}/predictions")
        self._call('POST', f"/sessions/{self.asker}/clear-stm")
        return {'predictions': out['predictions'], 'future_potentials': out['future_potentials'],
                'ends_here': out.get('ends_here'), 'chance_posterior': out.get('chance_posterior')}
