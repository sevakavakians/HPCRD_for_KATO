"""Invariants behind the worked examples.

1. Windows: the echo hold-out is exactly "frequency minus the times the pattern is among the
   last window-1 learns".
2. Evidence is causal: every learned pattern that is read lies wholly before what is being read.
3. Every PTRN|... symbol in node_1b and node_2b is a pattern of node_1a (every name unravels).
4. Every rule instance gives back its tokens: the rule, with each VAR replaced by the value bound
   to it and each chunk name unravelled through node_1a, equals the tokens of its part with the
   noise removed.
5. Every VAR in a node_1b pattern has at least one value in node_2b.
6. Texts 1 and 2 give the same nodes whether unexplained tokens are dropped or break the stretch.
"""
from collections import Counter, deque

import pytest

from examples.worked_examples import BASE, STREAM, T1, T2, T3, T3A, T4, T5, T5B
from hpcrd.kato_node import bare
from hpcrd.modeler import VAR, Modeler, Settings
from hpcrd.show import unravel

RUNS = {
    'T1 per window': (T1, {}),
    'T1 stitched': (T1, STREAM),
    'T2 per window': (T2, {}),
    'T2 stitched': (T2, STREAM),
    'T3A sketch': (T3A, {**STREAM, 'unexplained': 'drop'}),
    'T3 letter': (T3, {**STREAM, 'unexplained': 'drop'}),
    'T3 break': (T3, {**STREAM, 'unexplained': 'break'}),
    'T3 gap': (T3, {**STREAM, 'unexplained': 'break', 'slots': 'gap'}),
    'T4': (T4, {**STREAM, 'unexplained': 'break'}),
    'T4 default threshold': (T4, {**STREAM, 'unexplained': 'break', 'recall_threshold': 0.1}),
    'T4 edge': (T4, {'unexplained': 'break', 'edge_vars': True}),
    'T5 rule': (T5, {**STREAM, 'unexplained': 'break'}),
    'T5 neighbours': (T5, {**STREAM, 'unexplained': 'break', 'naming': 'neighbours'}),
    'T5 values': (T5, {**STREAM, 'unexplained': 'break', 'naming': 'values'}),
    'T5B values': (T5B, {**STREAM, 'unexplained': 'break', 'naming': 'values'}),
    'T5 gap values': (T5, {**STREAM, 'unexplained': 'break', 'naming': 'values', 'slots': 'gap'}),
}


def contents(m):
    return {node.name: sorted((e['name'], e['frequency']) for e in node.patterns.values())
            for node in (m.node0, m.node1a, m.node1b, m.node2a, m.node2b)}


def run(text, **kw):
    m = Modeler(Settings(**{**BASE, **kw}))
    results = []
    for token in text.split():
        step = m.feed(token)
        if m.s.span == 'window':
            results.append((step['stm'], step))
        else:
            results += [(m.tokens[r['stretch'][0]:r['stretch'][1]], r) for r in step['stretches']]
    results += [(m.tokens[r['stretch'][0]:r['stretch'][1]], r) for r in m.finish()]
    return m, results


@pytest.mark.parametrize('label', list(RUNS))
def test_invariants(label):
    text, kw = RUNS[label]
    s = Settings(**{**BASE, **kw})
    m = Modeler(s)
    recent = deque(maxlen=s.window - 1)
    results = []
    for token in text.split():
        step = m.feed(token)
        # 1. the hold-out, against the recent-learns rule
        counts = Counter(recent)
        expect = {p['name']: p['frequency'] - counts[p['name']] for p in step['raw']
                  if p['frequency'] - counts[p['name']] > 0}
        assert expect == {r.name: r.frequency for r, _ in step['readings']}
        # 2. causal
        start = step['t'] - len(step['stm']) + 1
        for r, places in step['readings']:
            assert all(base + len(r.pattern) - 1 < start for base in places)
        if step['learned']:
            recent.append(bare(step['learned']))
        if s.span == 'window':
            results.append((step['stm'], step))
        else:
            results += [(m.tokens[r['stretch'][0]:r['stretch'][1]], r) for r in step['stretches']]
    results += [(m.tokens[r['stretch'][0]:r['stretch'][1]], r) for r in m.finish()]
    check_nodes(m, results)


def check_nodes(m, results):
    # 4. every rule instance gives back its tokens
    rebuilt = 0
    for tokens, res in results:
        for part in res['parts']:
            if not part['rule']:
                continue
            values = [value for _var, value, _status, _alts in part['bindings']]
            words, k = [], 0
            for symbol in part['sequence']:
                if symbol.startswith(VAR):
                    value = values[k] if isinstance(values[k], (list, tuple)) else [values[k]]
                    for x in value:
                        words += unravel(x, m.node1a)
                    k += 1
                else:
                    words += unravel(symbol, m.node1a)
            lo, hi = part['span']
            assert words == [tokens[i] for i in range(lo, hi) if res['labels'][i] != 'N']
            rebuilt += 1
    # 3. every name unravels, and 5. every VAR has a value
    names = {'PTRN|' + n for n in m.node1a.patterns}
    variables = set()
    for node in (m.node1b, m.node2b):
        for entry in node.patterns.values():
            for event in entry['pattern_data']:
                symbol = event[0]
                if symbol.startswith('PTRN|'):
                    assert symbol in names
                if node is m.node1b and symbol.startswith(VAR):
                    variables.add(symbol)
    valued = {e['pattern_data'][0][0] for e in m.node2b.patterns.values()
              if e['pattern_data'][0][0].startswith(VAR)}
    assert variables <= valued
    return rebuilt


@pytest.mark.parametrize('text', [T1, T2], ids=['T1', 'T2'])
@pytest.mark.parametrize('span', [{}, STREAM], ids=['per window', 'stitched'])
def test_drop_and_break_agree_where_nothing_is_unexplained_inside(text, span):
    a, _ = run(text, **span, unexplained='drop')
    b, _ = run(text, **span, unexplained='break')
    assert contents(a) == contents(b)
