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
(Spell looks at every template), and ties go to the shorter template and then to the smaller
pattern name (Spell: the shorter, then unspecified). The alignment is the one KATO returns.

`successor` (which pattern replaced which) is kept here for the reader's own bookkeeping. KATO
does not record it.
"""
from .alignment import read
from .kato_node import Node, bare

PARAMETER = 'VAR|*'


class TemplateReader:
    def __init__(self, tau=0.5, recall_threshold=0.1):
        self.tau = tau
        self.node = Node('templates', recall_threshold=recall_threshold, max_predictions=10000)
        self.successor = {}     # retired pattern name -> the pattern that replaced it
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
            key = (len(r.pairs), -len(r.pattern))
            if best is None or key > best[0]:
                best = (key, r)
        if best is None or best[0][0] < self.tau * len(tokens):
            return self.keep(tokens), False, []
        r = best[1]
        new, gaps = [], []
        anchors = [(-1, -1)] + r.pairs + [(len(r.pattern), len(tokens))]
        for (q0, i0), (q1, i1) in zip(anchors, anchors[1:]):
            if q1 - q0 > 1 or i1 - i0 > 1:
                new.append(PARAMETER)
            if i1 - i0 > 1:
                gaps.append((i0 + 1, i1))
            if i1 < len(tokens):
                new.append(tokens[i1])
        learned = self.keep(new)
        if learned != r.name:           # the template changed: the old one is retired, not deleted
            self.node.retire([r.name])
            self.successor[r.name] = learned
        return learned, True, gaps

    def gaps(self, tokens, name):
        """The line's parameters under its message type's template as it is now."""
        constants = [x for x in self.template(name) if x != PARAMETER]
        out, i, start = [], 0, 0
        for constant in constants:      # the constants are a subsequence of every line of the type
            j = tokens.index(constant, i)
            if j > start:
                out.append((start, j))
            i = start = j + 1
        if start < len(tokens):
            out.append((start, len(tokens)))
        return out
