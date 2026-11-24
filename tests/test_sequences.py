"""Round 2: whole sequences at node_0, one VAR per gap, values as sequences, the inside reading,
and a learned rule reading a new sequence.

1. examples/sequences.py prints exactly examples/report_sequences.txt, under two hash seeds.
2. With whole sequences the module keeps no record of its own, node_0 holds one pattern per
   distinct sequence, and every pattern's frequency is the number of times it was read.
3. Every rule instance gives back its tokens, whichever way it was read.
4. Every inner rule gives back the value it describes.
5. Every name resolves: PTRN|... in node_1b is a chunk of node_1a; in node_2b a chunk or a rule;
   node_1t holds tokens and VARs only.
6. Every VAR in a rule has a value in node_2b.
7. A rule reads a sequence only when every constant is matched and each gap faces one VAR.
"""
import hashlib
import os
import pathlib
import subprocess
import sys
from collections import Counter

import pytest

from examples.sequences import CITIES, CLOSE, GAP, MIXED, PARTY, SEQUENCE
from examples.worked_examples import T1, T2, T3, T3A, T4, T5, T5B
from hpcrd.alignment import read
from hpcrd.kato_node import InProcessNode
from hpcrd.modeler import PREFIX, VAR, Modeler, Settings
from hpcrd.show import unravel

ROOT = pathlib.Path(__file__).resolve().parent.parent
REPORT = ROOT / 'examples' / 'report_sequences.txt'

RUNS = {
    'T1 per position': (T1, SEQUENCE),
    'T2 per position': (T2, SEQUENCE),
    'T3 per position': (T3, SEQUENCE),
    'T3A per position': (T3A, SEQUENCE),
    'T4 per position': (T4, SEQUENCE),
    'T5B per position, by values': (T5B, {**SEQUENCE, 'naming': 'values'}),
    'close analogs': (CLOSE, SEQUENCE),
    'T3 per gap': (T3, GAP),
    'T3A per gap': (T3A, GAP),
    'T4 per gap, nearest': (T4, {**GAP, 'fold': 'nearest'}),
    'T5 per gap, 0.7': (T5, {**GAP, 'recall_threshold': 0.7}),
    'T5 per gap, by values': (T5, {**GAP, 'naming': 'values'}),
    'T5B per gap, by neighbours': (T5B, {**GAP, 'naming': 'neighbours'}),
    'cities, inside': (CITIES, {**GAP, 'inside': True}),
    'party, inside': (PARTY, {**GAP, 'inside': True}),
    'T3A, inside': (T3A, {**GAP, 'inside': True}),
    'mixed, rules first': (MIXED, {**GAP, 'topdown': True, 'rule_threshold': 0.3}),
    'cities, rules first, inside': (CITIES, {**GAP, 'topdown': True, 'inside': True}),
    'T5, nearest, rules first': (T5, {**GAP, 'fold': 'nearest', 'topdown': True}),
}


def test_report_is_reproduced_under_two_hash_seeds():
    want = hashlib.sha1(REPORT.read_bytes()).hexdigest()
    assert want in (ROOT / 'README.md').read_text()
    for seed in ('0', '7'):
        env = {**os.environ, 'PYTHONHASHSEED': seed, 'PYTHONPATH': str(ROOT), 'LOG_LEVEL': 'ERROR'}
        out = subprocess.run([sys.executable, str(ROOT / 'examples' / 'sequences.py')], cwd=ROOT, env=env,
                             capture_output=True, text=True, check=True).stdout
        kept = ''.join(line + '\n' for line in out.splitlines()
                       if not line.startswith(('INFO', 'DEBUG', 'WARNING', '***')) and 'RapidFuzz' not in line)
        assert hashlib.sha1(kept.encode()).hexdigest() == want, f"PYTHONHASHSEED={seed}"


def tokens_of(symbols, values, node1a):
    """A rule's symbols with each VAR replaced by its value and each name unravelled."""
    words, k = [], 0
    for symbol in symbols:
        if symbol.startswith(VAR):
            value = values[k] if isinstance(values[k], (list, tuple)) else [values[k]]
            for x in value:
                words += unravel(x, node1a)
            k += 1
        else:
            words += unravel(symbol, node1a)
    return words


def check_inside(info, m):
    count = 0
    if info['rule']:
        values = [tokens for _var, tokens, _status, _alts in info['bindings']]
        assert tokens_of(info['sequence'], values, m.node1a) == info['value']
        count += 1
    for deeper in info['inside']:
        count += check_inside(deeper, m)
    return count


@pytest.mark.parametrize('label', list(RUNS))
def test_invariants(label):
    text, kw = RUNS[label]
    m = Modeler(Settings(**kw))
    sentences = Counter()
    instances = by_rule = inner = 0
    for token in text.split():
        step = m.feed(token)
        if not step['stm']:
            continue
        tokens = step['stm']
        sentences[tuple(tokens)] += 1
        for result in step['stretches']:
            for part in result['parts']:
                if not part['rule']:
                    continue
                instances += 1
                by_rule += bool(part.get('by_rule'))
                values = [value for _var, value, _status, _alts in part['bindings']]
                lo, hi = part['span']
                kept = [tokens[i] for i in range(lo, hi) if result['labels'][i] != 'N']
                assert tokens_of(part['sequence'], values, m.node1a) == kept            # 3
                for info in part['inside']:
                    inner += check_inside(info, m)                                       # 4
    m.finish()
    # 2. no record of the module's own; node_0 is the sentences, counted
    assert m.learned_at == {}
    assert sorted(e['frequency'] for e in m.node0.patterns.values()) == sorted(sentences.values())
    assert {tuple(ev[0] for ev in e['pattern_data']) for e in m.node0.patterns.values()} == set(sentences)
    # 5. names resolve
    chunks = {PREFIX + n for n in m.node1a.patterns}
    rules = {PREFIX + n for n in m.node1b.patterns}
    variables = set()
    for entry in m.node1b.patterns.values():
        for event in entry['pattern_data']:
            if event[0].startswith(PREFIX):
                assert event[0] in chunks
            if event[0].startswith(VAR):
                variables.add(event[0])
    for entry in m.node2b.patterns.values():
        for event in entry['pattern_data']:
            if event[0].startswith(PREFIX):
                assert event[0] in chunks | rules
    if m.node1t is not None:
        for entry in m.node1t.patterns.values():
            assert not any(event[0].startswith(PREFIX) for event in entry['pattern_data'])
        assert len(m.node1t.patterns) == len(m.rule_of)
    # 6. every VAR of a rule has a value
    valued = {e['pattern_data'][0][0] for e in m.node2b.patterns.values()}
    assert variables <= valued
    assert instances > 0
    if kw.get('topdown'):
        assert by_rule > 0
    if label in ('cities, inside', 'party, inside'):
        assert inner > 0
    if label == 'T3A, inside':
        assert inner == 0       # nothing in that text recombines


def test_whole_sequences_have_no_edges():
    """Two complete sequences are lined up end to end, so what stands before the first match
    or after the last one is a gap like any other."""
    node = InProcessNode('node_0')
    node.learn([[t] for t in "a dog sat on the mat".split()])
    stm = [[t] for t in "the cat sat on the rug".split()]
    prediction = node.predict(stm)['predictions'][0]
    assert [r[0] for r in read(prediction, stm).relation] == ['E', 'E', 'M', 'M', 'M', 'E']     # a window: edges
    whole = read(prediction, stm, whole=True)
    assert [r[0] for r in whole.relation] == ['S', 'S', 'M', 'M', 'M', 'S']
    assert [r[2] for r in whole.relation if r[0] == 'S'] == ['a', 'dog', 'mat']


def run(text, **kw):
    m = Modeler(Settings(**kw))
    steps = [m.feed(token) for token in text.split()]
    m.finish()
    return m, [s for s in steps if s['stm']]


def test_close_analogs_are_compared():
    """Weakness 6 of the first write-up: with windows of 7 this text gave no rule."""
    m, _ = run(CLOSE, **SEQUENCE)
    (rule,) = m.node1b.patterns.values()
    assert [e[0] for e in rule['pattern_data']] == ['the', 'VAR|1', 'says', 'VAR|2', '.']
    assert rule['frequency'] == 3


def test_a_gap_is_one_variable_whatever_its_length():
    m, _ = run(CITIES, **GAP)
    (rule,) = m.node1b.patterns.values()
    assert rule['frequency'] == 6 and sum(e[0].startswith(VAR) for e in rule['pattern_data']) == 1
    values = {tuple(e[0] for e in p['pattern_data'][1:]): p['frequency'] for p in m.node2b.patterns.values()}
    assert values[('new', 'york')] == 2             # the unit, counted
    assert values[('new', 'york', 'city')] == 1
    assert values[('boston',)] == 1                 # known only as what an earlier sentence had there


def test_inside_a_var_parts_that_recombine_become_slots_and_the_rule_stays():
    m, steps = run(PARTY, **GAP, inside=True)
    outer = [p['rule'] for s in steps for r in s['stretches'] for p in r['parts'] if p['rule']]
    assert len(set(outer)) == 1                     # one rule throughout
    inner = [e for e in m.node1b.patterns.values() if all(ev[0].startswith(VAR) for ev in e['pattern_data'])]
    assert [[ev[0] for ev in e['pattern_data']] for e in inner] == [['VAR|2', 'VAR|3']]
    assert inner[0]['frequency'] == 2
    held = {tuple(ev[0] for ev in e['pattern_data']) for e in m.node2b.patterns.values()}
    assert {('VAR|2', 'two'), ('VAR|2', 'four'), ('VAR|3', 'quiet', 'adults'), ('VAR|3', 'hungry', 'diners')} <= held


def test_a_rule_reads_a_value_of_any_length_and_refuses_an_insertion():
    m, steps = run(MIXED, **GAP, topdown=True, rule_threshold=0.3)
    by_rule = {' '.join(s['stm']): bool(s.get('by_rule')) for s in steps}
    assert by_rule['show flights from san francisco to denver .']
    assert by_rule['play the long and winding road .']
    assert not by_rule['show me flights from boston to denver .']     # `me` stands against no VAR
    held = {tuple(ev[0] for ev in e['pattern_data']) for e in m.node2b.patterns.values()}
    assert ('VAR|2', 'the', 'long', 'and', 'winding', 'road') in held
    assert len(m.node1b.patterns) == 2


def test_cut_gives_the_boundary_without_a_marker():
    a = Modeler(Settings(**{**GAP, 'markers': ()}))
    for sentence in CITIES.split(' . '):
        for token in sentence.replace(' .', '').split():
            a.feed(token)
        a.cut()
    b, _ = run(CITIES.replace(' .', ''), **{**GAP, 'markers': ()})
    assert len(a.node0.patterns) == 6 and len(a.node1b.patterns) == 1
    assert len(b.node0.patterns) == 1               # without a cut the text is one sequence
