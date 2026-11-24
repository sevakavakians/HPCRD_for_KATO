"""Spell's loop on a KATO node.

Spell (Du and Li 2016, https://doi.org/10.1109/ICDM.2016.0103) keeps one template per message
type. A new line joins the type whose template shares the longest common subsequence with it,
when that subsequence is at least tau of the line's length; the template then becomes that
subsequence, with one placeholder wherever either side had something else. Otherwise the line
is a new type.

Each step is something KATO already does:

    the longest common subsequence     KATO's matcher: `matches`, with `missing` and `extras`
                                       giving what each side has in the gaps
    a template                         a pattern: tokens and one placeholder symbol
    replacing a template               learn the new pattern, retire the old one (a tombstone:
                                       it stays stored, reads skip it, and it can be restored)

What is not Spell's: the node's recall_threshold decides which templates KATO returns at all
(Spell looks at every template), a line of one symbol is kept as a type of its own (KATO does
not learn a pattern of one symbol), and the alignment is the one KATO returns.

Ties go to the shorter template and then to the older type, as in the implementation the log
benchmark used. A prediction does not say when its pattern was learned, so the reader keeps two
records of its own: `born` (the order in which types were made) and `successor` (which pattern
replaced which).
"""
from .alignment import read
from .kato_node import Node, bare

PARAMETER = 'VAR|*'


class TemplateReader:
    def __init__(self, tau=0.5, recall_threshold=0.1, parameter=PARAMETER):
        """`parameter`: the placeholder symbol. A sequence that already holds that symbol (the log
        benchmark's preprocessing writes `<*>` into the lines) matches a template's placeholder
        like any other symbol, because to KATO it is one."""
        self.tau = tau
        self.parameter = parameter
        self.node = Node('templates', recall_threshold=recall_threshold, max_predictions=10000)
        self.successor = {}     # retired pattern name -> the pattern that replaced it
        self.born = {}          # live pattern name -> the order in which its type was made
        self.lines = 0
        self.revived = 0        # times a template's content was that of a pattern retired earlier

    def keep(self, symbols):
        """Learn a template and make sure it is live. A pattern's name is the hash of its content,
        so content that was a template once before, and was retired, is the same pattern again."""
        name = bare(self.node.learn([[x] for x in symbols]))
        if name in self.successor:
            self.node.unretire([name])
            del self.successor[name]
            self.revived += 1
        self.born.setdefault(name, len(self.born) + len(self.successor))
        return name

    def current(self, name):
        """The template a line's message type has now."""
        name = bare(name)
        while name in self.successor:
            name = self.successor[name]
        return name

    def template(self, name):
        return [event[0] for event in self.node.pattern(self.current(name))]

    def read(self, tokens):
        """One line. Returns (pattern name of its message type, joined an existing type, gaps):
        gaps are the stretches of the line that stand at a placeholder, as (first, after last)."""
        self.lines += 1
        tokens = list(tokens)
        events = [[t] for t in tokens]
        if len(tokens) < 2:     # KATO does not learn a pattern of one symbol
            return None, False, []
        best = None
        for p in sorted(self.node.predict(events)['predictions'], key=lambda p: p['name']):
            r = read(p, events, whole=True)
            key = (len(r.pairs), -len(r.pattern), -self.born[r.name])
            if best is None or key > best[0]:
                best = (key, r)
        if best is None or best[0][0] < self.tau * len(tokens):
            return self.keep(tokens), False, []
        r = best[1]
        new, gaps = [], []
        anchors = [(-1, -1)] + r.pairs + [(len(r.pattern), len(tokens))]
        for (q0, i0), (q1, i1) in zip(anchors, anchors[1:]):
            if i1 - i0 > 1:
                gaps.append((i0 + 1, i1))
            for symbol in ([self.parameter] if q1 - q0 > 1 or i1 - i0 > 1 else []) + ([tokens[i1]] if i1 < len(tokens) else []):
                if not (symbol == self.parameter and new and new[-1] == self.parameter):   # adjacent placeholders are one
                    new.append(symbol)
        if len(new) < 2:                # nothing KATO can learn: the line stays a type of its own
            return self.keep(tokens), False, []
        if new != r.pattern:            # the template changes: the old one is retired, not deleted
            age = self.born.pop(r.name)
            learned = self.keep(new)
            self.born[learned] = min(age, self.born[learned])   # the type keeps its place in the order
            self.node.retire([r.name])
            self.successor[r.name] = learned
        else:
            learned = self.keep(new)
        return learned, True, gaps

    def gaps(self, tokens, name):
        """The line's parameters under its message type's template as it is now."""
        constants = [x for x in self.template(name) if x != self.parameter]
        out, i, start = [], 0, 0
        for constant in constants:      # the constants are a subsequence of every line of the type
            j = tokens.index(constant, i)
            if j > start:
                out.append((start, j))
            i = start = j + 1
        if start < len(tokens):
            out.append((start, len(tokens)))
        return out
