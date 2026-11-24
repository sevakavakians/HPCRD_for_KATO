"""A first probe on annotated text: do VAR spans fall on annotated slot spans?

Data: user turns of the Schema-Guided Dialogue set (Rastogi et al. 2020, arXiv:1909.05855),
CC BY-SA 4.0, https://github.com/google-research-datasets/dstc8-schema-guided-dialogue.
The files are fetched from that host at run time, pinned by commit and sha256
(sgd_pins.json), and kept out of this repository. Results hold numbers only.

    ./run.sh experiments/sgd_probe.py --data ../sgd-data --fetch          every configuration
    ./run.sh experiments/sgd_probe.py --data ../sgd-data --only 5 --rules 12
    ./run.sh experiments/sgd_probe.py --data ../sgd-data --limit 500      the first 500 sentences

What is read: the user's utterances, in file, dialogue and turn order. Tokens are words and
punctuation marks, lower-cased. A sentence ends after `.`, `?` or `!`. One sentence is one
sequence. The annotation gives character spans for non-categorical slots only (a city, a
time, a title), so a VAR on a categorical value (a number of seats) counts here as a VAR
with no annotated slot. That makes the slot-side numbers firm and the VAR-side numbers a floor.

In-process (hpcrd.kato_node). Nothing here goes through KATO's API.
"""
import argparse
import hashlib
import json
import pathlib
import re
import sys
import time
import urllib.request
from collections import Counter

from hpcrd.modeler import VAR, Modeler, Settings
from hpcrd.show import digest

HERE = pathlib.Path(__file__).resolve().parent
PINS = json.loads((HERE / 'sgd_pins.json').read_text())
TOKEN = re.compile(r"\w+|[^\w\s]")
ENDS = ('.', '?', '!')

SEQ = dict(span='sequence', slots='gap', values='sequence', unexplained='break')
CONFIGS = [
    ('windows of 7, one VAR per position, 0.5 (round 1)',
     dict(span='stream', window=7, recall_threshold=0.5, slots='position', unexplained='break')),
    ('windows of 7, one VAR per gap, 0.5',
     dict(span='stream', window=7, recall_threshold=0.5, slots='gap', unexplained='break')),
    ('sentences, one VAR per position, 0.6',
     dict(SEQ, slots='position', values='name', recall_threshold=0.6)),
    ('sentences, one VAR per gap, all readings, 0.4', dict(SEQ, recall_threshold=0.4)),
    ('sentences, one VAR per gap, all readings, 0.5', dict(SEQ, recall_threshold=0.5)),
    ('sentences, one VAR per gap, all readings, 0.6', dict(SEQ, recall_threshold=0.6)),
    ('sentences, one VAR per gap, all readings, 0.7', dict(SEQ, recall_threshold=0.7)),
    ('sentences, one VAR per gap, all readings, 0.8', dict(SEQ, recall_threshold=0.8)),
    ('sentences, one VAR per gap, nearest, 0.4', dict(SEQ, recall_threshold=0.4, fold='nearest')),
    ('sentences, one VAR per gap, nearest, 0.5', dict(SEQ, recall_threshold=0.5, fold='nearest')),
    ('sentences, one VAR per gap, nearest, 0.6', dict(SEQ, recall_threshold=0.6, fold='nearest')),
    ('sentences, one VAR per gap, nearest, 0.7', dict(SEQ, recall_threshold=0.7, fold='nearest')),
    ('sentences, one VAR per gap, all readings, 0.5, support 2', dict(SEQ, recall_threshold=0.5, min_support=2)),
    ('sentences, one VAR per gap, all readings, 0.6, inside', dict(SEQ, recall_threshold=0.6, inside=True)),
    ('sentences, per gap, nearest 0.5, rules read first 0.4', dict(SEQ, recall_threshold=0.5, fold='nearest', topdown=True, rule_threshold=0.4)),
    ('sentences, per gap, nearest 0.5, rules read first 0.5', dict(SEQ, recall_threshold=0.5, fold='nearest', topdown=True, rule_threshold=0.5)),
    ('sentences, per gap, nearest 0.5, rules read first 0.6', dict(SEQ, recall_threshold=0.5, fold='nearest', topdown=True, rule_threshold=0.6)),
    ('sentences, per gap, nearest 0.6, rules read first 0.5', dict(SEQ, recall_threshold=0.6, fold='nearest', topdown=True, rule_threshold=0.5)),
    ('sentences, per gap, nearest 0.7, rules read first 0.5', dict(SEQ, recall_threshold=0.7, fold='nearest', topdown=True, rule_threshold=0.5)),
    ('sentences, per gap, all 0.6, rules read first 0.5', dict(SEQ, recall_threshold=0.6, topdown=True, rule_threshold=0.5)),
    ('sentences, per gap, all 0.7, rules read first 0.5', dict(SEQ, recall_threshold=0.7, topdown=True, rule_threshold=0.5)),
    ('sentences, per gap, nearest 0.5, rules first 0.5, inside', dict(SEQ, recall_threshold=0.5, fold='nearest', topdown=True, rule_threshold=0.5, inside=True)),
    ('sentences, per gap, nearest 0.5, inside', dict(SEQ, recall_threshold=0.5, fold='nearest', inside=True)),
    ("sentences, Spell's loop as the outer loop, tau 0.5", dict(SEQ, loop='templates', tau=0.5)),
    ("sentences, Spell's loop as the outer loop, tau 0.5, inside", dict(SEQ, loop='templates', tau=0.5, inside=True)),
]


def fetch(data):
    """Each pinned file from its original host, checked against its sha256."""
    for path, pin in PINS['files'].items():
        target = data / path
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            url = f"https://raw.githubusercontent.com/{PINS['source'].split('github.com/')[1]}/{PINS['commit']}/{path}"
            with urllib.request.urlopen(url, timeout=120) as response:
                target.write_bytes(response.read())
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        if digest != pin['sha256']:
            raise SystemExit(f"{path}: sha256 {digest} is not the pinned {pin['sha256']}")


def sentences(data):
    """[(tokens, [(slot name, first token, token after the last)])], and what was set aside."""
    out, aside = [], Counter()
    for path in sorted(PINS['files']):
        for dialogue in json.loads((data / path).read_text()):
            for turn in dialogue['turns']:
                if turn['speaker'] != 'USER':
                    continue
                aside['user turns'] += 1
                found = [(m.group().lower(), m.start(), m.end()) for m in TOKEN.finditer(turn['utterance'])]
                cut, current = [], []
                for token in found:
                    current.append(token)
                    if token[0] in ENDS:
                        cut.append(current)
                        current = []
                if current:
                    cut.append(current)
                spans = sorted({(s['slot'], s['start'], s['exclusive_end'])
                                for frame in turn['frames'] for s in frame['slots']})
                aside['slot spans'] += len(spans)
                placed = set()
                for sentence in cut:
                    slots = []
                    for span in spans:
                        _name, start, end = span
                        if sentence[0][1] <= start and end <= sentence[-1][2]:
                            inside = [i for i, (_t, a, b) in enumerate(sentence) if a < end and b > start]
                            slots.append((span[0], inside[0], inside[-1] + 1))
                            placed.add(span)
                    out.append(([t for t, _a, _b in sentence], slots))
                aside['slot spans cut by a sentence end'] += len(spans) - len(placed)
    return out, aside


def leaves(lo, hi, var, info):
    """A VAR's span, or, when the VAR's value was found to be made of parts, the spans of the
    slots among those parts (and so on down)."""
    if not info or not info['rule']:
        return [(lo, hi, var)]
    out = []
    for part in info['parts']:
        if part['kind'] == 'V':
            out += leaves(lo + part['lo'], lo + part['hi'], part['var'], part.get('inside'))
    return out


def judge(result, slots, deep=False):
    """One sentence: its VAR spans against its annotated slot spans."""
    spans, emissions, recognised = [], 0, 0
    if result:
        for part in result['parts']:
            if not part['rule']:
                continue
            emissions += 1
            recognised += part['rule_frequency'] > 1
            for item, symbol in zip(part['items'], part['sequence']):
                if item['kind'] == 'V' and item['hi'] > item['lo']:     # a VAR with nothing in this sentence has no span
                    spans += leaves(item['lo'], item['hi'], symbol, item.get('inside') if deep else None)
    covered = set()
    for a, b, _var in spans:
        covered.update(range(a, b))
    slot_side, var_side, pairs = Counter(), Counter(), []
    for name, lo, hi in slots:
        exact = [var for a, b, var in spans if (a, b) == (lo, hi)]
        touching = [(a, b) for a, b, _var in spans if a < hi and b > lo]
        if exact:
            slot_side['one VAR, exactly'] += 1
            pairs.append((exact[0], name))
        elif any(a <= lo and hi <= b for a, b in touching):
            slot_side['inside a longer VAR'] += 1
        elif touching and all(lo <= a and b <= hi for a, b in touching) and set(range(lo, hi)) <= covered:
            slot_side['tiled by several VARs'] += 1
        elif touching:
            slot_side['partly in a VAR'] += 1
        elif emissions:
            slot_side['constant in a rule, or dropped'] += 1
        else:
            slot_side['no rule for the sentence'] += 1
    for a, b, _var in spans:
        if any((lo, hi) == (a, b) for _n, lo, hi in slots):
            var_side['exactly a slot'] += 1
        elif any(a <= lo and hi <= b for _n, lo, hi in slots):
            var_side['longer than a slot'] += 1
        elif any(lo <= a and b <= hi for _n, lo, hi in slots):
            var_side['part of a slot'] += 1
        elif any(a < hi and b > lo for _n, lo, hi in slots):
            var_side['across a slot edge'] += 1
        else:
            var_side['no annotated slot'] += 1
    return slot_side, var_side, pairs, emissions, recognised


def run(settings, data, rules=0):
    m = Modeler(Settings(**settings), trace=False)
    starts, results, position = {}, {}, 0
    began = time.perf_counter()

    def take(stretches):
        for result in stretches:
            results[starts[result['stretch'][0]]] = result

    for k, (tokens, _slots) in enumerate(data):
        starts[position] = k
        for token in tokens:
            take(m.feed(token).get('stretches', ()))
        step = m.cut()
        if step:
            take(step['stretches'])
        position += len(tokens)
    take(m.finish())
    seconds = time.perf_counter() - began

    third = len(data) - len(data) // 3
    totals = {'all': [Counter(), Counter(), 0, 0, 0, 0], 'last third': [Counter(), Counter(), 0, 0, 0, 0]}
    pairs = []
    for k, (_tokens, slots) in enumerate(data):
        slot_side, var_side, found, emissions, recognised = judge(results.get(k), slots, settings.get('inside', False))
        pairs += found
        for key in ('all',) + (('last third',) if k >= third else ()):
            totals[key][0].update(slot_side)
            totals[key][1].update(var_side)
            totals[key][2] += 1
            totals[key][3] += emissions > 0
            totals[key][4] += emissions
            totals[key][5] += recognised
    by_var, by_slot = {}, {}
    for var, name in pairs:
        by_var.setdefault(var, Counter())[name] += 1
        by_slot.setdefault(name, Counter())[var] += 1
    out = {'seconds': round(seconds, 1)}
    for key, (slot_side, var_side, count, with_rule, emissions, recognised) in totals.items():
        out[key] = {'sentences': count, 'sentences with a rule': with_rule, 'rule instances': emissions,
                    'rule instances of a known rule': recognised,
                    'slots': dict(sorted(slot_side.items())), 'VARs': dict(sorted(var_side.items()))}
    frequencies = sorted((e['frequency'] for e in m.node1b.patterns.values()), reverse=True)
    out['nodes'] = {
        'node_0 patterns': len(m.node0.patterns),
        'node_0 stored symbols': sum(len(e['pattern_data']) for e in m.node0.patterns.values()),
        'node_1a chunks': len(m.node1a.patterns),
        'node_1b rules': len(frequencies),
        'node_1b rules seen again': sum(1 for f in frequencies if f > 1),
        'node_1b top frequencies': frequencies[:5],
        'VAR ids': m.var_count,
        'node_2b patterns': len(m.node2b.patterns),
    }
    if m.reader is not None:
        out['nodes']['templates stored'] = len(m.reader.node.patterns)
        out['nodes']['templates live'] = len(m.reader.node.patterns) - len(m.reader.node.retired)
        out['nodes']['node_1b rules live'] = len(m.node1b.patterns) - len(m.node1b.retired)
    nodes = [('node_0', m.node0), ('node_1a', m.node1a), ('node_1b', m.node1b), ('node_2a', m.node2a), ('node_2b', m.node2b)]
    nodes += [('node_1t', m.node1t)] if m.node1t is not None else []
    nodes += [('templates', m.reader.node)] if m.reader is not None else []
    out['nodes']['digest'] = digest(nodes)      # every pattern of every node: name, frequency, retired
    out['ids'] = {
        'VAR ids that hold exactly a slot': len(by_var),
        'of those, ids holding one slot name only': sum(1 for c in by_var.values() if len(c) == 1),
        'ids per slot name': {name: len(c) for name, c in sorted(by_slot.items())},
    }
    if rules:
        from hpcrd.show import seq
        top = sorted(m.node1b.patterns.values(), key=lambda e: (-e['frequency'], e['name']))[:rules]
        out['top rules'] = [f"f={e['frequency']}  " + seq([ev[0] for ev in e['pattern_data']], m.node1a) for e in top]
    return out, m


def rate(part, whole):
    return f"{100 * part / whole:5.1f}%" if whole else '    -'


def line(name, r):
    a = r['all']
    slots = sum(a['slots'].values())
    variables = sum(a['VARs'].values())
    late = r['last third']
    late_slots = sum(late['slots'].values())
    return (f"{name:58s} {rate(a['sentences with a rule'], a['sentences'])} "
            f"{rate(a['slots'].get('one VAR, exactly', 0), slots)} {rate(late['slots'].get('one VAR, exactly', 0), late_slots)} "
            f"{rate(a['slots'].get('inside a longer VAR', 0), slots)} "
            f"{rate(a['slots'].get('tiled by several VARs', 0), slots)} "
            f"{variables:6d} {rate(a['VARs'].get('exactly a slot', 0), variables)} "
            f"{rate(a['VARs'].get('no annotated slot', 0), variables)} "
            f"{r['nodes']['node_1b rules']:6d} {r['nodes']['node_1b rules seen again']:6d} "
            f"{rate(a['rule instances of a known rule'], a['rule instances'])} {r['nodes']['VAR ids']:6d} {r['seconds']:7.1f}")


HEADER = (f"{'configuration':58s} {'rule':>6s} {'exact':>6s} {'late':>6s} {'longer':>6s} {'tiled':>6s} "
          f"{'VARs':>6s} {'=slot':>6s} {'none':>6s} {'rules':>6s} {'again':>6s} {'known':>6s} {'ids':>6s} {'sec':>7s}")
LEGEND = """
rule    sentences that gave at least one rule
exact   annotated slot spans that are one VAR, exactly;  late: the same over the last third of the sentences
longer  slot spans inside a VAR that is longer than the slot;  tiled: slot spans covered by several VARs side by side
VARs    VAR spans in emitted rules;  =slot: those that are exactly a slot span;  none: those that touch no annotated span
rules   node_1b patterns;  again: those learned more than once;  known: rule instances that were a rule already learned
ids     VAR ids handed out;  sec: seconds, in-process
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', required=True, help='a directory outside the repository for the dataset files')
    parser.add_argument('--fetch', action='store_true', help='fetch missing files from the original host')
    parser.add_argument('--limit', type=int, default=0, help='only the first N sentences')
    parser.add_argument('--only', type=int, nargs='*', help='configuration numbers (from 0)')
    parser.add_argument('--rules', type=int, default=0, help='print the N most frequent rules of each run')
    parser.add_argument('--save', help='write the numbers to this JSON file')
    parser.add_argument('--joined', action='store_true',
                        help="keep 10:30, i'm and the like as one token (default: words and punctuation marks)")
    args = parser.parse_args()
    if args.joined:
        global TOKEN
        TOKEN = re.compile(r"\w+(?:[:'’.,]\w+)*|[^\w\s]")
    data_dir = pathlib.Path(args.data).resolve()
    if HERE.parent in data_dir.parents or data_dir == HERE.parent:
        raise SystemExit("keep the data outside the repository")
    if args.fetch:
        fetch(data_dir)
    data, aside = sentences(data_dir)
    if args.limit:
        data = data[:args.limit]
    lengths = sorted(len(tokens) for tokens, _ in data)
    described = {'tokens are': 'joined' if args.joined else 'words and punctuation marks',
                 'sentences': len(data), 'tokens': sum(lengths), 'median sentence length': lengths[len(lengths) // 2],
                 'slot spans in these sentences': sum(len(slots) for _, slots in data), **aside}
    print(json.dumps(described))
    print(HEADER)
    saved = {'data': described, 'pins': PINS, 'runs': {}}
    for index, (name, settings) in enumerate(CONFIGS):
        if args.only and index not in args.only:
            continue
        result, _m = run(settings, data, args.rules)
        print(line(f"{index:2d} {name}", result), flush=True)
        for text in result.pop('top rules', ()):
            print('        ' + text)
        saved['runs'][name] = {'settings': settings, **result}
        if args.save:       # after every run, so that a long batch can be read while it goes
            pathlib.Path(args.save).write_text(json.dumps(saved, indent=1, sort_keys=True) + '\n')
    print(LEGEND)


if __name__ == '__main__':
    sys.exit(main())
