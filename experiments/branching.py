"""Branching entropy over token sequences, and two published rules for cutting by it.

Harris (1955, "From phoneme to morpheme", Language 31) proposed that the number of different
things that can follow a stretch of a sequence rises where a unit ends. Jin and Tanaka-Ishii (2006,
"Unsupervised Segmentation of Chinese Text by Use of Branching Entropy",
https://aclanthology.org/P06-2056/) measure that as the entropy of what follows an n-gram x,

    h(x) = - sum over y of P(y | x) log2 P(y | x)

and test three rules for placing a boundary. Two of them are here, as the paper states them:

    B_increase   after x_(n+1) when h(x_(n+1)) - h(x_n) > val, x_n being x_(n+1) without its last token
    B_ordinary   after x when h(x) > val

Both are applied to every start position and every n-gram of up to `longest` tokens (6 in the
paper), reading forward (what follows) and backward (what precedes); a boundary that any one n-gram
gives is a boundary. On Chinese characters, with counts from 200 MB of text, the paper found
B_increase the best of the three (precision 0.88, recall 0.79 at val = 0).

What is this file's reading, and not the paper's:

- P(y | x) is the count of x followed by y over the count of x. The paper does not state its
  estimator.
- The sequences are separate (sentences). "Nothing follows" and "nothing precedes" are outcomes,
  written END and START. They are never part of an n-gram.
- An n-gram that was never seen has no entropy, and decides nothing.
- B_increase puts the boundary after the longer n-gram, where the entropy is the higher one.
- The counts can be those of the sequences read so far, which is what a system that learns as
  data arrives has. The paper takes them from a separate, much larger text.

Counts only. Nothing here uses KATO. Every sum runs in a stated order.
"""
import math
from collections import Counter

END, START = '</s>', '<s>'


def entropy(counts):
    """Shannon entropy in bits of a table of counts; None for an empty table. The terms are added
    from the smallest count up, so equal tables give equal bits whatever order they were filled in."""
    total = 0
    for count in counts.values():
        total += count
    if not total:
        return None
    bits = 0.0
    for count in sorted(counts.values()):
        share = count / total
        bits -= share * math.log2(share)
    return bits + 0.0       # -0.0, which one certain outcome gives, becomes 0.0


class Branching:
    """What followed, and what preceded, every stretch of up to `longest` tokens learned so far."""

    def __init__(self, longest=6):
        if longest < 1:
            raise ValueError("longest must be at least 1")
        self.longest = longest
        self.followed = {}      # n-gram -> Counter of the token after it, or END
        self.preceded = {}      # n-gram -> Counter of the token before it, or START
        self.sequences = 0

    def learn(self, tokens):
        tokens, n = list(tokens), len(tokens)
        self.sequences += 1
        for i in range(n):
            for j in range(i + 1, min(n, i + self.longest) + 1):
                gram = tuple(tokens[i:j])
                self.followed.setdefault(gram, Counter())[tokens[j] if j < n else END] += 1
                self.preceded.setdefault(gram, Counter())[tokens[i - 1] if i > 0 else START] += 1

    def after(self, gram):
        """h(gram): the entropy of what follows it. None when the n-gram was never seen."""
        counts = self.followed.get(tuple(gram))
        return entropy(counts) if counts else None

    def before(self, gram):
        """The same, read backward: the entropy of what precedes it."""
        counts = self.preceded.get(tuple(gram))
        return entropy(counts) if counts else None

    def increase(self, tokens, val=0.0, forward=True, backward=True):
        """B_increase. Returns the boundaries inside `tokens`: b stands between tokens[b-1] and
        tokens[b], 0 < b < len(tokens)."""
        tokens, n, cuts = list(tokens), len(tokens), set()
        for i in range(n):
            for j in range(i + 2, min(n, i + self.longest) + 1):    # tokens[i:j], two tokens or more
                if forward and j < n:
                    longer, shorter = self.after(tokens[i:j]), self.after(tokens[i:j - 1])
                    if longer is not None and shorter is not None and longer - shorter > val:
                        cuts.add(j)
                if backward and i > 0:
                    longer, shorter = self.before(tokens[i:j]), self.before(tokens[i + 1:j])
                    if longer is not None and shorter is not None and longer - shorter > val:
                        cuts.add(i)
        return cuts

    def ordinary(self, tokens, val, forward=True, backward=True):
        """B_ordinary. Boundaries as in `increase`."""
        tokens, n, cuts = list(tokens), len(tokens), set()
        for i in range(n):
            for j in range(i + 1, min(n, i + self.longest) + 1):
                if forward and j < n:
                    here = self.after(tokens[i:j])
                    if here is not None and here > val:
                        cuts.add(j)
                if backward and i > 0:
                    here = self.before(tokens[i:j])
                    if here is not None and here > val:
                        cuts.add(i)
        return cuts


def pieces(tokens, cuts):
    """The stretches `cuts` divide `tokens` into, as (first, after last)."""
    edges = [0] + sorted(cuts) + [len(tokens)]
    return list(zip(edges, edges[1:]))
