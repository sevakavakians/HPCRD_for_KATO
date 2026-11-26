"""Drain's rule: as three rules without KATO (experiments/log_benchmark.py, DrainRules) and on a KATO node
(hpcrd/templates.py, PositionReader). No data file is needed here."""
import pytest

from experiments.log_benchmark import STAR, DrainRules, apart
from hpcrd.templates import PositionReader, TemplateReader

pytestmark = pytest.mark.through_api


def groups_by_rules(lines, threshold, lead):
    parser, member = DrainRules(threshold, lead), []
    for line in lines:
        member.append(parser.add(line.split()))
    return [' '.join(parser.templates[k]) for k in member], parser


def groups_on_kato(lines, threshold, lead):
    reader, member = PositionReader(threshold, lead, parameter=STAR), []
    for line in lines:
        name, _joined, _gaps = reader.read(line.split())
        member.append(reader.kind if name else ('one symbol', tuple(line.split())))
    reader.check()
    return [' '.join(reader.template(reader.now(kind))) if isinstance(kind, int) else ' '.join(kind[1]) for kind in member], reader


def test_the_three_rules():
    lines = ['send pkt 1 to a', 'send pkt 2 to b', 'recv pkt 3 from a', 'send pkt 1', 'send pkt 9 to a']
    groups, parser = groups_by_rules(lines, 0.5, 1)
    # lines 1, 2 and 5 are one type: five tokens, "send" first, and three or four positions the same
    assert groups == [f"send pkt {STAR} to {STAR}"] * 2 + ['recv pkt 3 from a', 'send pkt 1', f"send pkt {STAR} to {STAR}"]
    # rule 1: "send pkt 1" has three tokens and joins nothing of five. Rule 2: "recv ..." does not start with "send".
    assert parser.templates == [['send', 'pkt', STAR, 'to', STAR], ['recv', 'pkt', '3', 'from', 'a'], ['send', 'pkt', '1']]


def test_rule_3_compares_by_position_and_spell_by_order():
    lines = ['a b c d', 'b c d e']
    assert groups_by_rules(lines, 0.5, 0)[0] == lines           # no position holds the same token: two types
    spell = TemplateReader(0.5)
    assert [spell.read(line.split())[1] for line in lines] == [False, True]      # three of four tokens, in order: one type


def test_rule_2_and_a_leading_token_with_a_digit():
    assert groups_by_rules(['job start x', 'run start y'], 0.3, 1)[0] == ['job start x', 'run start y']     # rule 2
    assert groups_by_rules(['job start x', 'run start y'], 0.3, 0)[0] == [f"{STAR} start {STAR}"] * 2       # without it
    # a token that holds a digit counts as a placeholder, so the first two lines are one type; and a template
    # that starts with a placeholder takes any leading token from then on
    assert groups_by_rules(['123 start x', '456 start y', 'job start z'], 0.3, 1)[0] == [f"{STAR} start {STAR}"] * 3


def test_ties_go_to_more_placeholders_then_to_the_older_type():
    # 'a b c' and 'a x c' make 'a <*> c'; 'q b c' is a second type. 'a b c' again holds two tokens of 'a <*> c'
    # and two of 'q b c': the template with the placeholder wins.
    lines = ['a b c', 'a x c', 'q b c', 'a b c']
    groups, parser = groups_by_rules(lines, 0.6, 0)
    assert groups == [f"a {STAR} c", f"a {STAR} c", 'q b c', f"a {STAR} c"]
    older, _ = groups_by_rules(['a b c', 'q b z', 'a b z'], 0.6, 0)             # two each, no placeholders: the older type
    assert older == [f"a b {STAR}", 'q b z', f"a b {STAR}"]


def test_a_placeholder_written_into_a_line_matches_nothing():
    # preprocessing writes <*> into the lines. Drain does not count it as the same token, on either side.
    lines = [f"{STAR} {STAR} x", f"{STAR} {STAR} x"]
    groups, parser = groups_by_rules(lines, 0.5, 0)
    assert len(parser.templates) == 2 and groups[0] == groups[1]        # one of three positions: two types, the same text
    on_kato, reader = groups_on_kato(lines, 0.5, 0)
    assert on_kato == groups and reader.merged == 1                     # on KATO that text is one pattern, for both types
    assert len(reader.where) == 2


def test_on_kato_the_matches_are_drains_count():
    reader = PositionReader(0.5, 1)
    name, joined, found = reader.read('send pkt 1 to a'.split())
    assert not joined and found == []
    assert reader.node.pattern(name) == [['0|=send'], ['1|=pkt'], ['2|=1'], ['3|=to'], ['4|=a']]
    name, joined, found = reader.read('send pkt 2 to b'.split())
    assert joined and found == [(2, 3), (4, 5)]
    assert reader.template(name) == ['send', 'pkt', 'VAR|*', 'to', 'VAR|*']
    assert reader.node.pattern(name) == [['0|=send'], ['1|=pkt'], ['2|*'], ['3|=to'], ['4|*']]
    assert len(reader.node.retired) == 1                                # the first version is kept, retired
    assert reader.read('pkt send 2 to b'.split())[1] is False           # the same tokens in other places: rule 2, and 3 of 5 otherwise
    assert reader.read('send pkt 1'.split())[1] is False                # rule 1
    assert reader.read('one'.split()) == (None, False, [])              # KATO does not learn one symbol
    reader.check()


def test_the_node_must_return_every_template_the_rule_could_accept():
    with pytest.raises(ValueError):
        PositionReader(threshold=0.05)


def made_up_lines(count=240):
    verbs, things, ends = ['open', 'close', 'read'], ['file', 'port', 'pipe', 'lock', 'link'], ['ok', 'failed', 'again', 'late']
    lines = []
    for i in range(count):      # no random numbers: every line is fixed by its index
        line = [verbs[i % 3], things[(i * 7) % 5], str(i % 11), 'for', f"user{(i * 5) % 13}", ends[(i // 3) % 4]]
        if i % 17 == 0:
            line = line[:4]
        if i % 19 == 0:
            line[0] = str(i)
        if i % 23 == 0:
            line[2] = STAR
        lines.append(' '.join(line))
    return lines


@pytest.mark.parametrize('threshold, lead', [(0.5, 1), (0.34, 0), (0.7, 2), (0.2, 3)])
def test_on_kato_every_line_is_grouped_as_by_the_three_rules(threshold, lead):
    lines = made_up_lines()
    plain, parser = groups_by_rules(lines, threshold, lead)
    on_kato, reader = groups_on_kato(lines, threshold, lead)
    assert apart(on_kato, plain) == 0
    assert len(set(plain)) > 3                                          # and it is not all one group
