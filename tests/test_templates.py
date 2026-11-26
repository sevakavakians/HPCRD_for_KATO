"""Spell's loop (Du and Li 2016) on a KATO node, and the retire mirror it needs.

The two worked examples are the paper's own (the second is from the authors' slides).
"""
import pytest

from examples.sequences import CITIES
from experiments.baselines import Spell, gaps
from hpcrd.kato_node import Node, RetiredPattern
from hpcrd.templates import PARAMETER, TemplateReader

pytestmark = pytest.mark.through_api

PAPER = [    # first line, second line, the template, the second line's parameter, the first line's
    ("Command Failed on: node-127", "Command Failed on: node-235 node-236", "Command Failed on: *",
     "node-235 node-236", "node-127"),
    ("Temperature (41C) exceeds warning threshold", "Temperature (42C, 43C) exceeds warning threshold",
     "Temperature * exceeds warning threshold", "(42C, 43C)", "(41C)"),
]


# `Node` is the in-process node, or KATO's REST API when KATO_API is set: these tests say what
# both do. Through the API they were run against a service at f32bac0 (see the README).

def test_a_retired_pattern_is_stored_and_skipped_by_every_prediction():
    node = Node('n')
    name = node.learn([['a'], ['b'], ['c']])
    assert [p['name'] for p in node.predict([['a'], ['b'], ['x']])['predictions']] == [name[5:]]
    node.retire([name])
    node.retire([name])                                         # twice is once
    assert node.predict([['a'], ['b'], ['x']])['predictions'] == []
    assert node.predict([['a']])['predictions'] == []           # the one-symbol path too
    assert node.frequency(name) == 1 and name[5:] in node.patterns     # still stored, and still read by name
    assert node.pattern(name) == [['a'], ['b'], ['c']]
    node.unretire([name])
    assert node.frequency(name) == 1
    assert len(node.predict([['a'], ['b'], ['x']])['predictions']) == 1


def test_a_retired_pattern_cannot_be_learned_again_until_it_is_unretired():
    # kato/informatics/knowledge_base.py, learnPattern: RetiredPatternError, which the API answers with 409
    node = Node('n')
    name = node.learn([['a'], ['b'], ['c']])
    node.retire([name])
    with pytest.raises(RetiredPattern):
        node.learn([['a'], ['b'], ['c']])
    assert node.learns == 1 and node.patterns[name[5:]]['frequency'] == 1      # nothing was written
    other = node.learn([['a'], ['b'], ['d']])                                   # and nothing is left in the way
    assert node.pattern(other) == [['a'], ['b'], ['d']]
    node.unretire([name])
    assert node.learn([['a'], ['b'], ['c']]) == name and node.frequency(name) == 2


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
    reader.check()


def test_the_same_text_gives_the_same_patterns_twice():
    a, _ = run(CITIES)
    b, _ = run(CITIES)
    assert sorted(a.node.patterns) == sorted(b.node.patterns) and a.node.retired == b.node.retired


def test_a_line_stays_with_its_message_type_when_its_text_is_learned_again():
    """A type's template wears down until the line that made the type no longer joins it. That text
    is then a new type, on the pattern KATO retired earlier: the name is the content's hash. The
    earlier lines stay with the type they joined."""
    reader, kinds = TemplateReader(0.5), []
    for line in ('a b c d', 'a b x y', 'a z', 'a b c d'):
        name, joined, _found = reader.read(line.split())
        kinds.append(reader.kind)
    assert kinds == [0, 0, 0, 1] and not joined and reader.revived == 1
    assert reader.template(reader.now(0)) == ['a', PARAMETER]
    assert reader.template(reader.now(1)) == ['a', 'b', 'c', 'd']
    assert name == reader.now(1) and name not in reader.node.retired and name not in reader.successor
    assert reader.node.frequency(name) == 2     # KATO counts the content: once as the first type's template
    reader.check()
    name, joined, _found = reader.read('a b c e'.split())
    assert joined and reader.kind == 1 and reader.template(name) == ['a', 'b', 'c', PARAMETER]
    assert reader.template(reader.now(0)) == ['a', PARAMETER]
    reader.check()


def test_two_types_whose_templates_become_the_same_are_one_pattern():
    """One content is one pattern in KATO. The types keep their numbers and share the template from then on."""
    star = '<*>'
    reader, kinds = TemplateReader(0.5, parameter=star), []
    for line in (['a', 'a'], [star, 'a', star], ['b', 'a'], [star, 'a']):
        name, joined, _found = reader.read(line)
        kinds.append(reader.kind)
    assert kinds == [0, 1, 0, 0] and reader.merged == 1
    assert reader.now(0) == reader.now(1) == name and reader.types[name] == [0, 1]
    assert reader.template(name) == [star, 'a', star]
    assert len(reader.node.patterns) == 2 and len(reader.node.retired) == 1
    reader.check()


def test_a_line_of_placeholders_only_joins_the_type_it_is():
    """Placeholders side by side run together into one symbol, and one symbol is nothing KATO learns."""
    star = '<*>'
    reader = TemplateReader(0.5, parameter=star)
    first, joined, _found = reader.read([star, star])
    assert not joined
    again, joined, found = reader.read([star, star])
    assert joined and again == first and found == [] and reader.kind == 0
    assert reader.node.frequency(first) == 2 and not reader.node.retired
    other, joined, _found = reader.read([star, star, star])
    assert not joined and reader.kind == 1      # three placeholders are another content, and no generalisation of the two
    reader.check()
