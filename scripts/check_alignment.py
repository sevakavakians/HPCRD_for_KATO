"""Check: with one symbol per event, the alignment KATO computes and does not return
can be rebuilt exactly from `missing`, `extras`, `past`, `present`, `future`.

Compares alignment.read() with the matcher's own (refined) positions on every
prediction of (1) the toy text and (2) generated streams with many repeated
symbols, for several window sizes. Streams come from a fixed linear congruential
generator, so every run reads the same data.
"""
from hpcrd.alignment import read
from hpcrd.kato_node import InProcessNode as Node


def lcg_stream(n, alphabet, state=12345):
    out = []
    for _ in range(n):
        state = (1103515245 * state + 12345) % (2 ** 31)
        out.append(alphabet[(state >> 16) % len(alphabet)])
    return out


def check(tokens, window):
    node = Node('node_0', max_pattern_length=window, stm_mode='ROLLING', max_predictions=10000)
    predictions = agree = 0
    kinds = {}
    for token in tokens:
        out = node.observe([token])
        for p in out['predictions']:
            predictions += 1
            reading = read(p, out['stm'])
            internal = list(zip(*p['_alignment']))
            if reading.pairs == internal:
                agree += 1
            for rel in reading.relation:
                kinds[rel[0]] = kinds.get(rel[0], 0) + 1
    return predictions, agree, kinds


if __name__ == '__main__':
    toy = ("the cat sat on the mat . the dog sat on the mat . "
           "the cat sat on the rug . a dog sat on the rug .").split()
    total = ok = 0
    for label, tokens in (('toy text', toy),
                          ('generated, 4 symbols', lcg_stream(400, list('abcd'))),
                          ('generated, 12 symbols', lcg_stream(400, list('abcdefghijkl'), state=777))):
        for window in (3, 5, 7, 10):
            n, a, kinds = check(tokens, window)
            total += n
            ok += a
            print(f"{label:22s} window {window:2d}: {a}/{n} predictions rebuilt exactly; positions {dict(sorted(kinds.items()))}")
    print(f"TOTAL {ok}/{total}")
