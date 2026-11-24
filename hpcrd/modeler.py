"""The module between node_0 and nodes 1a, 1b, 2a, 2b.

    node_0   rolling windows of tokens (KATO: stm_mode=ROLLING, max_pattern_length=window)
       | prediction ensemble, one per token
    module   reads each prediction's matches / missing / extras (alignment.read)
       |-> node_1a   contiguous matches                    -> PTRN|<chunk>
       |-> node_1b   [chunk names, single tokens, VAR|n]   -> PTRN|<rule>
       |       '-> node_2a   names of node_1b patterns, in order
       '-> node_2b   VAR|n with its values, joint values, runs of VARs

Every choice the description leaves open is a named setting (Settings), so the
experiments can run the alternatives side by side. Nothing is random, no clock
is read, and every loop over a set or dict runs in sorted order.

The module keeps one record of its own: at which step node_0 learned each
window (`learned_at`). KATO returns a pattern's name and frequency with a
prediction, not where it was learned, and the module needs that to hold out
echoes and to count evidence in earlier places of the stream.
"""
from collections import Counter
from dataclasses import dataclass

from .alignment import flat, read
from .kato_node import PREFIX, Node, bare, Pattern

VAR = 'VAR|'


@dataclass(frozen=True)
class Settings:
    window: int = 7              # node_0's rolling window
    recall_threshold: float = 0.1  # node_0: how unlike a learned pattern may be and still be read
    span: str = 'window'         # 'window': one rule per ensemble | 'stream': stitched along the stream
    markers: tuple = ()          # span='stream': tokens that close a stretch (the application's cut)
    naming: str = 'rule'         # what gives a slot its VAR id: 'rule' | 'neighbours' | 'values'
    slots: str = 'position'      # 'position': one VAR per aligned position | 'gap': one VAR per gap
    edge_vars: bool = False      # read an extra that lines up with `past`/`future` as a variable too
    mixed: str = 'var'           # a position some patterns match and others substitute: 'var' | 'const'
    min_support: int = 1         # earlier places a substitution must be seen in before it makes a variable
    unexplained: str = 'drop'    # a token no learned pattern accounts for: 'drop' it as noise | 'break' the stretch there
    rejoin: bool = True          # constants left side by side once noise is dropped are joined when node_1a holds the joined chunk
    node2a_window: int = 2       # node_2a's own rolling window over rule names


def pattern_name(events):
    return PREFIX + Pattern([list(e) for e in events]).name


class Evidence:
    """What the held-out ensemble says about each position of a stretch of tokens.

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

    def add(self, reading, places, offset=0, edge_vars=False):
        """`places`: the stream position of the pattern's first token, once per earlier learn."""
        n = len(self.tokens)
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
        k = min(hi - lo, window)
        return min(self.covered(x, x + k) for x in range(lo, hi - k + 1))

    def split_constants(self, lo, hi, window):
        """Cut a run of constants into chunks. A chunk is a stretch that was seen whole before:
        one contiguous match covers it (for a stretch longer than the window, one contiguous
        match covers every window-length piece of it). The longest such stretch is taken first,
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
        a pattern that matches the token before and the token after gives what it has between."""
        where = {}
        for offset, r, places in self.readings:
            i_l, i_r = lo - 1 - offset, hi - offset
            if i_l < 0 or i_r >= len(r.relation):
                continue
            rel_l, rel_r = r.relation[i_l], r.relation[i_r]
            if rel_l[0] != 'M' or rel_r[0] != 'M':
                continue
            filler = tuple(r.pattern[rel_l[1] + 1:rel_r[1]])
            if not filler or list(filler) == self.tokens[lo:hi]:
                continue
            where.setdefault(filler, set()).update(base + rel_l[1] for base in places)
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


class Modeler:
    def __init__(self, settings=Settings()):
        self.s = s = settings
        self.node0 = Node('node_0', recall_threshold=s.recall_threshold, max_predictions=10000,
                          max_pattern_length=s.window, stm_mode='ROLLING')
        self.node1a = Node('node_1a')
        self.node1b = Node('node_1b', max_predictions=10000)
        self.node2a = Node('node_2a', max_pattern_length=s.node2a_window, stm_mode='ROLLING')
        self.node2b = Node('node_2b', max_predictions=10000)
        self.learned_at = {}        # node_0 pattern name -> steps at which that window was learned
        self.var_count = 0
        self.frames = {}            # naming='neighbours': (left token, right token, k, run length) -> VAR id
        self.t = -1
        self.tokens = []            # the stream so far
        self.windows = []           # span='stream': (start position, held-out readings) per step
        self.closed = 0             # span='stream': first stream position not yet modelled
        self.trace = []

    # -- stream in ----------------------------------------------------------
    def feed(self, token):
        self.t += 1
        self.tokens.append(token)
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
        step = {'t': self.t, 'stm': stm, 'readings': readings, 'echoes': echoes,
                'ensemble': len(out['predictions']), 'learned': out['auto_learned_pattern'],
                'raw': out['predictions']}
        if self.s.span == 'window':
            ev = Evidence(stm)
            for r, places in readings:
                ev.add(r, places, 0, self.s.edge_vars)
            step.update(self.emit(ev))
            step['evidence'] = ev
        else:
            self.windows.append((self.t - len(stm) + 1, readings))
            step['stretches'] = self.close_stretches(final=False)
        if out['auto_learned_pattern']:
            self.learned_at.setdefault(bare(out['auto_learned_pattern']), []).append(self.t)
        self.trace.append(step)
        return step

    def finish(self):
        """span='stream': model what is still open at the end of the stream."""
        if self.s.span == 'stream':
            out = self.close_stretches(final=True)
            self.trace.append({'t': self.t, 'stm': [], 'readings': [], 'echoes': 0, 'ensemble': 0,
                               'learned': None, 'raw': [], 'stretches': out, 'final': True})
            return out
        return []

    def close_stretches(self, final):
        """A stretch ends at a marker token. It is modelled once the window has moved past its last
        token, so that every window that saw any of its tokens has been read (window-1 tokens later)."""
        out = []
        while True:
            end = None
            for n in range(self.closed, len(self.tokens)):
                if self.tokens[n] in self.s.markers:
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
            for start, readings in self.windows:
                if start + self.s.window <= a or start >= b:
                    continue
                for r, places in readings:
                    ev.add(r, places, start - a, self.s.edge_vars)
            result = self.emit(ev)
            result['stretch'] = (a, b)
            result['evidence'] = ev
            out.append(result)
            self.closed = b
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
                for a, b, sup in ev.split_constants(p, e, s.window):
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
                  'bindings': [], 'new_vars': [], 'recognised': False, 'probe': None, 'node2b': []}
        kinds = [item['kind'] for item in items]
        if len(items) < 2 or 'C' not in kinds:
            # Nothing node_1b can learn: fewer than two symbols, or no constant to anchor a rule.
            # A lone chunk of two or more tokens is still a contiguous match, so node_1a learns it.
            for item in items:
                if item['kind'] == 'C' and len(item['tokens']) >= 2:
                    name = self.chunk(item['tokens'])
                    result['chunks'].append((name, item['tokens'], item['support'], 'match', self.node1a.frequency(name)))
            return result

        symbols, alternatives = [], []
        for item in items:
            symbol = self.chunk(item['tokens'])
            symbols.append(symbol)
            if item['kind'] == 'C':
                alternatives.append(None)
                if len(item['tokens']) >= 2:
                    result['chunks'].append((symbol, item['tokens'], item['support'],
                                             'rejoined' if item.get('rejoined') else 'match',
                                             self.node1a.frequency(symbol)))
            else:
                if len(item['tokens']) >= 2:
                    result['chunks'].append((symbol, item['tokens'], 0, 'value', self.node1a.frequency(symbol)))
                alts = Counter()
                for filler, support in sorted(item['alts'].items()):
                    alts[self.chunk(filler, learn=False)] += support
                alternatives.append(alts)

        ids = self.name_vars(items, kinds, symbols, alternatives, result)
        sequence, k = [], 0
        for kind, symbol in zip(kinds, symbols):
            if kind == 'C':
                sequence.append(symbol)
            else:
                sequence.append(ids[k])
                k += 1
        before = self.node1b.frequency(pattern_name([[x] for x in sequence]))
        rule = self.node1b.learn([[x] for x in sequence])
        result.update(rule=rule, sequence=sequence, rule_frequency=before + 1, symbols=symbols)

        # node_2b: each VAR with its value; the values of one instance together; VARs side by side
        row, k = [], 0
        for kind, symbol, alts in zip(kinds, symbols, alternatives):
            if kind != 'V':
                continue
            var = ids[k]
            k += 1
            known = self.node2b.frequency(pattern_name([[var], [symbol]])) > 0
            self.node2b.learn([[var], [symbol]])
            result['bindings'].append((var, symbol, 'known' if known else 'new', dict(sorted(alts.items()))))
            for alt in sorted(alts):
                if self.node2b.frequency(pattern_name([[var], [alt]])) == 0:
                    self.node2b.learn([[var], [alt]])
                    result['node2b'].append(('value a learned pattern has there', [var, alt]))
            row += [var, symbol]
        if len(ids) >= 2:
            self.node2b.learn([[x] for x in row])
            result['node2b'].append(('values together', row))
            if s.slots == 'position':
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
        return result

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
            probe = [[x] for x in symbols]
            result['probe'] = symbols
            out = self.node1b.predict(probe)
            for p in sorted(out['predictions'], key=lambda p: p['name']):
                learned = flat(p['past']) + flat(p['present']) + flat(p['future'])
                if len(learned) != len(symbols):
                    continue
                if all((learned[i] == symbols[i]) if kinds[i] == 'C' else learned[i].startswith(VAR)
                       for i in range(len(symbols))):
                    result['recognised'] = True
                    result['recognition'] = p
                    return [learned[i] for i in range(len(symbols)) if kinds[i] == 'V']
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
            for kind, symbol, alts in zip(kinds, symbols, alternatives):
                if kind != 'V':
                    continue
                values = set([symbol]) | set(alts)
                shared = Counter()
                for value in sorted(values):
                    for p in self.node2b.predict([[value]])['predictions']:
                        learned = flat(p['past']) + flat(p['present']) + flat(p['future'])
                        if len(learned) == 2 and learned[0].startswith(VAR) and learned[1] == value:
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
