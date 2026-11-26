"""Can entropy keep a rule from being one rule for a whole sentence? Five measurements on the dialogue probe.

    .venv/bin/python -I experiments/entropy_probe.py --data ../sgd-data --save out.json
    .venv/bin/python -I experiments/entropy_probe.py --data ../sgd-data --only edges cuts parts     seconds, no KATO
    .venv/bin/python -I experiments/entropy_probe.py --data ../sgd-data --only kato     about 45 minutes

KATO_REPO must name a checkout of KATO for `evidence` and `kato`.

The data and the way a sentence is judged are those of sgd_probe.py: 3,873 user sentences, 1,388
marked values ("slots"), and a value counts as found when it is exactly one variable.

evidence   Spell's loop on KATO as before, and again with KATO's own weight of evidence as a floor
           on joining a template (hpcrd/templates.py, `evidence`). The weight of evidence is the
           `bayesian_likelihood` KATO returns with every prediction: how much better than chance the
           pattern explains what was observed, in bits.
edges      Is the entropy of what follows a word higher where a marked value starts than inside
           one, and the entropy of what precedes a word higher where a value ends?
cuts       Two published rules for cutting by that entropy (experiments/branching.py): how many
           marked values come out as exactly one piece, against what cutting at random at the same
           rate would give.
placeholders   What stood at each placeholder of Spell's templates at the end of the run: how many
           different things, and whether Spell's own rule for taking a template apart (Du and Li
           2019, section 3.5: fewer than 8 different tokens at a placeholder, none with a digit)
           would apply.
parts      Rules for parts of sentences, in the probe's own measure. Spell's loop on the pieces
           instead of on the words; and the smallest rule with a variable there is, two words with a
           piece between them (Mintz 2003, https://doi.org/10.1016/S0010-0277(03)00140-9, whose
           frame holds one word): the piece is a variable when those two words have stood around
           other pieces before.
kato       The question of `edges`, asked of KATO: the entropy of the next-event distribution a KATO
           node returns (`future_potentials` and `ends_here`), the node having learned the earlier
           sentences whole.

Everything is "as it arrived" unless a line says otherwise: a sentence is cut and judged with what
was learned from the sentences before it, and learned afterwards.

A threshold is picked on the first half of the sentences and the second half is reported beside
the whole, because the picking uses the marked values.
"""
import argparse
import json
import math
import os
import pathlib
import sys
import time
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))       # run with -I: the script reads downloaded files
os.environ.setdefault('LOG_LEVEL', 'ERROR')

from experiments.baselines import Spell, gaps, score  # noqa: E402
from experiments.branching import Branching, pieces  # noqa: E402
from experiments.sgd_probe import HERE, sentences  # noqa: E402

KINDS = ('time', 'city', 'cuisine', 'date', 'restaurant_name', 'title')
VALS = (2.5, 3.0, 3.5, 4.0, 4.5, 5.0)
FRAMES = ((2, 1), (5, 3), (10, 5), (20, 8))     # (times the two words were seen around a piece, other pieces seen there)


def auc(positives, negatives):
    """The chance that a positive scores above a negative, a tie counting half. 0.5: no better than
    a coin. None when either side is empty."""
    if not positives or not negatives:
        return None
    ranked = sorted([(value, 1) for value in positives] + [(value, 0) for value in negatives])
    rank_sum, i = 0.0, 0
    while i < len(ranked):
        j = i
        while j < len(ranked) and ranked[j][0] == ranked[i][0]:
            j += 1
        rank_sum += (i + 1 + j) / 2 * sum(label for _value, label in ranked[i:j])     # the mean rank of the tie
        i = j
    return (rank_sum - len(positives) * (len(positives) + 1) / 2) / (len(positives) * len(negatives))


def place(slots, boundary):
    """Where a boundary inside a sentence stands against the marked values: ({'start', 'end', 'inside'}
    or {'other'}, the kinds of the values concerned)."""
    labels, kinds = set(), set()
    for kind, first, after in slots:
        for label, here in (('start', boundary == first), ('end', boundary == after), ('inside', first < boundary < after)):
            if here:
                labels.add(label)
                kinds.add(kind)
    return labels or {'other'}, kinds


def mean(values):
    return sum(values) / len(values) if values else None


def part(some, whole):
    return round(some / whole, 3) if whole else None


def rounded(value, digits=3):
    return None if value is None else round(value, digits)


# -- edges ------------------------------------------------------------------------------------
def edge_rows(data, earlier=True):
    """One row per boundary inside a sentence: (labels, kinds, entropy of what follows the word
    before it, entropy of what precedes the word after it). An entropy is None when the word was
    never seen."""
    counts = Branching(longest=1)
    if not earlier:
        for tokens, _slots in data:
            counts.learn(tokens)
    rows = []
    for tokens, slots in data:
        for boundary in range(1, len(tokens)):
            labels, kinds = place(slots, boundary)
            rows.append((labels, kinds, counts.after(tokens[boundary - 1:boundary]), counts.before(tokens[boundary:boundary + 1])))
        if earlier:
            counts.learn(tokens)
    return rows


def edge_table(rows, forward=2, backward=3):
    """Means and AUCs. A word never seen gives no entropy; it is scored 0, as a rule that cuts on
    high entropy would treat it."""
    def take(label, column, kind=None, only=False):
        return [row[column] or 0.0 for row in rows
                if (row[0] == {label} if only else label in row[0]) and (kind is None or kind in row[1])]
    out = {'boundaries': len(rows), 'where a word was never seen': sum(1 for row in rows if row[forward] is None or row[backward] is None)}
    for name, column, edge in (('what follows, at a value\'s start', forward, 'start'), ('what precedes, at a value\'s end', backward, 'end')):
        at, inside, other = take(edge, column), take('inside', column, only=True), take('other', column, only=True)
        out[name] = {'mean bits at the edge': rounded(mean(at), 2), 'mean bits inside a value': rounded(mean(inside), 2),
                     'mean bits elsewhere': rounded(mean(other), 2), 'edges': len(at),
                     'AUC, edge against inside a value': rounded(auc(at, inside)), 'AUC, edge against elsewhere': rounded(auc(at, other)),
                     'AUC by kind, edge against inside': {kind: rounded(auc(take(edge, column, kind), take('inside', column, kind, only=True)))
                                                          for kind in KINDS}}
    return out


# -- cuts -------------------------------------------------------------------------------------
def cut_all(data, rule, earlier=True, longest=6, **settings):
    """The boundaries `rule` ('increase' or 'ordinary') puts in every sentence."""
    counts = Branching(longest)
    if not earlier:
        for tokens, _slots in data:
            counts.learn(tokens)
    out = []
    for tokens, _slots in data:
        out.append(getattr(counts, rule)(tokens, **settings))
        if earlier:
            counts.learn(tokens)
    return out


def cut_score(data, cuts, start=0):
    """How the cuts fall on the marked values, over the sentences from `start` on."""
    data, cuts = data[start:], cuts[start:]
    inside_sentences = sum(len(tokens) - 1 for tokens, _slots in data)
    made = sum(len(c) for c in cuts)
    rate = made / inside_sentences if inside_sentences else 0.0
    exact, by_chance, by_kind, of_kind = 0, 0.0, Counter(), Counter()
    edges, edges_cut, within, within_cut = 0, 0, 0, 0
    for (tokens, slots), here in zip(data, cuts):
        for kind, first, after in slots:
            need = [b for b in (first, after) if 0 < b < len(tokens)]   # an end of the sentence is given
            inner = range(first + 1, after)
            found = all(b in here for b in need) and not any(b in here for b in inner)
            exact += found
            by_kind[kind] += found
            of_kind[kind] += 1
            by_chance += rate ** len(need) * (1 - rate) ** len(inner)
            edges += len(need)
            edges_cut += sum(1 for b in need if b in here)
            within += len(inner)
            within_cut += sum(1 for b in inner if b in here)
    values = sum(of_kind.values())
    return {'boundaries cut': round(rate, 3), 'values': values, 'values that are exactly one piece': exact,
            'share': part(exact, values), 'share by chance at that rate': part(by_chance, values),
            'value edges cut': part(edges_cut, edges), 'boundaries inside a value cut': part(within_cut, within),
            'share by kind': {kind: part(by_kind[kind], of_kind[kind]) for kind in sorted(of_kind)}}


# -- parts ------------------------------------------------------------------------------------
def spell_on_pieces(data, cuts, tau=0.5):
    """Spell's loop with every piece as one symbol. Returns (the variables of each sentence as it
    arrived, the same at the end), as token spans."""
    units, places = [], []
    for (tokens, _slots), here in zip(data, cuts):
        spans = pieces(tokens, here)
        places.append(spans)
        units.append([' '.join(tokens[a:b]) for a, b in spans])
    parser, arrived, member = Spell(tau), [], []
    for sequence in units:
        k, joined = parser.add(sequence)
        member.append(k)
        arrived.append(gaps(sequence, parser.constants(k)) if joined else [])
    final = [gaps(sequence, parser.constants(k)) if parser.sizes[k] > 1 else [] for sequence, k in zip(units, member)]

    def in_tokens(per_sentence):
        return [[(spans[a][0], spans[b - 1][1]) for a, b in found] for found, spans in zip(per_sentence, places)]
    return in_tokens(arrived), in_tokens(final)


def framed(data, cuts, seen=2, others=1):
    """A piece is a variable when the word before it and the word after it have stood around a
    piece at least `seen` times before, with at least `others` different pieces. The ends of a
    sentence count as words. Returns the variables of each sentence as it arrived."""
    around, out = {}, []
    for (tokens, _slots), here in zip(data, cuts):
        spans = pieces(tokens, here)
        frames = [(tokens[a - 1] if a > 0 else '<s>', tokens[b] if b < len(tokens) else '</s>') for a, b in spans]
        found = []
        for (a, b), frame in zip(spans, frames):
            fillers = around.get(frame)
            if fillers:
                total = sum(fillers.values())
                different = sum(1 for filler in fillers if filler != tuple(tokens[a:b]))
                if total >= seen and different >= others:
                    found.append((a, b))
        out.append(found)
        for (a, b), frame in zip(spans, frames):
            around.setdefault(frame, Counter())[tuple(tokens[a:b])] += 1
    return out


def span_score(data, spans, start=0):
    """The probe's measure for variables given as spans, over the sentences from `start` on."""
    slot_side, var_side = score(data[start:], spans[start:], list(range(len(data) - start)))
    slots, variables = sum(slot_side.values()), sum(var_side.values())
    exact = slot_side.get('one VAR, exactly', 0)
    return {'values': slots, 'values that are exactly one variable': exact, 'share': round(exact / slots, 3),
            'values inside a longer variable': round(slot_side.get('inside a longer VAR', 0) / slots, 3),
            'variables marked': variables,
            'variables that are exactly a value': round(var_side.get('exactly a slot', 0) / variables, 3) if variables else None}


# -- placeholders -----------------------------------------------------------------------------
def placeholders(data, tau=0.5):
    """What stood at each placeholder of Spell's templates at the end of the run. A placeholder is
    the place between two neighbouring constants of a template (or before the first, or after the
    last). Only templates of two sentences or more, and placeholders filled in two of them or more."""
    from experiments.baselines import lcs_pairs
    parser, member = Spell(tau), []
    for tokens, _slots in data:
        member.append(parser.add(tokens)[0])
    held = {}       # (template, place) -> [(what stood there, it is exactly a marked value)]
    for (tokens, slots), k in zip(data, member):
        if parser.sizes[k] < 2:
            continue
        constants = parser.constants(k)
        anchors = [(-1, -1)] + lcs_pairs(tokens, constants) + [(len(tokens), len(constants))]
        for (i0, c0), (i1, _c1) in zip(anchors, anchors[1:]):
            if i1 - i0 > 1:
                held.setdefault((k, c0 + 1), []).append((tuple(tokens[i0 + 1:i1]), any((first, after) == (i0 + 1, i1) for _kind, first, after in slots)))
    rows = [fillers for _place, fillers in sorted(held.items()) if len(fillers) >= 2]

    def describe(group):
        different = sorted(len({filler for filler, _exact in fillers}) for fillers in group)
        lengths = sorted(sum(len(filler) for filler, _exact in fillers) / len(fillers) for fillers in group)
        few = sum(1 for fillers in group if len({filler for filler, _exact in fillers}) < 8
                  and not any(c.isdigit() for filler, _exact in fillers for token in filler for c in token))
        return {'placeholders': len(group), 'fillers': sum(len(fillers) for fillers in group),
                'median number of different fillers': different[len(different) // 2] if different else None,
                'median of the mean filler length, in tokens': round(lengths[len(lengths) // 2], 2) if lengths else None,
                "placeholders Spell's split rule would take apart (fewer than 8 different fillers, no digit)": few}
    values = [fillers for fillers in rows if 2 * sum(1 for _filler, exact in fillers if exact) >= len(fillers)]
    others = [fillers for fillers in rows if 2 * sum(1 for _filler, exact in fillers if exact) < len(fillers)]
    return {'all': describe(rows), 'at least half of the fillers are exactly a marked value': describe(values), 'the others': describe(others)}


# -- evidence ---------------------------------------------------------------------------------
def run_reader(data, tau=0.5, evidence=None):
    """Spell's loop on KATO (hpcrd/templates.py), in-process. Returns the reader, each sentence's
    variables as it arrived and at the end, and KATO's weight of evidence for each join."""
    from hpcrd.templates import TemplateReader
    reader, arrived, member, bits = TemplateReader(tau, evidence=evidence), [], [], []
    for tokens, _slots in data:
        _name, joined, found = reader.read(tokens)
        member.append(reader.kind)
        arrived.append(found if joined else [])
        bits.append(reader.last['evidence'] if joined else None)
    reader.check()
    names = [reader.now(kind) if kind is not None else None for kind in member]
    sizes = Counter(name for name in names if name)
    final = [reader.gaps(tokens, name) if name and sizes[name] > 1 else [] for (tokens, _slots), name in zip(data, names)]
    fixed = {name: sum(1 for symbol in reader.template(name) if not reader.is_parameter(symbol)) for name in sizes}
    worn = {'rules with at most two fixed words, holding two sentences or more': sum(1 for name in sizes if fixed[name] <= 2 and sizes[name] > 1),
            'sentences under them': sum(sizes[name] for name in sizes if fixed[name] <= 2 and sizes[name] > 1),
            # numbers only: the results file holds no text from the data. `shown` is for the screen.
            'most-used rules at the end (sentences, fixed words, variables)': [], }
    shown = []
    for name, count in sorted(sizes.items(), key=lambda item: (-item[1], item[0]))[:8]:
        template = reader.template(name)
        worn['most-used rules at the end (sentences, fixed words, variables)'].append([count, fixed[name], len(template) - fixed[name]])
        shown.append(f"{count} sentences: " + ' '.join('*' if reader.is_parameter(symbol) else symbol for symbol in template))
    run_reader.shown = shown
    return reader, arrived, final, bits, worn


def evidence_part(data, rules=False):
    out = {}
    for name, floor in (("Spell's loop on KATO", None), ('the same, joining only above 0 bits of evidence', 0.0)):
        began = time.perf_counter()
        reader, arrived, final, bits, worn = run_reader(data, evidence=floor)
        joins = [b for b in bits if b is not None]
        result = {'seconds': round(time.perf_counter() - began, 1), 'sentences that joined a rule': len(joins),
                  'rules at the end': len(reader.node.patterns) - len(reader.node.retired),
                  'as it arrived': span_score(data, arrived), 'at the end': span_score(data, final), **worn}
        if floor is None:
            low = [k for k, b in enumerate(bits) if b is not None and b <= 0]
            high = [k for k, b in enumerate(bits) if b is not None and b > 0]
            result['joins by evidence'] = {
                'at or below 0 bits': len(low), 'above 0 bits': len(high),
                'median bits': round(sorted(joins)[len(joins) // 2], 2),
                'values found exactly in joins at or below 0 bits': exact_in(data, arrived, low),
                'values found exactly in joins above 0 bits': exact_in(data, arrived, high)}
        out[name] = result
        print(f"  {name:50s} {show(result['as it arrived'])} | at the end {show(result['at the end'])} | {result['seconds']} s", flush=True)
        if rules:
            for text in run_reader.shown:
                print('        ' + text)
    return out


def exact_in(data, spans, which):
    return sum(1 for k in which for _kind, first, after in data[k][1] if (first, after) in spans[k])


def show(result):
    precise = result['variables that are exactly a value']
    return (f"{result['values that are exactly one variable']:4d} ({100 * result['share']:4.1f}%) exact, "
            f"{result['variables marked']:5d} variables, {'-' if precise is None else f'{100 * precise:4.1f}%'} of them a value")


# -- kato -------------------------------------------------------------------------------------
def kato_entropy(result):
    """The entropy, in bits, of the next-event distribution KATO returned: the probabilities of
    `future_potentials` and `ends_here`, which add up to 1. None when KATO predicted nothing."""
    shares = [entry['probability'] for entry in result['future_potentials']]
    if result['ends_here']:
        shares.append(result['ends_here'])
    shares = sorted(share for share in shares if share > 0)
    if not shares:
        return None
    bits = 0.0
    for share in shares:
        bits -= share * math.log2(share)
    return bits + 0.0


def kato_part(data, contexts=(1, 2, 0)):
    """A KATO node learns each sentence whole, after the sentence was asked about. At every boundary
    it is shown the `context` words before it (0: the sentence so far) and its next-event
    distribution is read. Beside it, the count of what followed the one word before."""
    from hpcrd.kato_node import Node
    # max_predictions does not touch the distribution: KATO scores every candidate before it cuts the list (and a service takes at most 10000)
    node, counts, rows = Node('sentences', recall_threshold=0.1, max_predictions=10000), Branching(longest=1), []
    began = time.perf_counter()
    for tokens, slots in data:
        for boundary in range(1, len(tokens)):
            labels, _kinds = place(slots, boundary)
            mine = [kato_entropy(node.predict([[t] for t in (tokens[:boundary] if context == 0 else tokens[max(0, boundary - context):boundary])]))
                    for context in contexts]
            rows.append((labels, counts.after(tokens[boundary - 1:boundary]), mine))
        if len(tokens) >= 2:        # KATO does not learn a pattern of one symbol
            node.learn([[t] for t in tokens])
        counts.learn(tokens)
    out = {'sentences': len(data), 'boundaries': len(rows), 'predictions asked': node.predicts, 'seconds': round(time.perf_counter() - began, 1)}

    def table(read):
        at = [read(row) or 0.0 for row in rows if 'start' in row[0]]
        inside = [read(row) or 0.0 for row in rows if row[0] == {'inside'}]
        other = [read(row) or 0.0 for row in rows if row[0] == {'other'}]
        return {'mean bits at a value\'s start': rounded(mean(at), 2), 'mean bits inside a value': rounded(mean(inside), 2),
                'mean bits elsewhere': rounded(mean(other), 2), 'AUC, start against inside a value': rounded(auc(at, inside)),
                'AUC, start against elsewhere': rounded(auc(at, other)), 'boundaries with nothing to go on': sum(1 for row in rows if read(row) is None)}
    out['counts of what followed the word before'] = table(lambda row: row[1])
    for index, context in enumerate(contexts):
        name = 'KATO, shown the sentence so far' if context == 0 else f"KATO, shown the {context} word{'s' if context > 1 else ''} before"
        out[name] = table(lambda row, index=index: row[2][index])
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', required=True)
    parser.add_argument('--limit', type=int, default=0, help='only the first N sentences')
    parser.add_argument('--only', nargs='*', default=['evidence', 'edges', 'cuts', 'parts', 'placeholders'],
                        help='evidence, edges, cuts, parts, placeholders, kato (kato is slow and is not run unless named)')
    parser.add_argument('--rules', action='store_true', help='evidence: print the most-used rules of each run (they are not saved)')
    parser.add_argument('--save')
    args = parser.parse_args()
    data_dir = pathlib.Path(args.data).resolve()
    if HERE.parent in data_dir.parents or data_dir == HERE.parent:
        raise SystemExit("keep the data outside the repository")
    data, _aside = sentences(data_dir)
    if args.limit:
        data = data[:args.limit]
    half = len(data) // 2
    saved = {'sentences': len(data), 'values': sum(len(slots) for _tokens, slots in data), 'second half starts at sentence': half}
    print(json.dumps(saved))

    def keep():
        if args.save:
            pathlib.Path(args.save).write_text(json.dumps(saved, indent=1, sort_keys=True) + '\n')

    if 'edges' in args.only:
        print('\nedges: entropy with one word of context')
        saved['edges'] = {}
        for name, earlier in (('counts from the sentences before', True), ('counts from every sentence', False)):
            table = saved['edges'][name] = edge_table(edge_rows(data, earlier))
            for side in ("what follows, at a value's start", "what precedes, at a value's end"):
                t = table[side]
                print(f"  {name:34s} {side:34s} {t['mean bits at the edge']:5.2f} bits at the edge, {t['mean bits inside a value']:5.2f} inside a value, "
                      f"{t['mean bits elsewhere']:5.2f} elsewhere | AUC against inside {t['AUC, edge against inside a value']:.3f}, against elsewhere {t['AUC, edge against elsewhere']:.3f}")
        keep()

    best = None
    if 'cuts' in args.only or 'parts' in args.only:
        print('\ncuts: marked values that come out as exactly one piece')
        saved['cuts'] = {}
        runs = [('B_increase, val 0', 'increase', dict(val=0.0))] + [(f'B_ordinary, val {val}', 'ordinary', dict(val=val)) for val in VALS]
        made = {}
        for earlier in (True, False):
            source = 'counts from the sentences before' if earlier else 'counts from every sentence'
            for name, rule, settings in runs:
                cuts = cut_all(data, rule, earlier, **settings)
                whole, first, second = cut_score(data, cuts), cut_score(data[:half], cuts[:half]), cut_score(data, cuts, half)
                saved['cuts'][f"{name}, {source}"] = {'all sentences': whole, 'first half': first, 'second half': second}
                if earlier:
                    made[name] = (cuts, first['share'], settings)
                print(f"  {name:20s} {source:34s} cuts {100 * whole['boundaries cut']:5.1f}% | exactly one piece {whole['values that are exactly one piece']:4d} "
                      f"({100 * whole['share']:4.1f}%), by chance {100 * whole['share by chance at that rate']:4.1f}% | second half "
                      f"{100 * second['share']:4.1f}%, by chance {100 * second['share by chance at that rate']:4.1f}%", flush=True)
        best = max((name for name in made if name.startswith('B_ordinary')), key=lambda name: (made[name][1], name))
        saved['cuts']['threshold picked on the first half'] = best
        print(f"  picked on the first half: {best}")
        keep()

    if 'parts' in args.only:
        print('\nparts: values that are exactly one variable, as the sentence arrived')
        saved['parts'] = {}
        cuts = made[best][0]
        words = [set(range(1, len(tokens))) for tokens, _slots in data]
        rows = [("Spell's loop on words", spell_on_pieces(data, words)[0]),
                (f"Spell's loop on pieces ({best})", spell_on_pieces(data, cuts)[0])]
        rows += [(f"two words around a piece, seen {seen} times with {others} other piece{'s' if others > 1 else ''}", framed(data, cuts, seen, others))
                 for seen, others in FRAMES]
        rows += [(f"two words around one word, seen {seen} times with {others} other word{'s' if others > 1 else ''}", framed(data, words, seen, others))
                 for seen, others in FRAMES[:2]]
        for name, spans in rows:
            saved['parts'][name] = {'all sentences': span_score(data, spans), 'second half': span_score(data, spans, half)}
            print(f"  {name:66s} {show(saved['parts'][name]['all sentences'])} | second half {show(saved['parts'][name]['second half'])}", flush=True)
        keep()

    if 'placeholders' in args.only:
        print("\nplaceholders: what stood at the placeholders of Spell's templates at the end")
        saved['placeholders'] = placeholders(data)
        for name, table in saved['placeholders'].items():
            print(f"  {name:52s} {table}")
        keep()

    if 'evidence' in args.only:
        print("\nevidence: KATO's weight of evidence as a floor on joining a rule")
        saved['evidence'] = evidence_part(data, args.rules)
        keep()

    if 'kato' in args.only:
        print("\nkato: the entropy of KATO's own next-event distribution")
        saved['kato'] = kato_part(data)
        for name, table in saved['kato'].items():
            if isinstance(table, dict):
                print(f"  {name:42s} {table}")
        keep()


if __name__ == '__main__':
    sys.exit(main())
