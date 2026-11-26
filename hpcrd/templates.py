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
                                       it stays stored, predictions skip it, and it can be restored)

What is not Spell's: the node's recall_threshold decides which templates KATO returns at all
(Spell looks at every template), a line of one symbol is kept as a type of its own (KATO does
not learn a pattern of one symbol), and the alignment is the one KATO returns. On the 16 systems
of the log benchmark only the second of these changes any line's group
(experiments/log_benchmark.py, the run called "lone"). One switch is not Spell's either and is off
unless asked for: `evidence`, a floor on KATO's weight of evidence for a template to be joined.

Ties go to the shorter template and then to the older type, as in the implementation the log
benchmark used. A prediction does not say when its pattern was learned, so the reader keeps
records of its own: the message types in the order they were made, with the pattern that is each
one's template now (`types`, `where`), and which pattern replaced which (`successor`).

A line belongs to a message type, not to a pattern. A pattern's name is the hash of its content,
so when a type's template has moved on and its old content is learned again as a new type, that
is the old pattern's name on a different type. `kind` is the type of the latest line read and
`now(kind)` is the pattern that is that type's template now.
"""
from .alignment import flat, read
from .kato_node import Node, Pattern, bare

PARAMETER = 'VAR|*'


class TemplateReader:
    def __init__(self, tau=0.5, recall_threshold=0.1, parameter=PARAMETER, number=None, evidence=None):
        """`parameter`: the placeholder symbol. A sequence that already holds that symbol (the log
        benchmark's preprocessing writes `<*>` into the lines) matches a template's placeholder
        like any other symbol, because to KATO it is one.

        `number`: a function that returns a new placeholder symbol starting with `parameter`
        (`VAR|7`). Then every placeholder of a template has its own symbol, and keeps it when the
        template is edited: a gap that holds an earlier placeholder takes that one's symbol.

        `evidence`: not Spell's. When set, a line may join only a template whose weight of evidence
        for the line is above it, in bits. That is the `bayesian_likelihood` KATO returns with the
        prediction: positive when the template explains the line better than chance does. A template
        that is the line itself is joined whatever its evidence. KATO counts every token at a
        placeholder as noise, so this holds back the lines that carry a value: on the dialogue
        sentences it found fewer of the marked values, not more (experiments/entropy_probe.py)."""
        self.tau = tau
        self.parameter = parameter
        self.number = number
        self.evidence = evidence
        self.last = None        # what the latest read did, for the caller that models it
        self.node = Node('templates', recall_threshold=recall_threshold, max_predictions=10000)
        if not hasattr(self.node, 'retire'):
            raise NotImplementedError("retiring a pattern is mirrored in-process only so far (hpcrd/kato_node.py)")
        self.successor = {}     # retired pattern name -> the pattern that replaced it
        self.types = {}         # live pattern name -> the message types it is the template of, oldest first
        self.where = {}         # message type (its number, in the order the types were made) -> its pattern now
        self.kind = None        # the message type of the latest line read
        self.lines = 0
        self.revived = 0        # times a template's content was that of a pattern retired earlier
        self.merged = 0         # times an edit gave a template the content of another live one

    def keep(self, symbols):
        """Learn a template and make sure it is live. A pattern's name is the hash of its content,
        so content that was a template once before, and was retired, is the same pattern again.
        KATO refuses to learn a retired pattern, so it is un-retired first."""
        events = [[x] for x in symbols]
        name = Pattern(events).name
        if name in self.successor:
            self.node.unretire([name])
            del self.successor[name]
            self.revived += 1
        learned = bare(self.node.learn(events))
        if learned != name:
            raise RuntimeError(f"KATO named {symbols} {learned}, not {name}")
        return name

    def found(self, symbols):
        """A new message type. Its template is the line itself."""
        name = self.keep(symbols)
        if name in self.types:      # a live template with the line's own content would have been joined
            raise RuntimeError(f"a new message type on a live template: {symbols}")
        self.kind = len(self.where)
        self.types[name] = [self.kind]
        self.where[self.kind] = name
        return name

    def now(self, kind):
        """The pattern that is a message type's template now."""
        return self.where[kind]

    def current(self, name):
        """The live pattern a retired one was replaced by, through every replacement since. This
        follows content, not lines: for the template of a line's message type, use `now`."""
        name = bare(name)
        while name in self.successor:
            name = self.successor[name]
        return name

    def template(self, name):
        return [event[0] for event in self.node.pattern(self.current(name))]

    def is_parameter(self, symbol):
        return symbol.startswith(self.parameter) if self.number else symbol == self.parameter

    def read(self, tokens):
        """One line. Returns (pattern name of its message type, joined an existing type, gaps):
        gaps are the stretches of the line that stand at a placeholder, as (first, after last)."""
        self.lines += 1
        self.last = self.kind = None
        tokens = list(tokens)
        events = [[t] for t in tokens]
        if len(tokens) < 2:     # KATO does not learn a pattern of one symbol
            return None, False, []
        best = None
        for p in sorted(self.node.predict(events)['predictions'], key=lambda p: p['name']):
            r = read(p, events, whole=True)
            if self.evidence is not None and r.pattern != tokens and p['bayesian_likelihood'] <= self.evidence:
                continue
            key = (len(r.pairs), -len(r.pattern), -self.types[r.name][0])
            if best is None or key > best[0]:
                best = (key, r, p)
        if best is None or best[0][0] < self.tau * len(tokens):
            return self.found(tokens), False, []
        r = best[1]
        new, gaps, slots = [], [], []
        anchors = [(-1, -1)] + r.pairs + [(len(r.pattern), len(tokens))]
        for (q0, i0), (q1, i1) in zip(anchors, anchors[1:]):
            if i1 - i0 > 1:
                gaps.append((i0 + 1, i1))
            between = []
            if q1 - q0 > 1 or i1 - i0 > 1:
                held = r.pattern[q0 + 1:q1]
                earlier = [x for x in held if self.is_parameter(x)]
                between = [earlier[0] if earlier else (self.number() if self.number else self.parameter)]
                # the slot: its symbol, where the line's value stands, and what the template held there
                # as constants before this line (a value every earlier line of the type shared)
                slots.append((between[0], i0 + 1, i1, [] if earlier else held))
            for symbol in between + ([tokens[i1]] if i1 < len(tokens) else []):
                if not (symbol == self.parameter and new and new[-1] == self.parameter):   # adjacent placeholders are one
                    new.append(symbol)
        if len(new) < 2:                # placeholders only, which run together into one symbol: nothing KATO can learn
            if r.pattern != tokens:
                return self.found(tokens), False, []    # the line stays a type of its own
            new = r.pattern             # the line is its type's template already: it joins, and nothing changes
        before = self.node.frequency(r.name)
        learned = self.settle(r.name, r.pattern, new)
        self.last = {'reading': r, 'old': r.pattern, 'new': new, 'slots': slots, 'changed': new != r.pattern,
                     'lines before': before, 'kind': self.kind,
                     'evidence': best[2].get('bayesian_likelihood')}    # KATO's weight of evidence for the template joined
        return learned, True, gaps

    def settle(self, name, old, new):
        """The line joins the message type whose template is the pattern `name`, and that template
        becomes `new`. Returns the pattern that is the template now."""
        kinds = self.types[name]
        self.kind = kinds[0]
        if new == old:
            return self.keep(new)
        del self.types[name]            # the template changes: the old one is retired, not deleted
        learned = self.keep(new)
        if learned in self.types:       # another type has this template already: one pattern for both
            self.merged += 1
        self.types[learned] = sorted(self.types.get(learned, []) + kinds)
        for kind in kinds:              # the type keeps its number, and so its place in the order
            self.where[kind] = learned
        self.node.retire([name])
        self.successor[name] = learned
        return learned

    def check(self):
        """The reader's records against the node's: every live pattern is the template of at least one
        message type, every type stands at one live pattern, and every retired pattern has the one
        that replaced it. Raises AssertionError."""
        live = {name for name in self.node.patterns if name not in self.node.retired}
        assert set(self.types) == live, 'a live pattern that is no type\'s template, or the reverse'
        assert sorted(k for kinds in self.types.values() for k in kinds) == list(range(len(self.where)))
        assert all(kind in self.types[name] for kind, name in self.where.items())
        assert set(self.successor) == set(self.node.retired)

    def gaps(self, tokens, name):
        """The line's parameters under its message type's template as it is now."""
        constants = [x for x in self.template(name) if not self.is_parameter(x)]
        out, i, start = [], 0, 0
        for constant in constants:      # the constants are a subsequence of every line of the type
            j = tokens.index(constant, i)
            if j > start:
                out.append((start, j))
            i = start = j + 1
        if start < len(tokens):
            out.append((start, len(tokens)))
        return out


class PositionReader(TemplateReader):
    """Drain's rule on a KATO node.

    Drain (He, Zhu, Zheng and Lyu 2017, https://doi.org/10.1109/ICWS.2017.13) keeps one template per
    message type, as Spell does, and decides differently which type a line joins:

        1. only a type whose lines have the line's number of tokens;
        2. only a type whose template starts with the line's first `lead` tokens (a token that holds a
           digit counts as a placeholder there, and a placeholder in the template goes with any token);
        3. of those, the type whose template holds the line's own token at the most positions, when
           that is at least `threshold` of the positions (ties: more placeholders, then the older type).

    The template then gets a placeholder at every position where the line has another token. Drain
    finds the types of rules 1 and 2 with a tree of fixed depth, `lead` being that depth less 3. Here
    they are rules read off the prediction, and the node finds the candidates.

    Rule 3 compares by position, where KATO compares by order. It becomes KATO's own comparison once
    a symbol says where its token stands: token `t` at position 3 is the symbol `3|=t`, and a
    template's placeholder there is `3|*`. Two sequences then share a symbol only where they hold the
    same token at the same position, so the prediction's `matches` are Drain's count. A line never
    holds a placeholder symbol: a `<*>` that preprocessing wrote into a line matches nothing, as in
    Drain.

    What is not Drain's: a line of one token is kept as a type of its own, as in TemplateReader;
    two types whose templates come to the same content are one pattern from then on; and the node's
    recall_threshold must not be above `threshold`. On the 16 systems of the log benchmark this
    groups every line as the three rules do without KATO (experiments/log_benchmark.py)."""

    def __init__(self, threshold=0.5, lead=1, recall_threshold=0.1, parameter=PARAMETER):
        if recall_threshold > threshold:
            raise ValueError("the node would not return every template that rule 3 could accept")
        super().__init__(tau=threshold, recall_threshold=recall_threshold, parameter=parameter)
        self.lead = lead

    def symbols(self, template):
        return [f"{i}|*" if token == self.parameter else f"{i}|={token}" for i, token in enumerate(template)]

    def tokens_of(self, symbols):
        """A template's tokens, the placeholder standing as `parameter`."""
        return [self.parameter if rest == '*' else rest[1:] for rest in (symbol.split('|', 1)[1] for symbol in symbols)]

    def is_parameter(self, symbol):
        return symbol.split('|', 1)[1] == '*'

    def key(self, token):
        return self.parameter if token == self.parameter or any(c.isdigit() for c in token) else token

    def same_lead(self, template, tokens):
        return all(self.key(a) in (self.parameter, self.key(b)) for a, b in zip(template[:self.lead], tokens[:self.lead]))

    def found(self, symbols):
        """A new message type. Unlike Spell's rule, Drain's can refuse a line the template that is the
        line's own content (a line of placeholders shares no token with anything). The new type then
        stands at that pattern too."""
        name = Pattern([[x] for x in symbols]).name
        if name not in self.types:
            return super().found(symbols)
        self.keep(symbols)
        self.kind = len(self.where)
        self.types[name] = sorted(self.types[name] + [self.kind])
        self.where[self.kind] = name
        self.merged += 1
        return name

    def read(self, tokens):
        """One line. Returns (pattern name of its message type, joined an existing type, gaps): the
        positions of the line that stand at a placeholder, as (position, position + 1)."""
        self.lines += 1
        self.last = self.kind = None
        tokens = list(tokens)
        if len(tokens) < 2:     # KATO does not learn a pattern of one symbol
            return None, False, []
        best = None
        for p in sorted(self.node.predict([[f"{i}|={token}"] for i, token in enumerate(tokens)])['predictions'], key=lambda p: p['name']):
            pattern = flat(p['past']) + flat(p['present']) + flat(p['future'])
            if len(pattern) != len(tokens):                                 # rule 1
                continue
            template = self.tokens_of(pattern)
            if not self.same_lead(template, tokens):                        # rule 2
                continue
            name = bare(p['name'])
            key = (len(p['matches']), sum(1 for token in template if token == self.parameter), -self.types[name][0])
            if best is None or key > best[0]:
                best = (key, name, template, pattern)
        if best is None or best[0][0] / len(tokens) < self.tau:             # rule 3, as Drain writes it
            return self.found(self.symbols(tokens)), False, []
        _key, name, template, pattern = best
        new = [a if a == b else self.parameter for a, b in zip(template, tokens)]
        before = self.node.frequency(name)
        learned = self.settle(name, pattern, self.symbols(new))
        self.last = {'old': template, 'new': new, 'changed': new != template, 'lines before': before, 'kind': self.kind}
        return learned, True, [(i, i + 1) for i, token in enumerate(new) if token == self.parameter]

    def template(self, name):
        return self.tokens_of(super().template(name))

    def gaps(self, tokens, name):
        return [(i, i + 1) for i, token in enumerate(self.template(name)) if token == self.parameter]
