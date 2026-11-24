"""Round 2 (24 Nov 2026): whole sequences at node_0, one VAR per gap, and what follows from them.

    ./run.sh examples/sequences.py            all examples
    ./run.sh examples/sequences.py 8 9        examples 8 and 9 only
    ./run.sh examples/sequences.py --digest   one sha1 over everything printed

Prints examples/report_sequences.txt. In-process, on KATO's own matcher, Pattern and scoring
code (hpcrd/kato_node.py). Set KATO_API to put every node in a running KATO service instead.
"""
import hashlib
import io
import json
import sys
from contextlib import redirect_stdout

from examples.worked_examples import BASE, STREAM, T1, T2, T3A, T4, T5, head, sub, table
from hpcrd.alignment import read
from hpcrd.kato_node import Node
from hpcrd.modeler import VAR, Modeler, Settings, pattern_name
from hpcrd.show import dump_node, print_sequence, seq, whole_reading_line

CLOSE = "the cat says meow . the dog says woof . the cat says meow . the dog says woof ."
CITIES = ("show flights from boston to denver . show flights from dallas to denver . "
          "show flights from new york to denver . show flights from los angeles to denver . "
          "show flights from new york to denver . show flights from new york city to denver . "
          "show flights from new jersey to denver .")
PARTY = ("book a table for two quiet adults at seven . book a table for four hungry diners at seven . "
         "book a table for two hungry diners at seven . book a table for four quiet adults at seven .")
MIXED = ("show flights from boston to denver . show flights from dallas to denver . "
         "show flights from san francisco to denver . play yesterday . play imagine . "
         "play the long and winding road . show me flights from boston to denver .")

SEQUENCE = dict(span='sequence', markers=('.',), recall_threshold=0.5, unexplained='break')
GAP = dict(SEQUENCE, slots='gap', values='sequence')


def settings_line(s):
    extra = ''.join(f" {name}={getattr(s, name)}" for name in ('fold', 'inside', 'topdown')
                    if getattr(s, name) != Settings.__dataclass_fields__[name].default)
    if s.topdown:
        extra += f" rule_threshold={s.rule_threshold}"
    print(f"settings: span={s.span} markers={list(s.markers)} recall_threshold={s.recall_threshold} "
          f"slots={s.slots} values={s.values} naming={s.naming} unexplained={s.unexplained}{extra}")


def run(text, show=True, readings=True, only=None, **kw):
    """Whole sequences: feed the text, print each sequence as it is read."""
    m = Modeler(Settings(**kw))
    if show:
        settings_line(m.s)
    count = 0
    for token in text.split():
        step = m.feed(token)
        if step['stm']:
            count += 1
            if show and (only is None or count in only):
                print_sequence(step, m, readings)
    m.finish()
    return m


def quiet(text, **kw):
    m = Modeler(Settings(**kw))
    for token in text.split():
        m.feed(token)
    m.finish()
    return m


def nodes(m, node0=True):
    if node0:
        dump_node(m.node0, 'node_0')
    dump_node(m.node1a, 'node_1a')
    dump_node(m.node1b, 'node_1b', m.node1a)
    dump_node(m.node2a, 'node_2a')
    dump_node(m.node2b, 'node_2b', m.node1a)
    if m.node1t is not None:
        dump_node(m.node1t, 'node_1t')


def sizes(m):
    rules = list(m.node1b.patterns.values())
    return {
        'node_0 patterns': len(m.node0.patterns),
        'node_0 symbols stored': sum(len(e['pattern_data']) for e in m.node0.patterns.values()),
        'node_0 predictions asked': m.node0.predicts,
        "module's own records": len(m.learned_at),
        'node_1a chunks': len(m.node1a.patterns),
        'longest chunk': max((len(e['pattern_data']) for e in m.node1a.patterns.values()), default=0),
        'node_1b rules': len(rules),
        'rules seen again': sum(1 for e in rules if e['frequency'] > 1),
        'VARs': m.var_count,
        'node_2b patterns': len(m.node2b.patterns),
    }


def rules_of(m, indent='      '):
    for e in sorted(m.node1b.patterns.values(), key=lambda e: (-e['frequency'], e['name'])):
        print(f"{indent}f={e['frequency']}  " + seq([event[0] for event in e['pattern_data']], m.node1a))


# ----------------------------------------------------------------------------------------------
def example7():
    head("EXAMPLE 7  Whole sequences at node_0 instead of rolling windows")
    print("node_0 learns each sentence as one pattern. The module asks for predictions on the whole sentence")
    print("before node_0 learns it, so nothing echoes. Two whole sentences line up end to end, so what stands")
    print("before the first match or after the last one is a gap like any other.")
    sub("7.1  text 1, sentence by sentence")
    m = run(T1, **SEQUENCE)
    print()
    nodes(m)

    sub("7.2  the same texts three ways (window 7, recall_threshold 0.5, one VAR per position)")
    for name, text in (('text 1', T1), ('text 2', T2), ('text 4', T4), ('text 5', T5)):
        print(f"\n{name} ({text.count(' .')} sentences, {len(text.split())} tokens)")
        rows = [('per window', sizes(quiet(text, **BASE, unexplained='break'))),
                ('stitched', sizes(quiet(text, **BASE, **STREAM, unexplained='break'))),
                ('whole', sizes(quiet(text, **SEQUENCE)))]
        table(rows, [r[0] for r in rows])

    sub("7.3  two instances closer together than a window (section 9.2 of the first write-up)")
    print(f"text: {CLOSE}")
    print("rolling windows of 7 found no rule here: the earlier sentence was still an echo.")
    m = run(CLOSE, readings=False, only=(2, 4), **SEQUENCE)
    print()
    nodes(m)

    sub("7.4  a chunk longer than any window: text 2")
    m = quiet(T2, **SEQUENCE)
    nodes(m, node0=False)


def example8():
    head("EXAMPLE 8  One VAR per gap, its value kept whole as a sequence of tokens")
    print("slots='gap': a run of positions that vary is one VAR, whatever its length.")
    print("values='sequence': node_2b holds the value as [VAR, token, token, ...], so KATO can match inside it.")
    sub("8.1  values of one, two and three tokens in the same slot")
    m = run(CITIES, only=(2, 3, 5, 6), **GAP)
    print()
    nodes(m, node0=False)

    sub("8.2  node_1b's own prediction binds a value of any length to the VAR")
    probe = "PTRN|ac5190 new york city PTRN|c97f0b".split()
    probe[0] = pattern_name([[t] for t in "show flights from".split()])
    probe[-1] = pattern_name([[t] for t in "to denver .".split()])
    out = m.node1b.predict([[x] for x in probe])
    p = sorted(out['predictions'], key=lambda p: p['name'])[0]
    print("  observe at node_1b: " + seq(probe, m.node1a))
    for key in ('matches', 'missing', 'extras'):
        print(f"      {key:8s} {json.dumps([[x[:11] if x.startswith('PTRN|') else x for x in e] for e in p[key]] if key != 'matches' else [x[:11] if x.startswith('PTRN|') else x for x in p[key]])}")
    r = read(p, [[x] for x in probe], whole=True)
    gap = [i for i, rel in enumerate(r.relation) if rel[0] in 'SU']
    print(f"      one gap: {len(gap)} extras against 1 missing -> [{r.pattern[1]}] <- [{' '.join(probe[gap[0]:gap[-1] + 1])}]")

    sub("8.3  the sketch text of the brief: one VAR per position against one VAR per gap (whole sentences)")
    for name, kw in (('one VAR per position', dict(SEQUENCE)), ('one VAR per gap', dict(GAP))):
        m = quiet(T3A, **kw)
        print(f"  {name}: {len(m.node1b.patterns)} rule(s), {m.var_count} VARs, {len(m.node2b.patterns)} node_2b patterns")
        rules_of(m)
    print("  With one VAR per gap, [two quiet adults] is one value. Nothing in the text says it is three.")

    sub("8.4  the flights text of Example 3 (a value of another length), per position against per gap")
    from examples.worked_examples import T3
    for name, kw in (('one VAR per position', dict(SEQUENCE)), ('one VAR per gap', dict(GAP))):
        m = quiet(T3, **kw)
        print(f"  {name}: {len(m.node1b.patterns)} rule(s), {m.var_count} VARs")
        rules_of(m)


def example9():
    head("EXAMPLE 9  Start long, refine inside: what a VAR's earlier values say about a new value")
    print("inside=True. Before a value is learned, node_2b is asked for predictions on [VAR, token, ...].")
    print("Its ensemble lines the value up with the VAR's earlier values. The rule that holds the VAR is not touched.")
    sub("9.1  units, and values that share a part")
    m = run(CITIES, readings=False, only=(3, 5, 6, 7), **GAP, inside=True)
    print()
    dump_node(m.node1a, 'node_1a')
    dump_node(m.node1b, 'node_1b', m.node1a)
    dump_node(m.node2b, 'node_2b', m.node1a)

    sub("9.2  parts that recombine: one VAR becomes two inside, the rule stays one")
    print(f"text: {PARTY}")
    m = run(PARTY, readings=False, only=(2, 3, 4), **GAP, inside=True)
    print()
    dump_node(m.node1b, 'node_1b', m.node1a)
    dump_node(m.node2b, 'node_2b', m.node1a)
    seen = sorted(' '.join(event[0] for event in e['pattern_data'][1:]) for e in m.node2b.patterns.values()
                  if e['pattern_data'][0][0] == 'VAR|1' and not e['pattern_data'][1][0].startswith('PTRN|'))
    print(f"  seen whole: {seen}")

    sub("9.3  parts that never recombine stay one value: the sketch text")
    m = run(T3A, readings=False, only=(4,), **GAP, inside=True)
    print(f"  inner rules: {sum(1 for e in m.node2b.patterns.values() if len(e['pattern_data']) == 2 and e['pattern_data'][1][0].startswith('PTRN|'))}")


def example10():
    head("EXAMPLE 10  A learned rule reads a new sequence (top-down), before node_0 is asked")
    print("topdown=True. node_1t holds each rule with its chunks spelled out. A rule fits a sequence when every")
    print("constant is matched, in order, and each stretch that is left stands against exactly one VAR.")
    print(f"text: {MIXED}")
    m = run(MIXED, only=(3, 6, 7), **GAP, topdown=True, rule_threshold=0.3)
    print()
    nodes(m, node0=False)
    print("\n  why node_0 alone cannot bind the five-token value at recall_threshold 0.5:")
    print("      [play the long and winding road .] against [play imagine .]: 2*2/(7+3) = 0.40, not recalled")
    print("      against the rule [play VAR|2 .] in node_1t:               2*2/(7+3) = 0.40, recalled at rule_threshold 0.3")
    print("      the rule needs no earlier sentence of the same length; the sentence needs one that is close.")


def example11():
    head("EXAMPLE 11  recall_threshold with whole sentences, and which readings decide")
    print("With one symbol per event KATO's similarity is 2 * matches / (pattern length + observed length).")
    print("For two 7-token sentences: one token differs 0.857, two differ 0.714, three differ 0.571.")
    print("fold='all': every recalled sentence decides what is constant. fold='nearest': only the most similar")
    print("sentences that differ decide (exact repeats with them); the others still fill gaps with alternatives.")
    for name, text in (('text 4', T4), ('text 5', T5)):
        sub(f"{name}: rules / rules seen again / VARs")
        print("  recall_threshold     " + '  '.join(f"{th:>10}" for th in (0.1, 0.3, 0.5, 0.7, 0.9)))
        kept = {}
        for fold in ('all', 'nearest'):
            cells = []
            for th in (0.1, 0.3, 0.5, 0.7, 0.9):
                m = quiet(text, **{**GAP, 'recall_threshold': th, 'fold': fold})
                rules = list(m.node1b.patterns.values())
                cells.append(f"{len(rules)} / {sum(1 for e in rules if e['frequency'] > 1)} / {m.var_count}")
                kept[(fold, th)] = m
            print(f"  fold={fold:<16s}" + '  '.join(f"{c:>10}" for c in cells))
        for fold, th in (('all', 0.1), ('all', 0.7), ('nearest', 0.1)):
            print(f"  rules at fold={fold}, recall_threshold={th}:")
            rules_of(kept[(fold, th)])


def example12():
    head("EXAMPLE 12  node_2b: three ways to hold a VAR's values")
    print("P  one pattern per VAR and value, a value of several tokens by its node_1a name   (the first write-up)")
    print("S  one pattern per VAR and value, the value as its own tokens                       [VAR|1] [new] [york]")
    print("K  one pattern per combination: the values seen together in one ensemble, sorted    [VAR|1] [a1] [a2] [a3]")

    def build(text):
        m = quiet(text, **GAP)
        chunks, P, S, K = Node('names'), Node('P'), Node('S'), Node('K')

        def symbol(value):
            return value[0] if len(value) == 1 else chunks.learn([[t] for t in value])

        for step in m.trace:
            for result in step['stretches']:
                for part in result['parts']:
                    for var, value, _status, alts in part['bindings']:
                        value = tuple(value)
                        S.learn([[var]] + [[t] for t in value])
                        P.learn([[var], [symbol(value)]])
                        for alt in sorted(alts):
                            if not S.frequency(pattern_name([[var]] + [[t] for t in alt])):
                                S.learn([[var]] + [[t] for t in alt])
                                P.learn([[var], [symbol(alt)]])
                        together = sorted({symbol(value)} | {symbol(alt) for alt in alts})
                        K.learn([[var]] + [[x] for x in together])
        return m, chunks, P, S, K

    sub("12.1  the cities text (7 sentences, 6 instances of one rule)")
    m, chunks, P, S, K = build(CITIES)
    for name, node in (('P', P), ('S', S), ('K', K)):
        stored = sum(len(e['pattern_data']) for e in node.patterns.values())
        print(f"  {name}: {len(node.patterns)} patterns, {stored} symbols stored, {node.learns} learns, "
              f"highest frequency {max(e['frequency'] for e in node.patterns.values())}")
    dump_node(S, 'S', None)
    dump_node(K, 'K', chunks)

    sub("12.2  three questions, one KATO call each where the layout allows it")
    york = pattern_name([[t] for t in ('new', 'york')])
    print("  is [new york] a value of VAR|1?")
    print(f"      P  frequency of [VAR|1] [{york[:11]}] = {P.frequency(pattern_name([['VAR|1'], [york]]))}   (by name; the chunk's name is the hash of its tokens)")
    print(f"      S  frequency of [VAR|1] [new] [york]  = {S.frequency(pattern_name([['VAR|1'], ['new'], ['york']]))}   (by name)")
    held = [p for p in K.predict([[york]])['predictions']]
    print(f"      K  no pattern has that name; observe [{york[:11]}] returns {len(held)} combinations that hold it")
    print("  which values are like [new jersey]?   observe [VAR|1] [new] [jersey]")
    asked = [['VAR|1'], ['new'], ['jersey']]
    out = S.predict(asked)
    for p in sorted(out['predictions'], key=lambda p: (-len(p['matches']), p['name'])):
        if len(p['matches']) > 1:
            print("      S  " + whole_reading_line(read(p, asked, whole=True), width=26))
    print("      P  a name is opaque to matching: only the VAR symbol matches, for every value alike")
    print("      K  the same: a combination is a list of names")
    print("  how often did each value stand in the slot?")
    counted = sorted(((e['frequency'], ' '.join(ev[0] for ev in e['pattern_data'][1:])) for e in S.patterns.values()), reverse=True)
    print("      S  " + ', '.join(f"{v} x{f}" for f, v in counted))
    print("      K  " + ', '.join(f"a combination of {len(e['pattern_data']) - 1} x{e['frequency']}"
                                 for e in sorted(K.patterns.values(), key=lambda e: (len(e['pattern_data']), e['name'])))
          + "   (frequency counts combinations, not values)")

    sub("12.3  the same six instances arriving in another order (the VAR held fixed)")
    instances = [tuple(value) for step in m.trace for result in step['stretches']
                 for part in result['parts'] for _var, value, _status, _alts in part['bindings']]

    def replay(order):
        S_, K_, seen = Node('S'), Node('K'), set()
        for value in order:
            S_.learn([['VAR|1']] + [[t] for t in value])
            seen.add(value[0] if len(value) == 1 else pattern_name([[t] for t in value]))
            K_.learn([['VAR|1']] + [[x] for x in sorted(seen)])
        return S_, K_

    (s1, k1), (s2, k2) = replay(instances), replay(list(reversed(instances)))
    print(f"  S: {len(s1.patterns)} patterns one way, {len(s2.patterns)} the other, {len(set(s1.patterns) & set(s2.patterns))} the same")
    print(f"  K: {len(k1.patterns)} patterns one way, {len(k2.patterns)} the other, {len(set(k1.patterns) & set(k2.patterns))} the same")
    print("  (the VAR is held fixed here. Which VAR ids and rules a text gives still depends on the order it arrives in.)")

    sub("12.4  growth: one more instance of a rule")
    print("  S and P add at most one pattern (a new value) or raise one frequency (a known value).")
    print("  K adds one pattern per new combination, and a combination holds every value seen so far in the slot:")
    for e in sorted(K.patterns.values(), key=lambda e: (len(e['pattern_data']), e['name'])):
        print(f"      {len(e['pattern_data']) - 1} values  f={e['frequency']}")


EXAMPLES = {'7': example7, '8': example8, '9': example9, '10': example10, '11': example11, '12': example12}

if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    chosen = args or list(EXAMPLES)
    if '--digest' in sys.argv:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            for key in chosen:
                EXAMPLES[key]()
        print(hashlib.sha1(buffer.getvalue().encode()).hexdigest(), len(buffer.getvalue().splitlines()), 'lines')
    else:
        for key in chosen:
            EXAMPLES[key]()
