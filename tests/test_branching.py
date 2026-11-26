"""Branching entropy and the two cutting rules (experiments/branching.py). Counts only: no KATO, no data file."""
import math

import pytest

from experiments.branching import END, START, Branching, entropy, pieces

LINES = ['eat in rome', 'eat in paris', 'eat in oslo', 'eat at home', 'sleep in rome']


def learned(lines=LINES, longest=6):
    counts = Branching(longest)
    for line in lines:
        counts.learn(line.split())
    return counts


def test_entropy_of_a_table_of_counts():
    assert entropy({}) is None
    assert entropy({'a': 4}) == 0.0 and math.copysign(1, entropy({'a': 4})) == 1.0    # 0.0, not -0.0
    assert entropy({'a': 1, 'b': 1}) == 1.0
    assert entropy({'a': 3, 'b': 1}) == pytest.approx(0.8112781244591328, abs=1e-12)
    assert entropy({'a': 1, 'b': 2, 'c': 3}) == entropy({'c': 3, 'a': 1, 'b': 2})     # filled in another order: the same bits


def test_what_followed_and_what_preceded_every_stretch():
    counts = learned()
    assert counts.followed[('in',)] == {'rome': 2, 'paris': 1, 'oslo': 1}
    assert counts.preceded[('in',)] == {'eat': 3, 'sleep': 1}
    assert counts.followed[('rome',)] == {END: 2}               # nothing follows: an outcome of its own
    assert counts.preceded[('eat',)] == {START: 4}
    assert counts.followed[('eat', 'in')] == {'rome': 1, 'paris': 1, 'oslo': 1}
    assert counts.after(['eat', 'in']) == pytest.approx(math.log2(3))
    assert counts.after(['eat']) == pytest.approx(0.8112781244591328)
    assert counts.before(['in', 'rome']) == 1.0
    assert counts.before(['rome']) == 0.0
    assert counts.after(['never', 'seen']) is None and counts.before(['never']) is None


def test_the_longest_stretch_counted_is_a_setting():
    assert ('eat', 'in') not in learned(longest=1).followed
    assert ('eat', 'in', 'rome') in learned(longest=3).followed and ('eat', 'in', 'rome') not in learned(longest=2).followed
    with pytest.raises(ValueError):
        Branching(longest=0)


def test_b_increase_cuts_where_the_entropy_rises():
    counts, line = learned(), 'eat in rome'.split()
    # forward: after "eat in" (1.585 bits) there is more doubt than after "eat" (0.811): a boundary after "in"
    assert counts.increase(line, backward=False) == {2}
    # backward: before "in rome" (1 bit) there is more doubt than before "rome" (0): a boundary before "in"
    assert counts.increase(line, forward=False) == {1}
    assert counts.increase(line) == {1, 2}
    assert counts.increase(line, val=1.0) == set()              # neither rise is above one bit


def test_b_ordinary_cuts_where_the_entropy_is_high():
    counts, line = learned(), 'eat in rome'.split()
    assert counts.ordinary(line, val=0.9) == {1, 2}             # after "in" 1.5 and after "eat in" 1.585; before "in rome" 1.0
    assert counts.ordinary(line, val=1.2) == {2}
    assert counts.ordinary(line, val=1.2, forward=False) == set()
    assert counts.ordinary(line, val=2.0) == set()


def test_a_stretch_never_seen_decides_nothing():
    counts = learned()
    assert counts.increase('fly to rome'.split()) == set()
    assert counts.ordinary('fly to rome'.split(), val=0.0) == set()
    # and so a sentence cut before anything was learned is not cut at all
    assert Branching().increase('eat in rome'.split()) == set()
    assert Branching().ordinary('eat in rome'.split(), val=0.0) == set()


def test_a_boundary_is_never_an_end_of_the_sequence():
    counts = learned()
    for line in LINES:
        tokens = line.split()
        for cuts in (counts.increase(tokens), counts.ordinary(tokens, val=0.0)):
            assert all(0 < b < len(tokens) for b in cuts)


def test_the_order_of_learning_does_not_change_the_cuts():
    one, other = learned(LINES), learned(list(reversed(LINES)))
    for line in LINES:
        assert one.increase(line.split()) == other.increase(line.split())
        assert one.ordinary(line.split(), val=0.9) == other.ordinary(line.split(), val=0.9)


def test_pieces_are_the_stretches_between_the_cuts():
    assert pieces(list('abcd'), {1, 3}) == [(0, 1), (1, 3), (3, 4)]
    assert pieces(list('abcd'), set()) == [(0, 4)]
    assert pieces(list('abcd'), {1, 2, 3}) == [(0, 1), (1, 2), (2, 3), (3, 4)]
