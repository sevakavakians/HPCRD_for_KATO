"""Worked examples for the rules experiment. Prints everything the write-up quotes.

    ./run.sh examples/worked_examples.py            all examples
    ./run.sh examples/worked_examples.py 3 5        examples 3 and 5 only
    ./run.sh examples/worked_examples.py --digest   one sha1 over everything printed

In-process, on KATO's own matcher, Pattern and scoring code (see kato_node.py).
Nothing here went through KATO's API.
"""
import hashlib
import io
import json
import sys
from contextlib import redirect_stdout

from hpcrd.alignment import flat
from hpcrd.modeler import VAR, Modeler, Settings, pattern_name
from hpcrd.show import dump_node, print_result, print_step, seq, spell, unravel

BASE = dict(window=7, recall_threshold=0.5)
STREAM = dict(span='stream', markers=('.',))

T1 = "the cat sat on the mat . the dog sat on the mat . the bird sat on the mat ."
T2 = ("the old cat sat on the mat by the door . the old dog sat on the mat by the door . "
      "the old bird sat on the mat by the door .")
T3 = ("show flights from boston to denver . show flights from dallas to denver . "
      "show me flights from boston to denver . show flights from new york to denver . "
      "show flights from los angeles to denver .")
T3A = ("please book a table for two quiet adults at seven tonight . "
       "kindly book a table for six hungry diners at seven today . "
       "please book a table for four tired guests at uh seven tonight . "
       "kindly book a table for two quiet adults at seven today .")
T4 = ("the cat sat on the mat . the dog sat on the mat . the cat sat on the rug . the dog sat on the rug . "
      "when the cat is happy it purrs . when the dog is happy it barks . "
      "when the cat is happy it purrs . when the dog is happy it barks .")
T5 = ("the cat sat on the mat . the dog sat on the mat . "
      "we saw the cat near the old barn . we saw the dog near the old barn . "
      "the cat sat by a warm fire . the dog sat by a warm fire . "
      "the bird sat on the mat . we saw the bird near the old barn . the bird sat by a warm fire .")
T5B = ("the big dog sat on the mat . the small cat sat on the mat . the big cat sat on the mat . "
       "we saw the big dog near the old barn . we saw the small cat near the old barn . "
       "we saw the small dog near the old barn .")


def head(title):
    print()
    print('=' * 100)
    print(title)
    print('=' * 100)


def sub(title):
    print()
    print('--- ' + title)


def settings_line(s):
    print(f"settings: window={s.window} recall_threshold={s.recall_threshold} span={s.span} "
          f"markers={list(s.markers)} naming={s.naming} slots={s.slots} unexplained={s.unexplained} "
          f"mixed={s.mixed} min_support={s.min_support} edge_vars={s.edge_vars}")


def run(text, show='all', readings=False, quiet=False, **kw):
    s = Settings(**{**BASE, **kw})
    m = Modeler(s)
    if not quiet:
        settings_line(s)

    def stretch(res):
        a, b = res['stretch']
        if quiet:
            return
        print(f"stretch {a}..{b - 1}  {' '.join(m.tokens[a:b])}")
        print_result(res, m, m.tokens[a:b])

    for token in text.split():
        step = m.feed(token)
        if s.span == 'window':
            if not quiet and (show == 'all' or step['t'] in show) and (step['parts'] or step['t'] in (show if show != 'all' else ())):
                print_step(step, m, readings=readings)
        else:
            for res in step['stretches']:
                stretch(res)
    for res in m.finish():
        stretch(res)
    return m


def counts(m):
    rules = [e for e in m.node1b.patterns.values()]
    longest = max((len(e['pattern_data']) for e in m.node1a.patterns.values()), default=0)
    return {
        'node_0 patterns': len(m.node0.patterns),
        'node_1a chunks': len(m.node1a.patterns),
        'node_1a learns': m.node1a.learns,
        'longest chunk': longest,
        'node_1b rules': len(rules),
        'node_1b learns': m.node1b.learns,
        'rules seen again': sum(1 for e in rules if e['frequency'] > 1),
        'VARs': m.var_count,
        'node_2a patterns': len(m.node2a.patterns),
        'node_2b patterns': len(m.node2b.patterns),
    }


def table(rows, columns):
    keys = list(rows[0][1].keys())
    width = max(len(k) for k in keys)
    print(' ' * width + '  ' + '  '.join(f"{c:>12s}" for c in columns))
    for k in keys:
        print(f"{k:<{width}s}  " + '  '.join(f"{r[1][k]:>12}" for r in rows))


def all_nodes(m, node0=False):
    if node0:
        dump_node(m.node0, 'node_0')
    else:
        print(f"  node_0: {len(m.node0.patterns)} patterns, {m.node0.learns} learns (one window per token from t={m.s.window - 1})")
    dump_node(m.node1a, 'node_1a')
    dump_node(m.node1b, 'node_1b', m.node1a)
    dump_node(m.node2a, 'node_2a')
    dump_node(m.node2b, 'node_2b', m.node1a)


def raw_fields(p, keys=('matches', 'missing', 'extras', 'past', 'present', 'future')):
    for key in keys:
        print(f"          {key:8s} {json.dumps(p[key])}")


# ----------------------------------------------------------------------------------------------
def example1():
    head("EXAMPLE 1  One slot, one window at a time (the description to the letter)")
    print("text:", T1)
    s = Settings(**BASE)
    settings_line(s)
    m = Modeler(s)
    steps = [m.feed(token) for token in T1.split()]

    sub("t=6: the first full window. Nothing has been learned, so the ensemble is empty.")
    st = steps[6]
    print(f"t=6   STM       {' '.join(st['stm'])}")
    print(f"      ensemble  {st['ensemble']} predictions.  node_0 learns this window as {st['learned'][:11]}")

    sub("t=13: what node_0 returns, and what the module holds out")
    st = steps[13]
    print(f"t=13  STM       {' '.join(st['stm'])}")
    held = {r.name for r, _ in st['readings']}
    for p in sorted(st['raw'], key=lambda p: m.learned_at[p['name']][0]):
        learned = m.learned_at[p['name']]
        what = 'READ' if p['name'] in held else 'echo: shares tokens with the STM'
        print(f"        {p['name'][:6]}  {' '.join(x[0] for x in p['past'] + p['present'] + p['future']):26s} "
              f"frequency {p['frequency']}  similarity {p['similarity']:.3f}  learned at t={learned[0]:<2d}  {what}")
    sub("t=13: the one prediction that is read, as KATO returns it")
    p = [p for p in st['raw'] if p['name'] in held][0]
    raw_fields(p)
    sub("t=13: what the module does with it")
    print_step(st, m, readings=True)

    sub("t=14: the same slot at the window's edge. The pattern's side is in `past`, not in `missing`.")
    st = steps[14]
    print(f"t=14  STM       {' '.join(st['stm'])}")
    p = [p for p in st['raw'] if p['name'].startswith('1eaaea')][0]
    print(f"        1eaaea  {' '.join(x[0] for x in p['past'] + p['present'] + p['future'])}")
    raw_fields(p)
    print_result(st, m, st['stm'])

    sub("t=20: the rule is recognised. node_1b's own prediction for the probe:")
    st = steps[20]
    part = st['parts'][0]
    print(f"t=20  STM       {' '.join(st['stm'])}")
    print('      probe     ' + seq(part['probe'], m.node1a))
    rec = part['recognition']
    print(f"        {rec['name'][:6]}  frequency {rec['frequency']}  similarity {rec['similarity']:.3f}")
    raw_fields(rec)
    print_result(st, m, st['stm'])

    sub("every step that taught a node above node_0")
    for st in steps:
        for part in st['parts']:
            rule = (seq(part['sequence'], m.node1a) + ('   (recognised)' if part['recognised'] else '')) if part['rule'] \
                else 'chunk only: ' + ', '.join('[' + ' '.join(c[1]) + ']' for c in part['chunks'])
            print(f"t={st['t']:<3d} {' '.join(st['stm']):28s} {rule}")

    sub("what every node holds at the end")
    all_nodes(m, node0=True)

    sub("the same text with edge_vars=True (an extra that lines up with `past` or `future` is a variable too)")
    m2 = run(T1, quiet=True, edge_vars=True)
    for st in m2.trace:
        for part in st['parts']:
            if part['rule']:
                print(f"t={st['t']:<3d} {' '.join(st['stm']):28s} {seq(part['sequence'], m2.node1a)}"
                      + ('   (recognised)' if part['recognised'] else ''))
    table([('strict', counts(m)), ('edge_vars', counts(m2))], ['strict', 'edge_vars'])
    return m


def example2():
    head("EXAMPLE 2  The same text stitched along the stream, and a chunk longer than the window")
    print("text:", T1)
    m_s = run(T1, **STREAM)
    sub("what every node holds at the end (stitched)")
    all_nodes(m_s)
    sub("one window at a time against stitched, same text, same settings otherwise")
    m_w = run(T1, quiet=True)
    table([('w', counts(m_w)), ('s', counts(m_s))], ['per window', 'stitched'])

    sub("a constant stretch of 8 tokens, window of 7")
    print("text:", T2)
    m2 = run(T2, **STREAM)
    all_nodes(m2)
    m2w = run(T2, quiet=True)
    table([('w', counts(m2w)), ('s', counts(m2))], ['per window', 'stitched'])
    sub("node_0 already knew the windows inside the long chunk: their frequency went to 2 and 3")
    for name in m2.node0.learn_order:
        entry = m2.node0.patterns[name]
        if entry['frequency'] > 1:
            print(f"    PTRN|{name[:6]}  f={entry['frequency']}  {' '.join(e[0] for e in entry['pattern_data'])}")
    return m_s


def example3():
    head("EXAMPLE 3  The sketch in the request, run; then noise, a value of another length, slots side by side")
    sub("(a) the layout of the sketch: VAR, chunk, VAR VAR VAR, chunk with noise inside it, VAR")
    print("text:", T3A)
    m0 = run(T3A, **STREAM, slots='position', unexplained='drop')
    all_nodes(m0)
    print()
    print("text:", T3)
    sub("(b) to the letter: one VAR per aligned position, everything else removed as noise")
    ma = run(T3, **STREAM, slots='position', unexplained='drop')
    all_nodes(ma)
    sub("(c) only an insertion is removed; a token nothing accounts for ends the part")
    mb = run(T3, **STREAM, slots='position', unexplained='break')
    all_nodes(mb)
    sub("(d) one VAR per gap: a value may be longer or shorter than the one it stands against")
    mc = run(T3, **STREAM, slots='gap', unexplained='break')
    all_nodes(mc)
    table([('a', counts(ma)), ('b', counts(mb)), ('c', counts(mc))], ['(b) letter', '(c) break', '(d) gap'])
    return mc


def example4():
    head("EXAMPLE 4  Two slots: how general a rule gets, and values that go together")
    print("text:", T4)
    m = run(T4, **STREAM, unexplained='break')
    all_nodes(m)

    sub("the dial: node_0's recall_threshold, and the two other settings that decide what varies")
    variants = [
        ('recall_threshold=0.1 (KATO default)', dict(recall_threshold=0.1)),
        ('recall_threshold=0.3', dict(recall_threshold=0.3)),
        ('recall_threshold=0.5', dict()),
        ('recall_threshold=0.7', dict(recall_threshold=0.7)),
        ('recall_threshold=0.9', dict(recall_threshold=0.9)),
        ('0.5, mixed=const', dict(mixed='const')),
        ('0.5, min_support=2', dict(min_support=2)),
    ]
    for label, kw in variants:
        mv = run(T4, quiet=True, **STREAM, unexplained='break', **kw)
        print(f"  {label}:  {len(mv.node1b.patterns)} rules, {mv.var_count} VARs")
        for entry in sorted(mv.node1b.patterns.values(), key=lambda e: mv.node1b.learn_order.index(e['name'])):
            print(f"      f={entry['frequency']}  {seq([e[0] for e in entry['pattern_data']], mv.node1a)}")

    sub("values that go together: the joint values node_2b holds for each rule with two slots")
    for entry in sorted(m.node1b.patterns.values(), key=lambda e: m.node1b.learn_order.index(e['name'])):
        symbols = [e[0] for e in entry['pattern_data']]
        vars_ = [x for x in symbols if x.startswith(VAR)]
        if len(vars_) < 2:
            continue
        print(f"  {seq(symbols, m.node1a)}")
        rows, values = [], {v: set() for v in vars_}
        for pat in m.node2b.patterns.values():
            row = [e[0] for e in pat['pattern_data']]
            if len(row) == 2 * len(vars_) and row[0::2] == vars_:
                rows.append((row[1::2], pat['frequency']))
        for pat in m.node2b.patterns.values():
            row = [e[0] for e in pat['pattern_data']]
            if len(row) == 2 and row[0] in values:
                values[row[0]].add(row[1])
        for vals, f in sorted(rows):
            print(f"      {' + '.join(vals):16s} seen together x{f}")
        possible = 1
        for v in vars_:
            possible *= len(values[v])
        print(f"      {len(rows)} of {possible} possible combinations seen "
              f"({' x '.join(str(len(values[v])) + ' values of ' + v for v in vars_)})")

    sub("asking node_2b: given the value of the first slot, what stands in the second?")
    for entry in sorted(m.node1b.patterns.values(), key=lambda e: m.node1b.learn_order.index(e['name'])):
        vars_ = [x[0] for x in entry['pattern_data'] if x[0].startswith(VAR)]
        if len(vars_) != 2:
            continue
        v1, v2 = vars_
        query = [[v1], ['cat'], [v2]]
        out = m.node2b.predict(query)
        full = [p for p in out['predictions'] if len(p['matches']) == 3]
        print(f"  observe {seq([q[0] for q in query])} at node_2b: {len(out['predictions'])} predictions, "
              f"{len(full)} match all three symbols")
        for p in sorted(full, key=lambda p: p['name']):
            print(f"      {p['name'][:6]}  frequency {p['frequency']}  similarity {p['similarity']:.3f}  "
                  f"present {json.dumps(p['present'])}  future {json.dumps(p['future'])}")
        print("      future_potentials:", json.dumps([{k: (round(v, 3) if isinstance(v, float) else v) for k, v in fp.items()}
                                                       for fp in out['future_potentials']]))
    return m


def example5():
    head("EXAMPLE 5  Three ways to give a slot its VAR id")
    print("text:", T5)
    models = {}
    for naming in ('rule', 'neighbours', 'values'):
        sub(f"naming={naming}")
        models[naming] = m = run(T5, quiet=True, **STREAM, unexplained='break', naming=naming)
        for st in m.trace:
            for res in st.get('stretches', []):
                a, b = res['stretch']
                for part in res['parts']:
                    if part['rule']:
                        print(f"  {' '.join(m.tokens[a:b]):38s} {seq(part['sequence'], m.node1a)}"
                              + ('   (new ' + ', '.join(part['new_vars']) + ')' if part['new_vars'] else ''))
        print(f"  node_1b: {len(m.node1b.patterns)} rules.  VARs: {m.var_count}")
        values = {}
        for pat in m.node2b.patterns.values():
            row = [e[0] for e in pat['pattern_data']]
            if len(row) == 2 and row[0].startswith(VAR):
                values.setdefault(row[0], []).append(f"{spell(row[1], m.node1a)} x{pat['frequency']}")
        for var in sorted(values, key=lambda v: int(v[len(VAR):])):
            print(f"      {var}: {', '.join(sorted(values[var]))}")
        if naming == 'neighbours':
            for key, var in sorted(m.frames.items(), key=lambda kv: int(kv[1][len(VAR):])):
                print(f"      {var} is the slot between '{key[0]}' and '{key[1]}'")
    table([(n, counts(models[n])) for n in models], list(models))

    sub("VARs that share values, found by asking node_2b (naming=rule): observe one value, read which VARs hold it")
    m = models['rule']
    for value in ('cat', 'bird'):
        out = m.node2b.predict([[value]])
        holders = sorted((flat(p['past'] + p['present'] + p['future'])[0], p['frequency']) for p in out['predictions']
                         if len(flat(p['past'] + p['present'] + p['future'])) == 2)
        print(f"  observe [{value}] at node_2b -> " + ', '.join(f"{v} (x{f})" for v, f in holders))
        if value == 'cat':
            p = sorted(out['predictions'], key=lambda p: p['name'])[0]
            print(f"      one of them, as KATO returns it: past {json.dumps(p['past'])} present {json.dumps(p['present'])} "
                  f"future {json.dumps(p['future'])} similarity {p['similarity']:.3f}")

    sub("VARs side by side that recur across rules")
    print("text:", T5B)
    for naming in ('rule', 'values'):
        m = run(T5B, quiet=True, **STREAM, unexplained='break', naming=naming)
        print(f"  naming={naming}: {m.var_count} VARs")
        for entry in sorted(m.node1b.patterns.values(), key=lambda e: m.node1b.learn_order.index(e['name'])):
            print(f"      node_1b f={entry['frequency']}  {seq([e[0] for e in entry['pattern_data']], m.node1a)}")
        for pat in sorted(m.node2b.patterns.values(), key=lambda e: e['name']):
            row = [e[0] for e in pat['pattern_data']]
            if all(x.startswith(VAR) for x in row):
                print(f"      node_2b f={pat['frequency']}  {seq(row)}   (VARs side by side)")
    return models


def example6():
    head("EXAMPLE 6  Using what was learned")
    print("text:", T4)
    m = run(T4, quiet=True, **STREAM, unexplained='break')
    sat = [e for e in m.node1b.patterns.values() if e['frequency'] == 2][0]
    when = [e for e in m.node1b.patterns.values() if e['frequency'] == 3][0]
    for name, entry in (('sat', sat), ('when', when)):
        print(f"  rule '{name}': PTRN|{entry['name'][:6]} f={entry['frequency']}  "
              f"{seq([e[0] for e in entry['pattern_data']], m.node1a)}")

    sub("(a) a new sentence with a value never seen in the slot")
    before = len(m.trace)
    for token in "the bird sat on the rug .".split():
        m.feed(token)
    for token in "the cat sat on the mat .".split():     # one more sentence, so the window moves past the first
        step = m.feed(token)
        for res in step['stretches']:
            a, b = res['stretch']
            print(f"stretch {a}..{b - 1}  {' '.join(m.tokens[a:b])}")
            print_result(res, m, m.tokens[a:b])

    sub("(b) which values a VAR accepts: observe the VAR alone at node_2b")
    symbols = [e[0] for e in sat['pattern_data']]
    v1, v2 = [x for x in symbols if x.startswith(VAR)]
    out = m.node2b.predict([[v1]])
    pairs = [p for p in out['predictions'] if len(flat(p['past'] + p['present'] + p['future'])) == 2]
    print(f"  observe [{v1}] at node_2b: {len(out['predictions'])} predictions, {len(pairs)} of them a VAR with one value")
    for p in sorted(pairs, key=lambda p: (-p['frequency'], p['name'])):
        print(f"      {p['name'][:6]}  frequency {p['frequency']}  present {json.dumps(p['present'])}  future {json.dumps(p['future'])}")

    sub("(c) what the 'sat' rule licenses, against what was seen")
    def vals(var):
        return sorted(flat(p['future'])[0] for p in m.node2b.predict([[var]])['predictions']
                      if len(flat(p['past'] + p['present'] + p['future'])) == 2)
    for entry in (sat, when):
        symbols = [e[0] for e in entry['pattern_data']]
        va, vb = [x for x in symbols if x.startswith(VAR)]
        for a in vals(va):
            for b in vals(vb):
                f = m.node2b.frequency(pattern_name([[va], [a], [vb], [b]]))
                words = []
                for x in symbols:
                    words += [a] if x == va else [b] if x == vb else unravel(x, m.node1a)
                print(f"      {' '.join(words):36s} {'seen together x' + str(f) if f else 'never seen: the rule allows it, no observation backs it'}")

    sub("(d) a sentence that shares nothing with what was learned")
    novel = "birds fly south in winter ."
    out = m.node0.predict([[t] for t in novel.split()])
    print(f"  node_0, asked about '{novel}' on its own: {len(out['predictions'])} predictions "
          f"(recall_threshold {m.node0.recall_threshold})")
    for token in novel.split() + "the cat sat on the mat .".split():
        step = m.feed(token)
        for res in step['stretches']:
            a, b = res['stretch']
            if m.tokens[a] == 'birds':
                print(f"stretch {a}..{b - 1}  {' '.join(m.tokens[a:b])}")
                print_result(res, m, m.tokens[a:b])

    sub("(e) every name unravels: a rule and its values give back the sentence")
    symbols = [e[0] for e in when['pattern_data']]
    va, vb = [x for x in symbols if x.startswith(VAR)]
    print(f"  node_1b  PTRN|{when['name'][:6]} = {seq(symbols)}")
    for x in symbols:
        if x.startswith('PTRN|'):
            print(f"      {x[:11]} -> node_1a -> {' '.join(unravel(x, m.node1a))}")
    words = []
    for x in symbols:
        words += ['cat'] if x == va else ['purrs'] if x == vb else unravel(x, m.node1a)
    print(f"      with {va}=cat and {vb}=purrs: {' '.join(words)}")
    return m


def limits():
    head("LIMITS  Two things the window cannot see")
    text = "the cat says meow . the dog says woof . the cat says meow . the dog says woof ."
    sub("an analog closer than one window: five-token sentences, window of 7")
    print("text:", text)
    m = run(text, **STREAM, unexplained='break')
    all_nodes(m)
    sub("the same text with a window of 5")
    m = run(text, **STREAM, unexplained='break', window=5)
    all_nodes(m)
    return m


def node2b_formats():
    head("NODE_2B  Two ways to store a VAR's values")
    from hpcrd.kato_node import Node
    sub("as one list per VAR (the description's example): [[VAR|1],[cat],[dog]], then bird arrives")
    n = Node('lists')
    print("  learn", n.learn([['VAR|1'], ['cat'], ['dog']])[:11], "= [VAR|1] [cat] [dog]")
    print("  learn", n.learn([['VAR|1'], ['cat'], ['dog'], ['bird']])[:11], "= [VAR|1] [cat] [dog] [bird]")
    print("  the same values in another order:", pattern_name([['VAR|1'], ['dog'], ['cat']])[:11], "(another pattern)")
    out = n.predict([['VAR|1']])
    for p in sorted(out['predictions'], key=lambda p: p['name']):
        print(f"      observe [VAR|1] -> {p['name'][:6]} f={p['frequency']} future {json.dumps(p['future'])}")
    out = n.predict([['bird']])
    for p in sorted(out['predictions'], key=lambda p: p['name']):
        print(f"      observe [bird]  -> {p['name'][:6]} f={p['frequency']} past {json.dumps(p['past'])}")
    sub("as one pattern per VAR and value: frequency counts how often the value stood in the slot")
    n = Node('pairs')
    for value, times in (('cat', 3), ('dog', 2), ('bird', 1)):
        for _ in range(times):
            n.learn([['VAR|1'], [value]])
    n.learn([['VAR|2'], ['cat']])
    out = n.predict([['VAR|1']])
    for p in sorted(out['predictions'], key=lambda p: (-p['frequency'], p['name'])):
        print(f"      observe [VAR|1] -> {p['name'][:6]} f={p['frequency']} future {json.dumps(p['future'])}")
    print("      future_potentials:", json.dumps([{k: (round(v, 3) if isinstance(v, float) else v) for k, v in fp.items()}
                                                   for fp in out['future_potentials']]))
    out = n.predict([['cat']])
    for p in sorted(out['predictions'], key=lambda p: p['name']):
        print(f"      observe [cat]   -> {p['name'][:6]} f={p['frequency']} past {json.dumps(p['past'])}")
    print("      is [VAR|1] [bird] known?  frequency of", pattern_name([['VAR|1'], ['bird']])[:11], "=",
          n.frequency(pattern_name([['VAR|1'], ['bird']])), "  (one lookup by name, no search)")
    print("      is [VAR|1] [fish] known?  frequency =", n.frequency(pattern_name([['VAR|1'], ['fish']])))


EXAMPLES = {'1': example1, '2': example2, '3': example3, '4': example4, '5': example5, '6': example6,
            'n': node2b_formats, 'l': limits}

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
