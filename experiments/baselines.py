"""Two published log parsers on the probe of sgd_probe.py, judged the same way.

    ./run.sh experiments/baselines.py --data ../sgd-data [--limit 1200] [--save out.json]
    ./run.sh experiments/baselines.py --data ../sgd-data --sweep        Spell alone, over tau

Drain   He, Zhu, Zheng and Lyu (2017), https://doi.org/10.1109/ICWS.2017.13
        Run through the drain3 package (version 0.9.11 here), with its defaults and with a second
        similarity threshold. Nothing is masked. One wildcard per token position.
Spell   Du and Li (2016), https://doi.org/10.1109/ICDM.2016.0103
        Written here from the paper's description, because the published implementations work on
        log files. Not checked against the paper's own data. On the log benchmark it gives the
        accuracy of the benchmark's implementation without its two shortcuts on 13 of 16 systems
        and is within 0.008 on the others (experiments/log_benchmark.py). A line joins the message type whose
        template shares the longest common subsequence with it, when that subsequence is at least
        tau of the line's length (ties: the shorter template, then the older one); the template
        becomes that subsequence, with one `*` wherever either side had something else.

A third run is Spell's loop on KATO's own matcher (hpcrd/templates.py), in-process.

Both are streaming parsers built for machine-written logs. Here they read dialogue sentences, which
is outside what either was shown to do. A sentence is judged twice: against its template as it stood
when the sentence arrived (as the module is judged), and against the template at the end of the run.
"""
import argparse
import json
import pathlib
import sys
import time
from collections import Counter

from rapidfuzz.distance import LCSseq

from experiments.sgd_probe import HERE, judge, sentences

STAR = '*'


def lcs_pairs(a, b):
    """One longest common subsequence of a and b, as index pairs."""
    n, m = len(a), len(b)
    table = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            table[i][j] = table[i + 1][j + 1] + 1 if a[i] == b[j] else max(table[i + 1][j], table[i][j + 1])
    pairs, i, j = [], 0, 0
    while i < n and j < m:
        if a[i] == b[j]:
            pairs.append((i, j))
            i, j = i + 1, j + 1
        elif table[i + 1][j] >= table[i][j + 1]:
            i += 1
        else:
            j += 1
    return pairs


def gaps(tokens, constants):
    """Where `tokens` has something between the constants of a template: the line's parameters."""
    pairs = lcs_pairs(tokens, constants)
    anchors = [-1] + [i for i, _ in pairs] + [len(tokens)]
    return [(a + 1, b) for a, b in zip(anchors, anchors[1:]) if b - a > 1]


class Spell:
    def __init__(self, tau=0.5, star=STAR, star_matches=False):
        """`star_matches`: the placeholder is a token like any other when sequences are compared.
        The log benchmark's preprocessing puts placeholders into the lines themselves, and its
        reference implementation lets them match (experiments/log_benchmark.py)."""
        self.tau, self.star, self.star_matches = tau, star, star_matches
        self.templates = []     # token lists, the placeholder marking a parameter
        self.sizes = []

    def add(self, tokens):
        best, where = 0, None
        for k, template in enumerate(self.templates):
            constants = template if self.star_matches else [t for t in template if t != self.star]
            shared = LCSseq.similarity(tokens, constants)
            if shared > best or (shared == best and where is not None and len(template) < len(self.templates[where])):
                best, where = shared, k
        if where is None or best < self.tau * len(tokens):
            self.templates.append(list(tokens))
            self.sizes.append(1)
            return len(self.templates) - 1, False
        old = self.templates[where]
        pairs = lcs_pairs(tokens, old)
        new, last = [], (-1, -1)
        for i, j in pairs + [(len(tokens), len(old))]:
            for symbol in ([self.star] if i - last[0] > 1 or j - last[1] > 1 else []) + ([tokens[i]] if i < len(tokens) else []):
                if not (symbol == self.star and new and new[-1] == self.star):     # adjacent placeholders are one
                    new.append(symbol)
            last = (i, j)
        self.templates[where] = new
        self.sizes[where] += 1
        return where, True

    def constants(self, k):
        return [t for t in self.templates[k] if t != self.star]


def run_spell(data, tau):
    parser, online, member = Spell(tau), [], []
    for tokens, _slots in data:
        k, joined = parser.add(tokens)
        member.append(k)
        online.append((gaps(tokens, parser.constants(k)) if joined else [], joined))
    final = [gaps(tokens, parser.constants(k)) if parser.sizes[k] > 1 else []
             for (tokens, _slots), k in zip(data, member)]
    return online, final, member, parser.sizes


def run_spell_on_kato(data, tau):
    """The same loop on KATO's own matcher (hpcrd/templates.py), in-process."""
    from hpcrd.templates import PARAMETER, TemplateReader
    reader, online, member = TemplateReader(tau), [], []
    for tokens, _slots in data:
        _name, joined, found = reader.read(tokens)
        member.append(reader.kind)      # a line belongs to its message type, whatever its template becomes
        online.append((found if joined else [], joined))
    reader.check()
    member = [reader.now(kind) if kind is not None else None for kind in member]
    sizes = Counter(name for name in member if name)
    final = [reader.gaps(tokens, name) if name and sizes[name] > 1 else []
             for (tokens, _slots), name in zip(data, member)]
    run_spell_on_kato.last = reader
    return online, final, member, [sizes[k] for k in sorted(sizes)]


def run_drain(data, sim_th):
    from drain3 import TemplateMiner
    from drain3.template_miner_config import TemplateMinerConfig
    config = TemplateMinerConfig()
    config.drain_sim_th = sim_th
    config.profiling_enabled = False
    miner = TemplateMiner(config=config)
    online, member = [], []

    def wildcards(template, n):
        cells = template.split()
        if len(cells) != n:     # cannot happen: Drain groups lines of one length
            raise ValueError(template)
        return [(i, i + 1) for i, cell in enumerate(cells) if cell == '<*>']

    for tokens, _slots in data:
        out = miner.add_log_message(' '.join(tokens))
        member.append(out['cluster_id'])
        joined = out['change_type'] != 'cluster_created'
        online.append((wildcards(out['template_mined'], len(tokens)) if joined else [], joined))
    templates = {c.cluster_id: c.get_template() for c in miner.drain.clusters}
    sizes = Counter(member)
    final = [wildcards(templates[k], len(tokens)) if sizes[k] > 1 else []
             for (tokens, _slots), k in zip(data, member)]
    return online, final, member, [sizes[k] for k in sorted(sizes)]


def score(data, spans_per_sentence, member):
    slot_side, var_side = Counter(), Counter()
    for (tokens, slots), spans, k in zip(data, spans_per_sentence, member):
        items = [{'kind': 'V', 'lo': a, 'hi': b} for a, b in spans]
        result = {'parts': [{'rule': k, 'rule_frequency': 2, 'items': items,
                             'sequence': [f"{k}:{n}" for n in range(len(items))]}]} if items else None
        s, v, _pairs, _emissions, _known = judge(result, slots)
        slot_side.update(s)
        var_side.update(v)
    return slot_side, var_side


def describe(name, data, online, final, member, sizes, seconds):
    out = {'seconds': round(seconds, 1), 'templates': len(sizes), 'templates with two or more lines': sum(1 for s in sizes if s > 1),
           'lines that joined an existing template': sum(1 for _spans, joined in online if joined), 'lines': len(data)}
    for label, spans in (('as it arrived', [spans for spans, _ in online]), ('at the end', final)):
        slot_side, var_side = score(data, spans, member)
        out[label] = {'slots': dict(sorted(slot_side.items())), 'VARs': dict(sorted(var_side.items()))}
    return out


def rate(part, whole):
    return f"{100 * part / whole:5.1f}%" if whole else '    -'


def line(name, r):
    cells = []
    for label in ('as it arrived', 'at the end'):
        slots, variables = r[label]['slots'], r[label]['VARs']
        total, spans = sum(slots.values()), sum(variables.values())
        cells.append(f"{rate(slots.get('one VAR, exactly', 0), total)} {rate(slots.get('tiled by several VARs', 0), total)} "
                     f"{rate(slots.get('inside a longer VAR', 0), total)} {spans:6d} {rate(variables.get('exactly a slot', 0), spans)}")
    return (f"{name:34s} {r['templates']:6d} {r['templates with two or more lines']:6d} "
            f"{rate(r['lines that joined an existing template'], r['lines'])} | " + ' | '.join(cells) + f" | {r['seconds']:6.1f}")


HEADER = (f"{'parser':34s} {'templ':>6s} {'2+':>6s} {'joined':>6s} | {'exact':>6s} {'tiled':>6s} {'longer':>6s} {'VARs':>6s} {'=slot':>6s}"
          f" | {'exact':>6s} {'tiled':>6s} {'longer':>6s} {'VARs':>6s} {'=slot':>6s} | {'sec':>6s}")
LEGEND = """
templ   templates (message types);  2+: those holding two or more lines;  joined: lines that joined an existing template
first block: each line against its template as it stood when the line arrived;  second block: against the template at the end
exact   annotated slot spans that are one parameter, exactly;  tiled: covered by several parameters side by side
longer  slot spans inside a longer parameter;  VARs: parameter spans;  =slot: those that are exactly a slot span
"""


def sweep(data, save):
    """Spell alone over tau: what its one threshold trades. Lower, and more sentences join a template
    but the templates wear down and the slots end up inside longer parameters. Higher, and the
    parameters are tighter but most sentences that hold a slot have no template yet."""
    total = sum(len(slots) for _, slots in data)
    print(f"{'tau':>4s} {'templ':>6s} {'joined':>7s} | as it arrived: {'exact':>6s} {'longer':>6s} {'partly':>6s} {'const':>6s} {'none':>6s}"
          f" {'exact, of slots in a line with a template':>42s} | at the end: {'exact':>6s} {'longer':>6s} {'none':>6s}")
    saved = {}
    for tau in (0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8):
        began = time.perf_counter()
        online, final, member, sizes = run_spell(data, tau)
        r = describe(f"Spell, tau {tau}", data, online, final, member, sizes, time.perf_counter() - began)
        a, e = r['as it arrived']['slots'], r['at the end']['slots']
        covered = total - a.get('no rule for the sentence', 0)
        print(f"{tau:4.1f} {r['templates']:6d} {rate(r['lines that joined an existing template'], r['lines']):>7s} |"
              f"                {rate(a.get('one VAR, exactly', 0), total)} {rate(a.get('inside a longer VAR', 0), total)}"
              f" {rate(a.get('partly in a VAR', 0), total)} {rate(a.get('constant in a rule, or dropped', 0), total)}"
              f" {rate(a.get('no rule for the sentence', 0), total)} {rate(a.get('one VAR, exactly', 0), covered):>42s} |"
              f"             {rate(e.get('one VAR, exactly', 0), total)} {rate(e.get('inside a longer VAR', 0), total)}"
              f" {rate(e.get('no rule for the sentence', 0), total)}", flush=True)
        saved[f"Spell, tau {tau}"] = r
    if save:
        pathlib.Path(save).write_text(json.dumps(saved, indent=1, sort_keys=True) + '\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', required=True)
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--save')
    parser.add_argument('--sweep', action='store_true', help='Spell alone over tau, and nothing else')
    args = parser.parse_args()
    data_dir = pathlib.Path(args.data).resolve()
    if HERE.parent in data_dir.parents or data_dir == HERE.parent:
        raise SystemExit("keep the data outside the repository")
    data, _aside = sentences(data_dir)
    if args.limit:
        data = data[:args.limit]
    print(json.dumps({'sentences': len(data), 'slot spans': sum(len(slots) for _, slots in data)}))
    if args.sweep:
        return sweep(data, args.save)
    print(HEADER)
    saved = {}
    runs = [('Drain (drain3), threshold 0.4', run_drain, 0.4), ('Drain (drain3), threshold 0.6', run_drain, 0.6),
            ('Spell, tau 0.5', run_spell, 0.5), ('Spell, tau 0.7', run_spell, 0.7),
            ("Spell's loop on KATO, tau 0.5", run_spell_on_kato, 0.5), ("Spell's loop on KATO, tau 0.7", run_spell_on_kato, 0.7)]
    for name, function, setting in runs:
        began = time.perf_counter()
        online, final, member, sizes = function(data, setting)
        result = describe(name, data, online, final, member, sizes, time.perf_counter() - began)
        if function is run_spell_on_kato:
            reader = run_spell_on_kato.last
            result['kato'] = {'patterns stored': len(reader.node.patterns), 'retired': len(reader.node.retired),
                              'learns': reader.node.learns, 'predictions asked': reader.node.predicts,
                              'retired content that came back': reader.revived,
                              'edits that met another live template': reader.merged}
        print(line(name, result), flush=True)
        saved[name] = result
    print(LEGEND)
    if args.save:
        pathlib.Path(args.save).write_text(json.dumps(saved, indent=1, sort_keys=True) + '\n')


if __name__ == '__main__':
    sys.exit(main())
