"""With one symbol per event, the alignment KATO computes and does not return
can be rebuilt exactly from `missing`, `extras`, `past`, `present`, `future`.

A fast subset. scripts/check_alignment.py runs the full check (502,184 predictions).
"""
import pytest

from hpcrd.alignment import read
from hpcrd.kato_node import InProcessNode

TOY = ("the cat sat on the mat . the dog sat on the mat . "
       "the cat sat on the rug . a dog sat on the rug .").split()


def generated(n, alphabet, state=12345):
    """A fixed linear congruential generator: the same stream on every run."""
    out = []
    for _ in range(n):
        state = (1103515245 * state + 12345) % (2 ** 31)
        out.append(alphabet[(state >> 16) % len(alphabet)])
    return out


@pytest.mark.parametrize('tokens', [TOY, generated(90, list('abcd')), generated(90, list('abcdefgh'), state=777)],
                         ids=['toy text', '4 symbols', '8 symbols'])
@pytest.mark.parametrize('window', [3, 5, 7])
def test_alignment_is_rebuilt_from_returned_fields(tokens, window):
    node = InProcessNode('node_0', max_pattern_length=window, stm_mode='ROLLING', max_predictions=10000)
    checked = 0
    for token in tokens:
        out = node.observe([token])
        for prediction in out['predictions']:
            reading = read(prediction, out['stm'])
            assert reading.pairs == list(zip(*prediction['_alignment']))
            checked += 1
    assert checked > 100
