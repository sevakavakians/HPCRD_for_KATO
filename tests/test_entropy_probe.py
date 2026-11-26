"""The measuring functions of experiments/entropy_probe.py, on sentences small enough to check by hand.
No data file is needed here. The last three tests use a KATO node, and run through a KATO service too."""
import pytest

from experiments.baselines import Spell, gaps
from experiments.entropy_probe import (auc, cut_all, cut_score, edge_rows, edge_table, framed, kato_entropy, place,
                                       placeholders, run_reader, span_score, spell_on_pieces)
from hpcrd.templates import TemplateReader

CITY = [('eat in rome .'.split(), [('city', 2, 3)]), ('eat in oslo .'.split(), [('city', 2, 3)]),
        ('eat in san jose .'.split(), [('city', 2, 4)])]


def test_auc_is_the_chance_that_a_positive_scores_higher():
    assert auc([3, 4], [1, 2]) == 1.0
    assert auc([1, 2], [3, 4]) == 0.0
    assert auc([1, 1], [1, 1]) == 0.5                           # ties count half
    assert auc([2, 1], [1, 0]) == pytest.approx(3.5 / 4)        # 2>1, 2>0, 1=1, 1>0
    assert auc([], [1]) is None and auc([1], []) is None


def test_where_a_boundary_stands_against_the_marked_values():
    slots = [('city', 2, 4), ('time', 4, 6)]
    assert place(slots, 1) == ({'other'}, set())
    assert place(slots, 2) == ({'start'}, {'city'})
    assert place(slots, 3) == ({'inside'}, {'city'})
    assert place(slots, 4) == ({'end', 'start'}, {'city', 'time'})      # one value ends where the next starts
    assert place(slots, 5) == ({'inside'}, {'time'})


def test_cut_score_counts_values_that_are_exactly_one_piece():
    data = [('eat in san jose .'.split(), [('city', 2, 4)]), ('eat in rome'.split(), [('city', 2, 3)])]
    result = cut_score(data, [{2, 4}, {1}])
    # the first value has both edges cut and nothing cut inside; the second needs boundary 2 (its end is the
    # sentence's end, which is given) and does not have it
    assert result['values'] == 2 and result['values that are exactly one piece'] == 1 and result['share'] == 0.5
    assert result['boundaries cut'] == 0.5                      # 3 of the 4 + 2 boundaries inside the sentences
    # at random at that rate: 0.5 x 0.5 x (1 - 0.5) for the first value, 0.5 for the second
    assert result['share by chance at that rate'] == pytest.approx((0.125 + 0.5) / 2, abs=0.001)
    assert result['value edges cut'] == pytest.approx(2 / 3, abs=0.001)
    assert result['boundaries inside a value cut'] == 0.0
    assert result['share by kind'] == {'city': 0.5}
    # a cut inside a value spoils it
    assert cut_score(data, [{2, 3, 4}, {2}])['values that are exactly one piece'] == 1
    # only the sentences from `start` on
    assert cut_score(data, [{2, 4}, {1}], start=1)['values'] == 1


def test_cutting_as_the_sentences_arrive_uses_only_the_earlier_ones():
    data = [(line.split(), []) for line in ('eat in rome', 'eat in paris', 'eat in oslo', 'eat at home', 'sleep in rome')]
    assert cut_all(data, 'increase', earlier=True, val=0.0)[0] == set()          # nothing learned yet
    assert cut_all(data, 'increase', earlier=False, val=0.0)[0] == {1, 2}        # with every sentence counted
    assert cut_all(data, 'ordinary', earlier=False, val=1.2)[0] == {2}
    late = cut_all(data, 'ordinary', earlier=True, val=0.9)
    assert late[0] == set() and late[2] == {2}     # by the third sentence "in" has been followed by two different words


def test_edge_rows_read_the_entropy_on_each_side_of_a_boundary():
    rows = edge_rows(CITY, earlier=False)
    assert len(rows) == 3 + 3 + 4
    labels, kinds, follows, precedes = rows[1]      # sentence 1, the boundary between "in" and "rome"
    assert labels == {'start'} and kinds == {'city'}
    assert follows == pytest.approx(1.585, abs=0.001)           # after "in": rome, oslo, san
    assert precedes == 0.0                                      # before "rome": always "in"
    table = edge_table(rows)
    assert table['boundaries'] == 10 and table['where a word was never seen'] == 0
    assert table["what follows, at a value's start"]['edges'] == 3
    # with nothing learned beforehand the first sentence has no entropy to read
    assert edge_rows(CITY, earlier=True)[1][2] is None


def test_a_piece_is_a_variable_when_its_two_neighbours_stood_around_another_piece():
    cuts = [{2, 3}, {2, 3}, {2, 4}]                 # eat in | rome | .    eat in | oslo | .    eat in | san jose | .
    assert framed(CITY, cuts, seen=1, others=1) == [[], [(2, 3)], [(2, 4)]]
    assert framed(CITY, cuts, seen=2, others=2) == [[], [], [(2, 4)]]
    # the same piece again is not another piece
    same = [CITY[0]] * 3
    assert framed(same, [{2, 3}] * 3, seen=1, others=1) == [[], [], []]
    # an end of the sentence counts as a neighbour
    ends = [('rome'.split(), []), ('oslo'.split(), [])]
    assert framed(ends, [set(), set()], seen=1, others=1) == [[], [(0, 1)]]


def test_spells_loop_on_pieces_is_spells_loop_when_every_word_is_a_piece():
    data = [(line.split(), []) for line in ('book for two at seven .', 'book for six at seven .', 'book for six at nine .',
                                            'thanks a lot .', 'book for a party at nine .')]
    words = [set(range(1, len(tokens))) for tokens, _slots in data]
    arrived, final = spell_on_pieces(data, words)
    parser, expected = Spell(0.5), []
    for tokens, _slots in data:
        k, joined = parser.add(tokens)
        expected.append(gaps(tokens, parser.constants(k)) if joined else [])
    assert arrived == expected and arrived[1] == [(2, 3)] and arrived[4] == [(2, 4), (5, 6)]
    # with pieces, a variable is a whole piece
    arrived, _final = spell_on_pieces(data[:2], [{2, 3}, {2, 3}])       # book for | two | at seven .
    assert arrived == [[], [(2, 3)]]


def test_what_stood_at_the_placeholders_of_spells_templates():
    data = [('eat in rome .'.split(), [('city', 2, 3)]), ('eat in oslo .'.split(), [('city', 2, 3)]),
            ('eat in san jose .'.split(), [('city', 2, 4)]), ('thanks a lot .'.split(), []), ('thanks 4 that .'.split(), []),
            ('never joined by anything else here'.split(), [])]
    table = placeholders(data)
    # two templates of two sentences or more: "eat in * ." and "thanks * .". One placeholder each.
    assert table['all']['placeholders'] == 2 and table['all']['fillers'] == 5
    cities = table['at least half of the fillers are exactly a marked value']
    assert cities['placeholders'] == 1 and cities['fillers'] == 3 and cities['median number of different fillers'] == 3
    assert cities['median of the mean filler length, in tokens'] == pytest.approx(4 / 3, abs=0.01)
    # three different fillers and no digit: Spell's split rule would turn the city placeholder back into constants
    assert cities["placeholders Spell's split rule would take apart (fewer than 8 different fillers, no digit)"] == 1
    # "a lot" and "4 that": a digit among the fillers, so the rule leaves that one alone
    assert table['the others']["placeholders Spell's split rule would take apart (fewer than 8 different fillers, no digit)"] == 0


def test_span_score_is_the_probes_measure():
    data = [('a b c'.split(), []), ('a x c'.split(), [('kind', 1, 2)])]
    result = span_score(data, [[], [(1, 2)]])
    assert result['values that are exactly one variable'] == 1 and result['variables marked'] == 1
    assert result['variables that are exactly a value'] == 1.0
    assert span_score(data, [[], []])['variables that are exactly a value'] is None


def test_the_entropy_of_katos_next_event_distribution():
    assert kato_entropy({'future_potentials': [], 'ends_here': None}) is None
    assert kato_entropy({'future_potentials': [], 'ends_here': 1.0}) == 0.0
    both = {'future_potentials': [{'next_event': ['a'], 'probability': 0.5}, {'next_event': ['b'], 'probability': 0.25}], 'ends_here': 0.25}
    assert kato_entropy(both) == 1.5


# -- with the in-process KATO node --------------------------------------------------------------
FILLER = ['m1 m2 m3 m4', 'n1 n2 n3 n4', 'o1 o2 o3 o4', 'p1 p2 p3 p4', 'q1 q2 q3 q4', 'r1 r2 r3 r4']


def reader_with(evidence, tau=0.2):
    reader = TemplateReader(tau, evidence=evidence)
    for line in FILLER + ['a b c d']:
        reader.read(line.split())
    return reader


@pytest.mark.through_api
def test_a_floor_on_katos_weight_of_evidence_holds_back_a_thin_match():
    # "a z1 z2 z3 z4 d" shares two tokens of six with "a b c d": enough for tau 0.2. KATO's weight of
    # evidence for it is two matches (about 4.7 bits each in this node) less 4.32 bits for each of the
    # two missing and four extra tokens: far below zero.
    thin = 'a z1 z2 z3 z4 d'.split()
    plain = reader_with(None)
    _name, joined, found = plain.read(thin)
    assert joined and found == [(1, 5)] and plain.last['evidence'] < 0
    gated = reader_with(0.0)
    _name, joined, found = gated.read(thin)
    assert not joined and found == []
    # three matches of four outweigh one missing and one extra token: the line joins either way
    _name, joined, found = gated.read('a b c x'.split())
    assert joined and found == [(3, 4)] and gated.last['evidence'] > 0
    gated.check()


@pytest.mark.through_api
def test_a_line_that_is_its_template_joins_whatever_the_floor():
    reader = TemplateReader(0.5, evidence=1000.0)
    reader.read('a b'.split())
    _name, joined, _found = reader.read('a b'.split())
    assert joined
    reader.check()


@pytest.mark.through_api
def test_run_reader_reports_the_evidence_of_every_join():
    data = [(line.split(), []) for line in FILLER + ['a b c d', 'a b c x', 'u v']]
    reader, arrived, final, bits, worn = run_reader(data, tau=0.5)
    assert [b is not None for b in bits] == [False] * 7 + [True, False]
    assert arrived[7] == [(3, 4)] and final[6] == [(3, 4)] and final[7] == [(3, 4)]
    assert worn['rules with at most two fixed words, holding two sentences or more'] == 0 and worn['sentences under them'] == 0
    most_used = 'most-used rules at the end (sentences, fixed words, variables)'
    assert worn[most_used][0] == [2, 3, 1] and run_reader.shown[0] == '2 sentences: a b c *'
    # a rule of two fixed words with two sentences under it is counted as worn
    _reader, _arrived, _final, _bits, worn = run_reader([(line.split(), []) for line in ('no , thanks .', 'no way out .')], tau=0.5)
    assert worn['rules with at most two fixed words, holding two sentences or more'] == 1 and worn['sentences under them'] == 2
    assert worn[most_used] == [[2, 2, 1]] and run_reader.shown == ['2 sentences: no * .']
