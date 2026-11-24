"""Position-level reading of one KATO prediction, from its returned fields only.

Scope: every event holds exactly one symbol (this experiment's text setting).

KATO's matcher computes which pattern position each observed position was
matched to, and does not return it. With one symbol per event the returned
fields are enough to rebuild it:

    extras[i]  == []   <=>  STM position i was matched
    missing[j] == []   <=>  position j of `present` was matched
    the alignment is strictly increasing on both sides, so the k-th matched STM
    position pairs with the k-th matched position of `present`.

`read(prediction, stm)` returns one Reading: for each STM position, how this
one learned pattern accounts for it.

    ('M', q)        matched to pattern position q
    ('S', q, x)     substituted: aligned with pattern position q, which holds x.
                    Interior gap, as many `extras` as `missing`, position for position.
    ('E', q, x)     edge: an extra before the first / after the last match that lines
                    up with a position of `past` / `future` holding x
    ('I', q)        inserted: an extra inside the matched span with nothing opposite it;
                    q is the pattern position of the match before it
    ('U', n, m, q)  unequal gap: one of n extras standing against m missing (n != m, m > 0);
                    q is the pattern position of the match before the gap
    ('O',)          out of view: beyond the pattern's first or last event
"""
from typing import NamedTuple


class Reading(NamedTuple):
    name: str
    frequency: int
    pattern: list          # the learned pattern, one symbol per position
    offset_past: int       # len(past)
    relation: list         # one tuple per STM position (see module docstring)
    pairs: list            # [(pattern position, STM position)] matched, in order
    blocks: list           # [(pattern start, STM start, length)] maximal contiguous matches
    deletions: list        # [(STM position before, [pattern symbols skipped])] missing with no extra opposite


def flat(events):
    out = []
    for event in events:
        if len(event) != 1:
            raise ValueError(f"one symbol per event expected, got {event!r}")
        out.append(event[0])
    return out


def read(prediction, stm_events):
    stm = flat(stm_events)
    extras, missing = prediction['extras'], prediction['missing']
    past, present, future = prediction['past'], prediction['present'], prediction['future']
    pattern = flat(past) + flat(present) + flat(future)
    n = len(stm)
    s_pos = [i for i in range(n) if not extras[i]]
    p_pos = [len(past) + j for j in range(len(present)) if not missing[j]]
    if not (len(s_pos) == len(p_pos) == len(prediction['matches'])):
        raise ValueError("fields do not describe a one-symbol-per-event alignment")
    pairs = list(zip(p_pos, s_pos))
    relation = [None] * n
    for q, i in pairs:
        if pattern[q] != stm[i]:
            raise ValueError("matched positions hold different symbols")
        relation[i] = ('M', q)

    deletions = []
    for (q0, i0), (q1, i1) in zip(pairs, pairs[1:]):
        gap_s, gap_p = i1 - i0 - 1, q1 - q0 - 1
        if gap_s == 0 and gap_p > 0:
            deletions.append((i0, pattern[q0 + 1:q1]))
        for d in range(1, gap_s + 1):
            if gap_s == gap_p:
                relation[i0 + d] = ('S', q0 + d, pattern[q0 + d])
            elif gap_p == 0:
                relation[i0 + d] = ('I', q0)
            else:
                relation[i0 + d] = ('U', gap_s, gap_p, q0)

    q0, i0 = pairs[0]
    for d in range(1, i0 + 1):
        q = q0 - d
        relation[i0 - d] = ('E', q, pattern[q]) if q >= 0 else ('O',)
    q_last, i_last = pairs[-1]
    for d in range(1, n - i_last):
        q = q_last + d
        relation[i_last + d] = ('E', q, pattern[q]) if q < len(pattern) else ('O',)

    blocks = []
    for q, i in pairs:
        if blocks and blocks[-1][0] + blocks[-1][2] == q and blocks[-1][1] + blocks[-1][2] == i:
            blocks[-1] = (blocks[-1][0], blocks[-1][1], blocks[-1][2] + 1)
        else:
            blocks.append((q, i, 1))
    return Reading(prediction['name'], prediction['frequency'], pattern, len(past),
                   relation, pairs, blocks, deletions)
