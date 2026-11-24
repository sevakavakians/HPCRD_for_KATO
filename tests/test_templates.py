"""Spell's loop (Du and Li 2016) on a KATO node, and the retire mirror it needs.

The two worked examples are the paper's own (the second is from the authors' slides).
"""
from examples.sequences import CITIES
from experiments.baselines import Spell, gaps
from hpcrd.kato_node import InProcessNode
from hpcrd.templates import PARAMETER, TemplateReader

PAPER = [    # first line, second line, the template, the second line's parameter, the first line's
    ("Command Failed on: node-127", "Command Failed on: node-235 node-236", "Command Failed on: *",
     "node-235 node-236", "node-127"),
    ("Temperature (41C) exceeds warning threshold", "Temperature (42C, 43C) exceeds warning threshold",
     "Temperature * exceeds warning threshold", "(42C, 43C)", "(41C)"),
]


def test_a_retired_pattern_is_stored_and_skipped_by_every_read():
    node = InProcessNode('n')
    name = node.learn([['a'], ['b'], ['c']])
    assert [p['name'] for p in node.predict([['a'], ['b'], ['x']])['predictions']] == [name[5:]]
    node.retire([name])
    assert node.predict([['a'], ['b'], ['x']])['predictions'] == []
    assert node.predict([['a']])['predictions'] == []           # the one-symbol path too
    assert node.frequency(name) == 0 and name[5:] in node.patterns
    node.unretire([name])
    assert node.frequency(name) == 1
    assert len(node.predict([['a'], ['b'], ['x']])['predictions']) == 1


def test_spell_as_written_gives_the_papers_templates():
    for first, second, template, value, _ in PAPER:
        parser = Spell(0.5)
        assert parser.add(first.split()) == (0, False)
        assert parser.add(second.split()) == (0, True)
        assert ' '.join(parser.templates[0]) == template
        assert [' '.join(second.split()[a:b]) for a, b in gaps(second.split(), parser.constants(0))] == [value]


def test_the_loop_on_kato_gives_the_papers_templates_and_retires_the_old_ones():
    for first, second, template, value, earlier in PAPER:
        reader = TemplateReader(0.5)
        old, joined, found = reader.read(first.split())
        assert not joined and found == []
        new, joined, found = reader.read(second.split())
        assert joined and [' '.join(second.split()[a:b]) for a, b in found] == [value]
        assert ' '.join(reader.template(new)) == template.replace('*', PARAMETER)
        assert old in reader.node.retired and new not in reader.node.retired
        assert reader.current(old) == new                       # the first line's type is the new template
        assert len(reader.node.patterns) == 2                   # the old template is still stored
        # the first line again: it joins, and nothing changes but the count
        again, joined, found = reader.read(first.split())
        assert again == new and joined and reader.node.frequency(new) == 2
        assert [' '.join(first.split()[a:b]) for a, b in found] == [earlier]


def run(text, tau=0.5):
    reader, seen = TemplateReader(tau), []
    for sentence in text.split(' . '):
        tokens = sentence.replace(' .', '').split() + ['.']
        seen.append((tokens, *reader.read(tokens)))
    return reader, seen


def test_one_template_for_the_cities_and_each_city_at_its_placeholder():
    reader, seen = run(CITIES)
    live = [e for e in reader.node.patterns.values() if e['name'] not in reader.node.retired]
    assert [[ev[0] for ev in e['pattern_data']] for e in live] == [['show', 'flights', 'from', PARAMETER, 'to', 'denver', '.']]
    assert live[0]['frequency'] == 6                            # six lines joined it; the first made it
    values = [' '.join(tokens[a:b]) for tokens, name, _joined, _found in seen for a, b in reader.gaps(tokens, name)]
    assert values == ['boston', 'dallas', 'new york', 'los angeles', 'new york', 'new york city', 'new jersey']


def test_the_same_text_gives_the_same_patterns_twice():
    a, _ = run(CITIES)
    b, _ = run(CITIES)
    assert sorted(a.node.patterns) == sorted(b.node.patterns) and a.node.retired == b.node.retired
