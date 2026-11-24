"""Printing helpers shared by the example scripts.

How one learned pattern accounts for each observed position (alignment.read):

    =        matched
    ~x       substituted: the pattern holds x at the aligned position   (`extras` against `missing`)
    e:x      edge: lines up with x in the pattern's `past` or `future`   (rolling windows only)
    +        inserted: the pattern has the two neighbours side by side
    u        unequal gap: n extras against a different number of missing
    .        out of the pattern's view                                   (rolling windows only)
"""

GLYPH = {'I': '+', 'U': 'u', 'O': '.'}


def short(symbol):
    """PTRN|<sha1> -> PTRN|<first 6 hex digits>."""
    if isinstance(symbol, str) and symbol.startswith('PTRN|'):
        return symbol[:11]
    return symbol


def unravel(symbol, node1a):
    """Tokens a symbol stands for: a node_1a name gives its tokens, anything else gives itself."""
    if isinstance(symbol, str) and symbol.startswith('PTRN|') and node1a.frequency(symbol):
        out = []
        for event in node1a.pattern(symbol):
            out += unravel(event[0], node1a)
        return out
    return [symbol]


def spell(symbol, node1a=None):
    """PTRN|ab12cd(sat on the) for a chunk, the symbol itself otherwise."""
    if node1a is not None and isinstance(symbol, str) and symbol.startswith('PTRN|') and node1a.frequency(symbol):
        return f"{symbol[:11]}({' '.join(unravel(symbol, node1a))})"
    return short(symbol)


def seq(symbols, node1a=None):
    return ' '.join(f"[{spell(x, node1a)}]" for x in symbols)


def cells(r):
    out = []
    for rel in r.relation:
        if rel[0] == 'M':
            out.append('=')
        elif rel[0] == 'S':
            out.append('~' + rel[2])
        elif rel[0] == 'E':
            out.append('e:' + rel[2])
        else:
            out.append(GLYPH[rel[0]])
    return out


def reading_line(r, places, stm, width=30):
    where = ','.join(str(p) for p in places)
    return f"{r.name[:6]}  {' '.join(r.pattern):{width}s} @{where:<6s} | " + '  '.join(cells(r))


def whole_reading_line(r, decides=True, width=44):
    """A whole sequence against a whole sequence: no places, the frequency instead."""
    note = '' if decides else '   (not among the nearest: fills gaps, decides nothing)'
    return f"{r.name[:6]}  {' '.join(r.pattern):{width}s} x{r.frequency} | " + '  '.join(cells(r)) + note


def value_text(value, node1a=None):
    """A slot's value: one symbol (values='name') or its tokens (values='sequence')."""
    if isinstance(value, (list, tuple)):
        return ' '.join(spell(x, node1a) for x in value)
    return spell(value, node1a)


def label_line(tokens, res):
    reasons = dict()
    out, k = [], 0
    for token, label in zip(tokens, res['labels']):
        if label == 'N':
            out.append(f"{token}/N:{res['noise'][k][1]}")
            k += 1
        else:
            out.append(f"{token}/{label}")
    return '  '.join(out)


def print_step(step, m, readings=True):
    stm = step['stm']
    learned = step['learned'][:11] if step['learned'] else '-'
    print(f"t={step['t']:<3d} STM       {' '.join(stm)}")
    print(f"      ensemble  {step['ensemble']} predictions: {step['echoes']} echoes held out, "
          f"{len(step['readings'])} read.  node_0 then learns this window as {learned}")
    if readings:
        for r, places in step['readings']:
            print('        ' + reading_line(r, places, stm))
    print_result(step, m, stm)


def print_result(res, m, tokens):
    if 'labels' not in res:
        return
    print('      labels    ' + label_line(tokens, res))
    if not res['parts']:
        print('      nothing to learn above node_0')
    for part in res['parts']:
        print_part(part, m, tokens, many=len(res['parts']) > 1)


def print_part(res, m, tokens, many=False):
    if many:
        lo, hi = res['span']
        print(f"      part      {' '.join(tokens[lo:hi])}")
    for name, toks, support, how, frequency in res['chunks']:
        note = {'match': f"contiguous match, seen whole in {support} earlier place{'s' if support != 1 else ''}",
                'rejoined': 'joined again after the noise between its parts was dropped',
                'value': 'the value of a slot',
                'rule': 'a constant of the rule that read the sequence'}[how]
        print(f"      node_1a   {name[:11]} = [{' '.join(toks)}]   frequency {frequency}   ({note})")
    if res['rule'] is None:
        print('      node_1b   nothing to learn: one symbol is not a pattern')
        return
    if res.get('probe') is not None:
        how = 'RECOGNISED' if res['recognised'] else 'no learned rule fits: new VAR ids'
        print('      probe     ' + seq(res['probe'], m.node1a) + f"   -> {how}")
    print(f"      node_1b   {res['rule'][:11]} = " + seq(res['sequence'], m.node1a)
          + f"   frequency {res['rule_frequency']}")
    for var, value, status, alts in res['bindings']:
        extra = ('; earlier: ' + ', '.join(f"{value_text(a, m.node1a)} x{c}" for a, c in alts.items())) if alts else ''
        print(f"      node_2b   [{var}] [{value_text(value, m.node1a)}]   ({status} value{extra})")
    for what, symbols in res['node2b']:
        print(f"      node_2b   {seq(symbols, m.node1a)}   ({what})")
    for info in res.get('inside', ()):
        print_inside(info, m)


def print_inside(info, m, depth=0):
    """What a VAR's earlier values say about the inside of a new value (Modeler.read_inside)."""
    pad = '      ' + '    ' * depth
    var, value = info['var'], ' '.join(info['value'])
    facts = [f"seen whole {info['same']} time{'s' if info['same'] != 1 else ''} before"]
    if info['partly']:
        facts.append('partly like ' + ', '.join(f"[{' '.join(v)}] x{f}" for v, f in info['partly']))
    if info['apart']:
        facts.append(f"{info['apart']} other value{'s share' if info['apart'] != 1 else ' shares'} no token with it")
    if not info['partly'] and (len(info['value']) < 2 or not (info['same'] or info['apart'])):
        return      # one token, or the VAR's first value: nothing to say
    print(f"{pad}inside    [{var}] <- [{value}]: " + '; '.join(facts))
    if not info['parts']:
        return
    cut = '  '.join(f"[{' '.join(part['tokens'])}]/{'const' if part['kind'] == 'C' else 'slot'}" for part in info['parts'])
    print(f"{pad}  parts   {cut}")
    if info['rule'] is None:
        print(f"{pad}  one part, or nothing in it varies: nothing to record")
        return
    for name, toks, support, _how, frequency in info['chunks']:
        print(f"{pad}  node_1a {name[:11]} = [{' '.join(toks)}]   frequency {frequency}")
    how = 'known' if info['recognised'] else 'new'
    print(f"{pad}  node_1b {info['rule'][:11]} = " + seq(info['sequence'], m.node1a)
          + f"   frequency {info['rule_frequency']}   ({how} inner rule)")
    print(f"{pad}  node_2b [{var}] [{info['rule'][:11]}]   (what the VAR is made of)")
    for inner, tokens, status, alts in info['bindings']:
        extra = ('; earlier: ' + ', '.join(f"{' '.join(a)} x{c}" for a, c in alts.items())) if alts else ''
        print(f"{pad}  node_2b [{inner}] [{' '.join(tokens)}]   ({status} value{extra})")
    for deeper in info['inside']:
        print_inside(deeper, m, depth + 1)


def print_sequence(step, m, readings=True):
    """span='sequence': one whole sequence, its ensemble, and what the module made of it."""
    tokens = step['stm']
    if not tokens:
        return
    learned = step['learned'][:11] if step['learned'] else '-'
    decides = step.get('decides', [])
    read = len(step['readings'])
    print(f"sequence  {' '.join(tokens)}")
    if step.get('by_rule'):
        r = step['stretches'][0]['reading']
        print(f"      node_1t   {r.name[:6]}  {' '.join(r.pattern)}  x{r.frequency} | " + '  '.join(cells(r)))
        print(f"      a learned rule reads the sequence: every constant matched, each gap against one VAR."
              f"  node_0 then learns the sequence as {learned}")
        for res in step['stretches']:
            print_result(res, m, tokens)
        return
    print(f"      ensemble  {step['ensemble']} prediction{'s' if step['ensemble'] != 1 else ''}"
          + (f", {sum(decides)} decide" if read and sum(decides) != read else '')
          + f".  node_0 then learns the sequence as {learned}")
    if readings:
        for (r, _places), d in zip(step['readings'], decides):
            print('        ' + whole_reading_line(r, d))
    for res in step['stretches']:
        print_result(res, m, tokens)


def dump_node(node, title, node1a=None, limit=None):
    print(f"  {title}: {len(node.patterns)} patterns, {node.learns} learns")
    rows = sorted(node.patterns.values(), key=lambda e: (-e['frequency'], e['name']))
    shown = rows if limit is None else rows[:limit]
    for entry in shown:
        symbols = [event[0] for event in entry['pattern_data']]
        print(f"    PTRN|{entry['name'][:6]}  f={entry['frequency']}  {seq(symbols, node1a)}")
    if limit is not None and len(rows) > limit and limit > 0:
        print(f"    ... and {len(rows) - limit} more")
