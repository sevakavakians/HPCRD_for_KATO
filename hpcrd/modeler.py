"""The module between node_0 and nodes 1a, 1b, 2a, 2b.

    node_0   sequences of symbols: rolling windows (KATO: stm_mode=ROLLING,
       |     max_pattern_length=window), or whole sequences as the application cuts them
       | prediction ensemble
    module   reads each prediction's matches / missing / extras (alignment.read)
       |-> node_1a   contiguous matches                    -> PTRN|<chunk>
       |-> node_1b   [chunk names, single tokens, VAR|n]   -> PTRN|<rule>
       |       '-> node_2a   names of node_1b patterns, in order
       '-> node_2b   VAR|n with its values, joint values, runs of VARs, what a VAR is made of

Every choice the description leaves open is a named setting (Settings), so the
experiments can run the alternatives side by side. Nothing is random, no clock
is read, and every loop over a set or dict runs in sorted order.

With rolling windows the module keeps one record of its own: at which step
node_0 learned each window (`learned_at`). KATO returns a pattern's name and
frequency with a prediction, not where it was learned, and the module needs
that to hold out echoes and to count evidence in earlier places of the stream.
With whole sequences it keeps none: nothing echoes, and a pattern's frequency
is the number of earlier places it stands for.
"""
from collections import Counter
from dataclasses import dataclass
from fractions import Fraction

from .alignment import flat, read
from .kato_node import PREFIX, Node, bare, Pattern
from .templates import TemplateReader

VAR = 'VAR|'


@dataclass(frozen=True)
class Settings:
    window: int = 7              # node_0's rolling window (span 'window' and 'stream')
    recall_threshold: float = 0.1  # node_0: how unlike a learned pattern may be and still be read
    span: str = 'window'         # 'window': one rule per ensemble | 'stream': stitched along the stream
                                 # | 'sequence': node_0 learns whole sequences, one rule per sequence
    markers: tuple = ()          # tokens that close a stretch ('stream') or a sequence ('sequence')
    naming: str = 'rule'         # what gives a slot its VAR id: 'rule' | 'neighbours' | 'values'
    slots: str = 'position'      # 'position': one VAR per aligned position | 'gap': one VAR per gap
    edge_vars: bool = False      # read an extra that lines up with `past`/`future` as a variable too
    mixed: str = 'var'           # a position some patterns match and others substitute: 'var' | 'const'
    min_support: int = 1         # earlier places a substitution must be seen in before it makes a variable
    unexplained: str = 'drop'    # a token no learned pattern accounts for: 'drop' it as noise | 'break' the stretch there
    rejoin: bool = True          # constants left side by side once noise is dropped are joined when node_1a holds the joined chunk
    node2a_window: int = 2       # node_2a's own rolling window over rule names
    values: str = 'name'         # a value of two or more tokens in node_2b: 'name' (a node_1a chunk, by name)
                                 # | 'sequence' (its tokens, so that KATO can match inside it)
    fold: str = 'all'            # the readings that decide constant / variable: 'all' that were read
                                 # | 'nearest' (the most similar ones that differ, and exact repeats)
    inside: bool = False         # values='sequence': read each new value against its VAR's earlier values
    loop: str = 'ensemble'       # span='sequence': 'ensemble' reads node_0's ensemble (rounds 1 and 2)
                                 # | 'templates' is Spell's loop (Du and Li 2016): a sequence joins the template it
                                 #   shares most with, and that template is edited. `fold` and `topdown` are not used.
    tau: float = 0.5             # loop='templates': the share of a sequence a template must share with it
    topdown: bool = False        # span='sequence': a learned rule that fits a new sequence reads it, before node_0 is asked
    rule_threshold: float = 0.5  # topdown: how much of a sequence a rule's constants must account for (node_1t's recall_threshold)


def pattern_name(events):
    return PREFIX + Pattern([list(e) for e in events]).name


def shape(symbols):
    """A rule with its VARs blanked: the constants, and where the slots are."""
    return tuple(None if x.startswith(VAR) else x for x in symbols)


class Evidence:
    """What the ensemble says about each position of a stretch of tokens.

    Evidence is counted in earlier places of the stream. A learned window that
    lines up with the stretch stands for one earlier place per time it was
    learned; the six windows that overlap one earlier sentence are six patterns
    and still one place per token.
    """

    def __init__(self, tokens):
        self.tokens = list(tokens)
        n = len(self.tokens)
        self.match = [set() for _ in range(n)]      # earlier positions holding the same token, aligned
        self.alts = [dict() for _ in range(n)]      # other symbol -> earlier positions holding it, aligned
        self.unequal = [set() for _ in range(n)]    # earlier positions of the match before an unequal gap
        self.inserted = [set() for _ in range(n)]   # earlier positions of the match before an insertion
        self.blocks = {}                            # (lo, hi) -> earlier positions of the token at lo
        self.readings = []                          # (offset, Reading, places)

    def add(self, reading, places, offset=0, edge_vars=False, decides=True):
        """`places`: the stream position of the pattern's first token, once per earlier learn.
        `decides`: this reading takes part in labelling positions constant or variable. One that
        does not still says where tokens stood together (blocks) and what else filled a gap."""
        n = len(self.tokens)
        if decides:
            for i, rel in enumerate(reading.relation):
                p = i + offset
                if not 0 <= p < n:
                    continue
                kind = rel[0]
                if kind == 'M':
                    self.match[p].update(base + rel[1] for base in places)
                elif kind == 'S' or (kind == 'E' and edge_vars):
                    self.alts[p].setdefault(rel[2], set()).update(base + rel[1] for base in places)
                elif kind == 'U':
                    self.unequal[p].update(base + rel[3] for base in places)
                elif kind == 'I':
                    self.inserted[p].update(base + rel[1] for base in places)
        for (q, i, length) in reading.blocks:
            lo, hi = max(i + offset, 0), min(i + offset + length, n)
            if hi > lo:
                shift = lo - (i + offset)
                self.blocks.setdefault((lo, hi), set()).update(base + q + shift for base in places)
        self.readings.append((offset, reading, list(places)))

    def alternatives(self, p):
        return Counter({symbol: len(where) for symbol, where in self.alts[p].items()})

    def labels(self, s):
        out = []
        for p in range(len(self.tokens)):
            elsewhere = set()
            for where in self.alts[p].values():
                elsewhere |= where
            varies = len(elsewhere) >= s.min_support
            if s.slots == 'gap':
                varies = varies or len(self.unequal[p]) >= s.min_support
            matched = bool(self.match[p])
            if varies and (s.mixed == 'var' or not matched):
                out.append('V')
            elif matched:
                out.append('C')
            else:
                out.append('N')
        return out

    def noise(self, p):
        """Why a position that is neither constant nor variable was dropped."""
        if self.inserted[p]:
            return 'inserted'       # a learned pattern has its two neighbours side by side
        if self.unequal[p]:
            return 'unequal'        # stands against a different number of symbols in a learned pattern
        if any(self.alts[p].values()):
            return 'too few'        # a substitution seen in fewer places than min_support
        return 'unexplained'        # no learned pattern lines up with it

    # -- constants: where one chunk ends and the next begins -----------------
    def covered(self, lo, hi):
        """In how many earlier places tokens lo..hi-1 stood together inside one contiguous match."""
        where = set()
        for (b_lo, b_hi), starts in self.blocks.items():
            if b_lo <= lo and b_hi >= hi:
                where.update(e + (lo - b_lo) for e in starts)
        return len(where)

    def chunk_support(self, lo, hi, window):
        k = hi - lo if window is None else min(hi - lo, window)
        return min(self.covered(x, x + k) for x in range(lo, hi - k + 1))

    def split_constants(self, lo, hi, window):
        """Cut a run of constants into chunks. A chunk is a stretch that was seen whole before:
        one contiguous match covers it (with rolling windows, for a stretch longer than the window,
        one contiguous match covers every window-length piece of it; `window` None means node_0
        holds whole sequences and there is no such limit). The longest such stretch is taken first,
        then the one seen in more places, then the leftmost; what is left on either side is cut
        the same way."""
        if hi <= lo:
            return []
        best = None
        for a in range(lo, hi):
            for b in range(hi, a, -1):
                support = self.chunk_support(a, b, window)
                if support > 0:
                    key = (b - a, support, -a)
                    if best is None or key > best[0]:
                        best = (key, a, b, support)
                    break   # the longest stretch starting at a
        if best is None:    # cannot happen for a run of matched positions
            return [(p, p + 1, 0) for p in range(lo, hi)]
        _key, a, b, support = best
        return self.split_constants(lo, a, window) + [(a, b, support)] + self.split_constants(b, hi, window)

    # -- variables: what else has stood in a slot ----------------------------
    def gap_alternatives(self, lo, hi):
        """Fillers that learned patterns hold where tokens lo..hi-1 stand, read gap to gap:
        a pattern that matches the token before and the token after gives what it has between.
        When both are whole sequences, the start and the end are anchors as well."""
        where = {}
        for offset, r, places in self.readings:
            i_l, i_r = lo - 1 - offset, hi - offset
            if i_l == -1 and r.whole:
                q_l = -1
            elif 0 <= i_l < len(r.relation) and r.relation[i_l][0] == 'M':
                q_l = r.relation[i_l][1]
            else:
                continue
            if i_r == len(r.relation) and r.whole:
                q_r = len(r.pattern)
            elif 0 <= i_r < len(r.relation) and r.relation[i_r][0] == 'M':
                q_r = r.relation[i_r][1]
            else:
                continue
            filler = tuple(r.pattern[q_l + 1:q_r])
            if not filler or list(filler) == self.tokens[lo:hi]:
                continue
            where.setdefault(filler, set()).update(base + q_l for base in places)
        return Counter({filler: len(w) for filler, w in where.items()})

    def rows(self, positions, edge_vars=False):
        """What one learned pattern holds at all of `positions` at once (position-level slots)."""
        out = set()
        for offset, r, _places in self.readings:
            row = []
            for p in positions:
                i = p - offset
                rel = r.relation[i] if 0 <= i < len(r.relation) else ('O',)
                if rel[0] == 'M' or rel[0] == 'S' or (rel[0] == 'E' and edge_vars):
                    row.append(r.pattern[rel[1]])
                else:
                    break
            else:
                out.add(tuple(row))
        return sorted(out)


def whole_places(readings):
    """Whole sequences: a pattern learned f times stands for f earlier places. Each gets a range of
    positions of its own (one before the first token and one after the last included, for the two
    ends), so that evidence can be counted in distinct earlier places."""
    out, base = [], 0
    for r in readings:
        step = len(r.pattern) + 2
        out.append((r, [base + 1 + k * step for k in range(r.frequency)]))
        base += r.frequency * step
    return out


class Modeler:
    def __init__(self, settings=Settings(), trace=True):
        self.s = s = settings
        whole = s.span == 'sequence'
        self.node0 = Node('node_0', recall_threshold=s.recall_threshold, max_predictions=10000,
                          max_pattern_length=0 if whole else s.window,
                          stm_mode='CLEAR' if whole else 'ROLLING')
        self.node1a = Node('node_1a')
        self.node1b = Node('node_1b', max_predictions=10000)
        self.node2a = Node('node_2a', max_pattern_length=s.node2a_window, stm_mode='ROLLING')
        self.node2b = Node('node_2b', max_predictions=10000)
        # topdown: every rule again with its chunks spelled out, so that KATO can line a raw sequence
        # up with it. `rule_of` links that pattern to the node_1b rule; it holds nothing KATO does not
        # (the pattern is the rule with its names unravelled through node_1a).
        self.node1t = Node('node_1t', recall_threshold=s.rule_threshold, max_predictions=10000) if s.topdown else None
        self.rule_of = {}
        self.reader = None
        if s.loop == 'templates':
            if not (whole and s.slots == 'gap' and s.values == 'sequence'):
                raise ValueError("loop='templates' needs span='sequence', slots='gap' and values='sequence'")
            self.reader = TemplateReader(tau=s.tau, parameter=VAR, number=self.next_var)
        self.reach = None if whole else s.window    # the longest stretch one node_0 pattern can show whole
        self.learned_at = {}        # rolling windows: node_0 pattern name -> steps at which it was learned
        self.var_count = 0
        self.frames = {}            # naming='neighbours': (left token, right token, k, run length) -> VAR id
        self.t = -1
        self.tokens = []            # the stream so far
        self.windows = []           # span='stream': (start position, held-out readings, which decide) per step
        self.closed = 0             # span='stream' / 'sequence': first stream position not yet modelled
        self.cuts = set()           # stream positions where the application ended a stretch or sequence (cut())
        self.keep_trace = trace
        self.trace = []

    # -- stream in ----------------------------------------------------------
    def decides(self, readings, n):
        """fold='nearest': only the learned patterns most like the observed tokens decide what is
        constant and what varies, and exact repeats with them. Likeness is KATO's similarity for
        one symbol per event, 2 * matches / (pattern length + observed length), kept as an exact
        fraction so that ties are ties."""
        if self.s.fold == 'all':
            return [True] * len(readings)
        like = [Fraction(2 * len(r.pairs), len(r.pattern) + n) for r, _places in readings]
        best = max((x for x in like if x < 1), default=None)
        return [x == 1 or x == best for x in like]

    def feed(self, token):
        self.t += 1
        self.tokens.append(token)
        if self.s.span == 'sequence':
            if token in self.s.markers:
                step = self.read_sequence(self.closed, len(self.tokens))
            else:
                step = {'t': self.t, 'stm': [], 'readings': [], 'echoes': 0, 'ensemble': 0,
                        'learned': None, 'raw': [], 'stretches': []}
            if self.keep_trace:
                self.trace.append(step)
            return step
        out = self.node0.observe([token])
        stm = flat(out['stm'])
        # A window learned at step u covers the stream positions that end at u. It shares no token
        # with the window in the STM when u <= t - window. Later ones are echoes: the same tokens,
        # shifted.
        cutoff = self.t - self.s.window
        readings, echoes = [], 0
        for p in out['predictions']:
            steps = [u for u in self.learned_at.get(p['name'], ()) if u <= cutoff]
            if not steps:
                echoes += 1
                continue
            r = read(p, out['stm'])._replace(frequency=len(steps))
            readings.append((r, [u - len(r.pattern) + 1 for u in steps]))
        readings.sort(key=lambda pair: pair[0].name)
        decides = self.decides(readings, len(stm))
        step = {'t': self.t, 'stm': stm, 'readings': readings, 'echoes': echoes,
                'ensemble': len(out['predictions']), 'learned': out['auto_learned_pattern'],
                'raw': out['predictions']}
        if self.s.span == 'window':
            ev = Evidence(stm)
            for (r, places), d in zip(readings, decides):
                ev.add(r, places, 0, self.s.edge_vars, d)
            step.update(self.emit(ev))
            step['evidence'] = ev
        else:
            self.windows.append((self.t - len(stm) + 1, readings, decides))
            step['stretches'] = self.close_stretches(final=False)
        if out['auto_learned_pattern']:
            self.learned_at.setdefault(bare(out['auto_learned_pattern']), []).append(self.t)
        if self.keep_trace:
            self.trace.append(step)
        return step

    def cut(self):
        """The application ends the sequence here (a line, a turn, a sentence), without a marker
        token. span='sequence': the open sequence is read and learned. span='stream': the open
        stretch ends here; node_0's window still rolls across the cut. span='window': nothing."""
        if self.s.span == 'sequence':
            if self.closed >= len(self.tokens):
                return None
            step = self.read_sequence(self.closed, len(self.tokens))
            if self.keep_trace:
                self.trace.append(step)
            return step
        self.cuts.add(len(self.tokens))
        return None

    def read_sequence(self, a, b):
        """span='sequence': predict on the whole sequence, model it, then let node_0 learn it.
        The sequence is not in node_0 when it is read, so nothing has to be held out, and the
        learned patterns are whole sequences too, so their ends line up with its ends."""
        tokens = self.tokens[a:b]
        events = [[x] for x in tokens]
        step = {'t': b - 1, 'stm': tokens, 'readings': [], 'echoes': 0, 'ensemble': 0,
                'learned': None, 'raw': [], 'stretches': []}
        self.closed = b
        if len(tokens) < 2:     # one symbol is not a pattern
            return step
        if self.reader is not None:
            result = self.read_by_templates(tokens)
            result['stretch'] = (a, b)
            step.update(stretches=[result], by_template=result['template'], learned=self.node0.learn(events))
            return step
        if self.s.topdown:
            result = self.read_by_rule(tokens)
            if result is not None:
                result['stretch'] = (a, b)
                step.update(stretches=[result], by_rule=result['by_rule'], learned=self.node0.learn(events))
                return step
        out = self.node0.predict(events)
        readings = whole_places(read(p, events, whole=True)
                                for p in sorted(out['predictions'], key=lambda p: p['name']))
        decides = self.decides(readings, len(tokens))
        ev = Evidence(tokens)
        for (r, places), d in zip(readings, decides):
            ev.add(r, places, 0, False, d)
        result = self.emit(ev)
        result['stretch'] = (a, b)
        result['evidence'] = ev
        step.update(readings=readings, ensemble=len(out['predictions']), raw=out['predictions'],
                    stretches=[result], decides=decides, learned=self.node0.learn(events))
        return step

    def finish(self):
        """Model what is still open at the end of the stream."""
        if self.s.span == 'stream':
            out = self.close_stretches(final=True)
            if self.keep_trace:
                self.trace.append({'t': self.t, 'stm': [], 'readings': [], 'echoes': 0, 'ensemble': 0,
                                   'learned': None, 'raw': [], 'stretches': out, 'final': True})
            return out
        if self.s.span == 'sequence' and self.closed < len(self.tokens):
            step = self.read_sequence(self.closed, len(self.tokens))
            if self.keep_trace:
                self.trace.append(step)
            return step['stretches']
        return []

    def close_stretches(self, final):
        """A stretch ends at a marker token. It is modelled once the window has moved past its last
        token, so that every window that saw any of its tokens has been read (window-1 tokens later)."""
        out = []
        while True:
            end = None
            for n in range(self.closed, len(self.tokens)):
                if self.tokens[n] in self.s.markers or (n + 1) in self.cuts:
                    end = n + 1
                    break
            if end is None:
                if not final or self.closed >= len(self.tokens):
                    break
                end = len(self.tokens)
            elif not final and self.t < end - 1 + self.s.window - 1:
                break
            a, b = self.closed, end
            ev = Evidence(self.tokens[a:b])
            for start, readings, decides in self.windows:
                if start + self.s.window <= a or start >= b:
                    continue
                for (r, places), d in zip(readings, decides):
                    ev.add(r, places, start - a, self.s.edge_vars, d)
            result = self.emit(ev)
            result['stretch'] = (a, b)
            result['evidence'] = ev
            out.append(result)
            self.closed = b
        if out:     # windows that end before the open stretch begins are not read again
            self.windows = [w for w in self.windows if w[0] + self.s.window > self.closed]
        return out

    # -- one stretch of tokens -> chunks, rule, values ----------------------
    def chunk(self, tokens, learn=True):
        """A single token stands for itself. Two or more are learned in node_1a and stand by name."""
        tokens = list(tokens)
        if len(tokens) == 1:
            return tokens[0]
        events = [[t] for t in tokens]
        name = pattern_name(events)
        if learn or self.node1a.frequency(name) == 0:
            self.node1a.learn(events)
        return name

    def rejoin(self, items):
        """Dropping noise can leave two constants side by side that were one chunk before the noise
        came between them. They are joined when node_1a already holds the joined chunk, which is one
        lookup by name: a pattern's name is the hash of its content."""
        out = []
        for item in items:
            prev = out[-1] if out else None
            if (prev and prev['kind'] == 'C' and item['kind'] == 'C' and prev['hi'] < item['lo']
                    and self.node1a.frequency(pattern_name([[t] for t in prev['tokens'] + item['tokens']])) > 0):
                out[-1] = {'kind': 'C', 'lo': prev['lo'], 'hi': item['hi'],
                           'tokens': prev['tokens'] + item['tokens'],
                           'support': min(prev['support'], item['support']), 'rejoined': True}
            else:
                out.append(item)
        return out

    def emit(self, ev):
        """Label every position, then model each part of the stretch.

        unexplained='drop': everything that is neither constant nor variable is noise and is
        removed (the description, to the letter). unexplained='break': only an insertion is
        removed; a token no learned pattern accounts for ends the part, and what stands on either
        side of it is modelled on its own."""
        s = self.s
        tokens, labels = ev.tokens, ev.labels(s)
        n = len(labels)
        noise = {i: ev.noise(i) for i in range(n) if labels[i] == 'N'}
        segments, start = [], 0
        if s.unexplained == 'break':
            for i in range(n):
                if labels[i] == 'N' and noise[i] != 'inserted':
                    if i > start:
                        segments.append((start, i))
                    start = i + 1
            if start < n:
                segments.append((start, n))
        else:
            segments = [(0, n)]
        out = {'labels': labels, 'noise': [(tokens[i], noise[i]) for i in sorted(noise)], 'parts': []}
        for lo, hi in segments:
            part = self.emit_part(ev, labels, lo, hi)
            if part['chunks'] or part['rule']:
                out['parts'].append(part)
        return out

    def emit_part(self, ev, labels, lo, hi):
        s = self.s
        tokens = ev.tokens
        items = []      # constants: kind C, tokens, support.  slots: kind V, tokens (the value), alts
        p, n = lo, hi
        while p < n:
            if labels[p] == 'N':
                p += 1
                continue
            e = p
            while e < n and labels[e] == labels[p]:
                e += 1
            if labels[p] == 'C':
                for a, b, sup in ev.split_constants(p, e, self.reach):
                    items.append({'kind': 'C', 'lo': a, 'hi': b, 'tokens': tokens[a:b], 'support': sup})
            elif s.slots == 'gap':
                items.append({'kind': 'V', 'lo': p, 'hi': e, 'tokens': tokens[p:e],
                              'alts': ev.gap_alternatives(p, e)})
            else:
                for i in range(p, e):
                    items.append({'kind': 'V', 'lo': i, 'hi': i + 1, 'tokens': tokens[i:i + 1],
                                  'alts': Counter({(x,): c for x, c in ev.alternatives(i).items()})})
            p = e
        if s.rejoin:
            items = self.rejoin(items)
        result = {'span': (lo, hi), 'items': items, 'rule': None, 'sequence': None, 'chunks': [],
                  'bindings': [], 'new_vars': [], 'recognised': False, 'probe': None, 'node2b': [],
                  'inside': []}
        kinds = [item['kind'] for item in items]
        if len(items) < 2 or 'C' not in kinds:
            # Nothing node_1b can learn: fewer than two symbols, or no constant to anchor a rule.
            # A lone chunk of two or more tokens is still a contiguous match, so node_1a learns it.
            for item in items:
                if item['kind'] == 'C' and len(item['tokens']) >= 2:
                    name = self.chunk(item['tokens'])
                    result['chunks'].append((name, item['tokens'], item['support'], 'match', self.node1a.frequency(name)))
            return result

        symbols, alternatives = self.stand_for(items, result)
        ids = self.name_vars(items, kinds, symbols, alternatives, result)
        self.record(result, items, symbols, alternatives, ids, ev)
        return result

    def stand_for(self, items, result, how='match'):
        """What stands for each item: a constant is one symbol (a token, or a chunk's name, learned
        in node_1a). A slot's value is one symbol too (values='name'), or its own tokens
        (values='sequence')."""
        spelled = self.s.values == 'sequence'
        symbols, alternatives = [], []
        for item in items:
            if item['kind'] == 'C':
                symbol = self.chunk(item['tokens'])
                symbols.append((symbol,))
                alternatives.append(None)
                if len(item['tokens']) >= 2:
                    result['chunks'].append((symbol, item['tokens'], item['support'],
                                             'rejoined' if item.get('rejoined') else how,
                                             self.node1a.frequency(symbol)))
            elif spelled:
                symbols.append(tuple(item['tokens']))
                alternatives.append(Counter({tuple(filler): support
                                             for filler, support in sorted(item['alts'].items())}))
            else:
                symbol = self.chunk(item['tokens'])
                symbols.append((symbol,))
                if len(item['tokens']) >= 2:
                    result['chunks'].append((symbol, item['tokens'], 0, 'value', self.node1a.frequency(symbol)))
                alts = Counter()
                for filler, support in sorted(item['alts'].items()):
                    alts[(self.chunk(filler, learn=False),)] += support
                alternatives.append(alts)
        return symbols, alternatives

    def record(self, result, items, symbols, alternatives, ids, ev):
        """One instance of a rule, into the nodes: the rule (node_1b), each VAR with its value, the
        values together, VARs side by side (node_2b), and the rule's name in order (node_2a)."""
        s = self.s
        spelled = s.values == 'sequence'
        kinds = [item['kind'] for item in items]

        def shown(value):       # a value as the result reports it
            return list(value) if spelled else value[0]

        sequence, k = [], 0
        for kind, value in zip(kinds, symbols):
            if kind == 'C':
                sequence.append(value[0])
            else:
                sequence.append(ids[k])
                k += 1
        before = self.node1b.frequency(pattern_name([[x] for x in sequence]))
        rule = self.node1b.learn([[x] for x in sequence])
        result.update(rule=rule, sequence=sequence, rule_frequency=before + 1,
                      symbols=[shown(value) if kind == 'V' else value[0] for kind, value in zip(kinds, symbols)])
        if s.topdown:
            spelled_out = [x for item, symbol in zip(items, sequence)
                           for x in (item['tokens'] if item['kind'] == 'C' else [symbol])]
            self.rule_of[bare(self.node1t.learn([[x] for x in spelled_out]))] = sequence

        # node_2b: each VAR with its value; the values of one instance together; VARs side by side
        row, k = [], 0
        for item, value, alts in zip(items, symbols, alternatives):
            if item['kind'] != 'V':
                continue
            var = ids[k]
            k += 1
            entry = [var] + list(value)
            if s.inside and spelled:    # before the value is learned, as at node_0
                item['inside'] = self.read_inside(var, list(value))
                result['inside'].append(item['inside'])
            known = self.node2b.frequency(pattern_name([[x] for x in entry])) > 0
            self.node2b.learn([[x] for x in entry])
            result['bindings'].append((var, shown(value), 'known' if known else 'new',
                                       {(tuple(a) if spelled else a[0]): c for a, c in sorted(alts.items())}))
            for alt in sorted(alts):
                other = [var] + list(alt)
                if self.node2b.frequency(pattern_name([[x] for x in other])) == 0:
                    self.node2b.learn([[x] for x in other])
                    result['node2b'].append(('value a learned pattern has there', other))
            row += entry
        if len(ids) >= 2:
            self.node2b.learn([[x] for x in row])
            result['node2b'].append(('values together', row))
            if s.slots == 'position' and ev is not None:
                positions = [item['lo'] for item in items if item['kind'] == 'V']
                for values in ev.rows(positions, s.edge_vars):
                    other = [x for pair in zip(ids, values) for x in pair]
                    if other != row and self.node2b.frequency(pattern_name([[x] for x in other])) == 0:
                        self.node2b.learn([[x] for x in other])
                        result['node2b'].append(('values together in a learned pattern', other))
        run = []
        for kind, symbol in list(zip(kinds, sequence)) + [('C', None)]:
            if kind == 'V':
                run.append(symbol)
                continue
            if len(run) >= 2:
                self.node2b.learn([[x] for x in run])
                result['node2b'].append(('VARs side by side', list(run)))
            run = []
        self.node2a.observe([rule], predict=False)

    # -- Spell's loop as the outer loop ---------------------------------------
    def next_var(self):
        self.var_count += 1
        return f'{VAR}{self.var_count}'

    def rule_of_template(self, template):
        """The node_1b form of a template: each run of constants by its chunk's name, VARs as they are."""
        out, run = [], []
        for symbol in list(template) + [None]:
            if symbol is not None and not symbol.startswith(VAR):
                run.append(symbol)
                continue
            if run:
                out.append(run[0] if len(run) == 1 else pattern_name([[x] for x in run]))
                run = []
            if symbol is not None:
                out.append(symbol)
        return out

    def read_by_templates(self, tokens):
        """loop='templates'. The template node is the rule store: the sequence joins the template it
        shares most with (hpcrd/templates.py), and the nodes above are fed from that. A VAR is a
        placeholder of the template and keeps its symbol when the template is edited. When the
        template changes, the old rule in node_1b is retired with it."""
        n = len(tokens)
        name, joined, _gaps = self.reader.read(tokens)
        out = {'labels': ['C'] * n, 'noise': [], 'parts': [], 'evidence': None, 'template': name, 'joined': joined,
               'changed': False}
        if not joined:
            return out      # a type of its own so far: nothing above the template
        last = self.reader.last
        r, slots = last['reading'], iter(last['slots'])
        items, run = [], None
        for (q0, i0), (q1, i1) in zip([(-1, -1)] + r.pairs, r.pairs + [(len(r.pattern), n)]):
            if q1 - q0 > 1 or i1 - i0 > 1:
                if run:
                    items.append({'kind': 'C', 'lo': run[0], 'hi': run[1], 'tokens': tokens[run[0]:run[1]],
                                  'support': last['lines before']})
                    run = None
                var, lo, hi, held = next(slots)
                items.append({'kind': 'V', 'lo': lo, 'hi': hi, 'tokens': tokens[lo:hi], 'var': var,
                              'alts': Counter({tuple(held): last['lines before']}) if held else Counter()})
            if i1 < n:
                run = (run[0], i1 + 1) if run else (i1, i1 + 1)
        if run:
            items.append({'kind': 'C', 'lo': run[0], 'hi': run[1], 'tokens': tokens[run[0]:run[1]],
                          'support': last['lines before']})
        for item in items:
            if item['kind'] == 'V':
                out['labels'][item['lo']:item['hi']] = ['V'] * (item['hi'] - item['lo'])
        part = {'span': (0, n), 'items': items, 'rule': None, 'sequence': None, 'chunks': [], 'bindings': [],
                'new_vars': [], 'recognised': not last['changed'], 'probe': None, 'node2b': [], 'inside': [],
                'by_template': name}
        out.update(parts=[part], changed=last['changed'], old=last['old'], new=last['new'])
        symbols, alternatives = self.stand_for(items, part, how='rule')
        if not any(item['kind'] == 'V' for item in items):
            return out      # the type has no VAR yet: the sequence again, whole. Its chunk is counted.
        self.record(part, items, symbols, alternatives, [item['var'] for item in items if item['kind'] == 'V'], None)
        if last['changed']:     # the rule was edited: its earlier form is retired, not deleted
            old = self.rule_of_template(last['old'])
            if len(old) >= 2 and self.node1b.frequency(pattern_name([[x] for x in old])):
                self.node1b.retire([pattern_name([[x] for x in old])])
                part['retired'] = old
        return out

    # -- top-down: a learned rule reads a new sequence -----------------------
    def read_by_rule(self, tokens):
        """Is the sequence an instance of a rule already learned?

        node_1t holds each rule with its chunks spelled out: [show] [flights] [from] [VAR|1] [to]
        [denver] [.]. KATO lines the raw sequence up with those. A rule fits when every one of its
        constants is matched, in order, and what is left of the sequence stands, gap for gap,
        against exactly one VAR. Then the gaps are the values, of any length, with no earlier
        sequence needed to compare with. Of the rules that fit, the one with the most constants
        reads the sequence; then the one learned most often; then the first by name."""
        events = [[x] for x in tokens]
        best = None
        for p in sorted(self.node1t.predict(events)['predictions'], key=lambda p: p['name']):
            r = read(p, events, whole=True)
            slots, anchors = [], [(-1, -1)] + r.pairs + [(len(r.pattern), len(tokens))]
            for (q0, i0), (q1, i1) in zip(anchors, anchors[1:]):
                seen, held = i1 - i0 - 1, r.pattern[q0 + 1:q1]
                if seen and len(held) == 1 and held[0].startswith(VAR):
                    slots.append((i0 + 1, i1))
                elif seen or held:
                    slots = None
                    break
            if slots is None:
                continue
            key = (len(r.pairs), r.frequency)
            if best is None or key > best[0]:
                best = (key, r, slots)
        if best is None:
            return None
        _key, r, slots = best
        items, position, k = [], 0, 0
        for symbol in self.rule_of[r.name]:
            if symbol.startswith(VAR):
                lo, hi = slots[k]
                k += 1
                items.append({'kind': 'V', 'lo': lo, 'hi': hi, 'tokens': tokens[lo:hi], 'alts': Counter()})
            else:
                hi = position + (len(self.node1a.pattern(symbol)) if symbol.startswith(PREFIX) else 1)
                items.append({'kind': 'C', 'lo': position, 'hi': hi, 'tokens': tokens[position:hi],
                              'support': r.frequency})
            position = items[-1]['hi']
        labels = [item['kind'] for item in items for _ in range(item['hi'] - item['lo'])]
        part = {'span': (0, len(tokens)), 'items': items, 'rule': None, 'sequence': None, 'chunks': [],
                'bindings': [], 'new_vars': [], 'recognised': True, 'probe': None, 'node2b': [],
                'inside': [], 'by_rule': PREFIX + r.name}
        symbols, alternatives = self.stand_for(items, part, how='rule')
        self.record(part, items, symbols, alternatives,
                    [x for x in self.rule_of[r.name] if x.startswith(VAR)], None)
        return {'labels': labels, 'noise': [], 'parts': [part], 'evidence': None, 'by_rule': PREFIX + r.name,
                'reading': r}

    # -- three ways to give a slot its VAR id -------------------------------
    def new_var(self, result):
        self.var_count += 1
        var = f'{VAR}{self.var_count}'
        result['new_vars'].append(var)
        return var

    def name_vars(self, items, kinds, symbols, alternatives, result):
        s = self.s
        slot_count = kinds.count('V')
        if slot_count == 0:
            return []
        if s.naming == 'rule':
            # Show node_1b the sequence with the observed values standing in the slots.
            # A learned rule with the same constants in the same places hands back its VAR ids.
            probe = [x for value in symbols for x in value]
            result['probe'] = probe
            want = tuple(value[0] if kind == 'C' else None for kind, value in zip(kinds, symbols))
            out = self.node1b.predict([[x] for x in probe])
            for p in sorted(out['predictions'], key=lambda p: p['name']):
                learned = flat(p['past']) + flat(p['present']) + flat(p['future'])
                if shape(learned) == want:
                    result['recognised'] = True
                    result['recognition'] = p
                    return [x for x in learned if x.startswith(VAR)]
            return [self.new_var(result) for _ in range(slot_count)]

        if s.naming == 'neighbours':
            # The id is looked up from the tokens on either side of the run of slots.
            ids, i = [], 0
            while i < len(items):
                if kinds[i] != 'V':
                    i += 1
                    continue
                j = i
                while j < len(items) and kinds[j] == 'V':
                    j += 1
                left = items[i - 1]['tokens'][-1] if i > 0 else '^'
                right = items[j]['tokens'][0] if j < len(items) else '$'
                for k in range(j - i):
                    key = (left, right, k, j - i)
                    if key not in self.frames:
                        self.frames[key] = self.new_var(result)
                    ids.append(self.frames[key])
                i = j
            return ids

        if s.naming == 'values':
            # A VAR is a class of values. Ask node_2b which VARs already hold the slot's values
            # (the observed one and those the learned patterns have there); most shared values wins.
            ids, here = [], {}      # here: VARs given earlier in this same sequence -> their values
            for kind, value, alts in zip(kinds, symbols, alternatives):
                if kind != 'V':
                    continue
                values = set([value]) | set(alts)
                shared = Counter()
                for v in sorted(values):
                    for p in self.node2b.predict([[x] for x in v])['predictions']:
                        learned = flat(p['past']) + flat(p['present']) + flat(p['future'])
                        if learned[0].startswith(VAR) and tuple(learned[1:]) == v:
                            shared[learned[0]] += 1
                for var, held in here.items():
                    shared[var] = max(shared[var], len(values & held))
                shared = {v: c for v, c in shared.items() if c > 0}
                if shared:
                    best = max(shared.values())
                    var = min((v for v, c in shared.items() if c == best), key=lambda v: int(v[len(VAR):]))
                else:
                    var = self.new_var(result)
                here.setdefault(var, set()).update(values)
                ids.append(var)
            return ids
        raise ValueError(f"unknown naming {s.naming!r}")

    # -- inside a VAR: the same reading, one level down ----------------------
    def read_inside(self, var, tokens):
        """What a VAR's earlier values say about the inside of a new value, before it is learned.

        node_2b holds each value as [VAR, token, ...], so its ensemble for the new value lines the
        value up with the VAR's earlier values, the way node_0's ensemble lines a sequence up with
        earlier sequences. An earlier value is
            the same      the value was seen whole before: a unit;
            apart         it shares no token with the value: another unit, silent about the inside;
            partly alike  it shares some tokens: the shared parts and the differing parts are the
                          value's own constants and slots.
        A value with two or more parts, one of them varying, is recorded as what the VAR is made of:
        an inner rule in node_1b, and [VAR, PTRN|<inner rule>] in node_2b. The rule that holds the
        VAR is not touched.
        """
        tokens = list(tokens)
        n = len(tokens)
        events = [[var]] + [[t] for t in tokens]
        info = {'var': var, 'value': tokens, 'same': 0, 'apart': 0, 'partly': [], 'parts': [],
                'rule': None, 'sequence': None, 'rule_frequency': 0, 'recognised': False,
                'bindings': [], 'chunks': [], 'inside': [], 'new_vars': []}
        related = []
        for p in sorted(self.node2b.predict(events)['predictions'], key=lambda p: p['name']):
            learned = flat(p['past']) + flat(p['present']) + flat(p['future'])
            if learned[0] != var or any(x.startswith(VAR) or x.startswith(PREFIX) for x in learned[1:]):
                continue    # values together, VARs side by side, what a VAR is made of, other VARs' values
            r = read(p, events, whole=True)
            if r.relation[0][0] != 'M':
                continue
            if learned[1:] == tokens:
                info['same'] = r.frequency
            elif len(r.pairs) == 1:
                info['apart'] += 1
            else:
                related.append(r)
                info['partly'].append((learned[1:], r.frequency))
        if not related:
            return info
        ev = Evidence(tokens)
        for r, places in whole_places(related):
            ev.add(r, places, offset=-1)
        # Parts: a stretch seen whole in an earlier value stays whole; the rest stands as it is.
        matched = [bool(ev.match[p]) for p in range(n)]
        parts, p = [], 0
        while p < n:
            e = p
            while e < n and matched[e] == matched[p]:
                e += 1
            cuts = ev.split_constants(p, e, None) if matched[p] else [(p, e, 0)]
            for a, b, support in cuts:
                alts = ev.gap_alternatives(a, b)
                # shared and never replaced: a constant of the VAR. Otherwise a slot of its own.
                kind = 'C' if matched[p] and not alts else 'V'
                parts.append({'kind': kind, 'lo': a, 'hi': b, 'tokens': tokens[a:b], 'support': support,
                              'alts': alts, 'shared': matched[p]})
            p = e
        info['parts'] = parts
        kinds = [part['kind'] for part in parts]
        if len(parts) < 2 or 'V' not in kinds:
            return info

        symbols = []
        for part in parts:
            if part['kind'] == 'C':
                symbol = self.chunk(part['tokens'])
                symbols.append(symbol)
                if len(part['tokens']) >= 2:
                    info['chunks'].append((symbol, part['tokens'], part['support'], 'match',
                                           self.node1a.frequency(symbol)))
            else:
                symbols.append(None)
        want = tuple(symbols)
        # The ids of the inner slots: from what this VAR is already made of; else, when the inner
        # rule has a constant, from any learned rule of the same shape; else new.
        ids = None
        for p in sorted(self.node2b.predict([[var]])['predictions'], key=lambda p: p['name']):
            learned = flat(p['past']) + flat(p['present']) + flat(p['future'])
            if len(learned) == 2 and learned[0] == var and self.node1b.frequency(learned[1]):
                inner = [event[0] for event in self.node1b.pattern(learned[1])]
                if shape(inner) == want:
                    ids = [x for x in inner if x.startswith(VAR)]
                    break
        if ids is None and 'C' in kinds:
            probe = [x for part, symbol in zip(parts, symbols) for x in ([symbol] if symbol else part['tokens'])]
            for p in sorted(self.node1b.predict([[x] for x in probe])['predictions'], key=lambda p: p['name']):
                learned = flat(p['past']) + flat(p['present']) + flat(p['future'])
                if shape(learned) == want:
                    ids = [x for x in learned if x.startswith(VAR)]
                    break
        info['recognised'] = ids is not None
        if ids is None:
            ids = [self.new_var(info) for _ in range(kinds.count('V'))]
        sequence, k = [], 0
        for symbol in symbols:
            if symbol is None:
                sequence.append(ids[k])
                k += 1
            else:
                sequence.append(symbol)
        before = self.node1b.frequency(pattern_name([[x] for x in sequence]))
        rule = self.node1b.learn([[x] for x in sequence])
        self.node2b.learn([[var], [rule]])
        info.update(rule=rule, sequence=sequence, rule_frequency=before + 1)
        k = 0
        for part in parts:
            if part['kind'] != 'V':
                continue
            inner_var = ids[k]
            k += 1
            entry = [inner_var] + part['tokens']
            part['var'] = inner_var
            if len(part['tokens']) >= 2:    # shorter than the value it is part of, so this ends
                part['inside'] = self.read_inside(inner_var, part['tokens'])
                info['inside'].append(part['inside'])
            known = self.node2b.frequency(pattern_name([[x] for x in entry])) > 0
            self.node2b.learn([[x] for x in entry])
            info['bindings'].append((inner_var, part['tokens'], 'known' if known else 'new',
                                     dict(sorted(part['alts'].items()))))
            for alt in sorted(part['alts']):
                other = [inner_var] + list(alt)
                if self.node2b.frequency(pattern_name([[x] for x in other])) == 0:
                    self.node2b.learn([[x] for x in other])
        return info
