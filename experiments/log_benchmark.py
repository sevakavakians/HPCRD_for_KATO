"""Spell's loop on KATO, held to the published log-parsing benchmark.

    .venv/bin/python -I experiments/log_benchmark.py --data ../loghub-data --fetch --save out.json

The benchmark: Zhu et al. (2019), "Tools and Benchmarks for Automated Log Parsing",
https://arxiv.org/abs/1811.03509. 2,000 sampled lines from each of 16 systems, templates labelled by
hand. A line is parsed correctly only if its template groups it with exactly the lines the labels do.

Data: the Loghub samples distributed with https://github.com/logpai/logparser (data/loghub_2k), from
the Loghub collection, https://github.com/logpai/loghub (Zhu, He, He, Liu and Lyu 2023,
https://arxiv.org/abs/2008.06448). Freely available for research or academic work under the LICENSE
OF LOGHUB. Fetched at run time, pinned by commit and sha256 (loghub_pins.json), kept out of this
repository. Run with -I: the script reads downloaded files.

Per-system settings (tau, Drain's threshold and depth, the preprocessing expressions) are the ones in
logparser's own benchmark scripts at the pinned commit. PUBLISHED is Table IV of the benchmark paper.

Eight parsers:
  reference   the benchmark's Spell, re-written here from logparser/Spell/Spell.py (Apache 2.0): a
              prefix tree, then a set-containment loop, then the longest common subsequence. It is
              here to check this harness against the published numbers.
  plain       the same without the prefix tree and the set-containment loop: what those two
              shortcuts add to, or take from, the published numbers.
  paper       Spell as its paper describes it (experiments/baselines.py): the subsequence step alone.
  lone        the same with the one rule KATO adds: a line of one token is a type of its own,
              because KATO does not learn a pattern of one symbol.
  on KATO     the same loop on KATO's matcher (hpcrd/templates.py), in-process.
  Drain       the drain3 package with the benchmark's threshold and depth, as a second check.
  rules       Drain as three rules on the loop Spell uses, without Drain's tree (DrainRules below):
              the same number of tokens, the same leading tokens, and the same token at enough positions.
  rules on KATO   the same three rules on KATO's matcher (hpcrd/templates.py, PositionReader), in-process.
"""
import argparse
import csv
import hashlib
import json
import os
import pathlib
import re
import sys
import time
import urllib.request
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault('LOG_LEVEL', 'ERROR')
PINS = json.loads((ROOT / 'experiments' / 'loghub_pins.json').read_text())
STAR = '<*>'

# system: (Spell tau, Drain threshold, Drain depth, preprocessing expressions)
SETTINGS = {
    'HDFS': (0.7, 0.5, 4, [r"blk_-?\d+", r"(\d+\.){3}\d+(:\d+)?"]),
    'Hadoop': (0.7, 0.5, 4, [r"(\d+\.){3}\d+"]),
    'Spark': (0.55, 0.5, 4, [r"(\d+\.){3}\d+", r"\b[KGTM]?B\b", r"([\w-]+\.){2,}[\w-]+"]),
    'Zookeeper': (0.7, 0.5, 4, [r"(/|)(\d+\.){3}\d+(:\d+)?"]),
    'BGL': (0.75, 0.5, 4, [r"core\.\d+"]),
    'HPC': (0.65, 0.5, 4, [r"=\d+"]),
    'Thunderbird': (0.5, 0.5, 4, [r"(\d+\.){3}\d+"]),
    'Windows': (0.7, 0.7, 5, [r"0x.*?\s"]),
    'Linux': (0.55, 0.39, 6, [r"(\d+\.){3}\d+", r"\d{2}:\d{2}:\d{2}"]),
    'Android': (0.95, 0.2, 6, [r"(/[\w-]+)+", r"([\w-]+\.){2,}[\w-]+",
                               r"\b(\-?\+?\d+)\b|\b0[Xx][a-fA-F\d]+\b|\b[a-fA-F\d]{4,}\b"]),
    'HealthApp': (0.5, 0.2, 4, []),
    'Apache': (0.6, 0.5, 4, [r"(\d+\.){3}\d+"]),
    'Proxifier': (0.85, 0.6, 3, [r"<\d+\ssec", r"([\w-]+\.)+[\w-]+(:\d+)?", r"\d{2}:\d{2}(:\d{2})*", r"[KGTM]B"]),
    'OpenSSH': (0.8, 0.6, 5, [r"(\d+\.){3}\d+", r"([\w-]+\.){2,}[\w-]+"]),
    'OpenStack': (0.9, 0.5, 5, [r"((\d+\.){3}\d+,?)+", r"/.+?\s", r"\d+"]),
    'Mac': (0.6, 0.7, 6, [r"([\w-]+\.){2,}[\w-]+"]),
}
PUBLISHED = {   # system: (Spell, Drain), Table IV
    'HDFS': (1.0, 0.998), 'Hadoop': (0.778, 0.948), 'Spark': (0.905, 0.920), 'Zookeeper': (0.964, 0.967),
    'OpenStack': (0.764, 0.733), 'BGL': (0.787, 0.963), 'HPC': (0.654, 0.887), 'Thunderbird': (0.844, 0.955),
    'Windows': (0.989, 0.997), 'Linux': (0.605, 0.690), 'Mac': (0.757, 0.787), 'Android': (0.919, 0.911),
    'HealthApp': (0.639, 0.780), 'Apache': (1.0, 1.0), 'OpenSSH': (0.554, 0.788), 'Proxifier': (0.527, 0.527),
}
ORDER = list(PUBLISHED)


def fetch(data):
    for name, pin in PINS['files'].items():
        target = data / name
        if not target.exists():
            data.mkdir(parents=True, exist_ok=True)
            system = name.split('_2k')[0]
            url = f"https://raw.githubusercontent.com/logpai/logparser/{PINS['commit']}/data/loghub_2k/{system}/{name}"
            with urllib.request.urlopen(url, timeout=120) as response:
                target.write_bytes(response.read())
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        if digest != pin['sha256']:
            raise SystemExit(f"{name}: sha256 {digest} is not the pinned {pin['sha256']}")


def load(data, system):
    """[(message with the benchmark's preprocessing applied, labelled event id)]"""
    out = []
    with open(data / f"{system}_2k.log_structured.csv", newline='', encoding='utf-8') as handle:
        for row in csv.DictReader(handle):
            content = row['Content']
            for expression in SETTINGS[system][3]:
                content = re.sub(expression, STAR, content)
            out.append((content, row['EventId']))
    return out


def spell_tokens(content):
    return [x for x in re.split(r"[\s=:,]", content) if x != '']


def accuracy(parsed, labelled):
    """The benchmark's parsing accuracy: the share of lines in a parsed group that is exactly a labelled group."""
    sizes = Counter(labelled)
    groups = {}
    for k, group in enumerate(parsed):
        groups.setdefault(group, []).append(k)
    right = 0
    for members in groups.values():
        events = {labelled[k] for k in members}
        if len(events) == 1 and len(members) == sizes[labelled[members[0]]]:
            right += len(members)
    return right / len(labelled)


def apart(one, other):
    """Lines that two groupings put with different sets of lines. 0: the same groups, whatever their names."""
    def company(parsed):
        groups = {}
        for k, group in enumerate(parsed):
            groups.setdefault(group, []).append(k)
        return {k: tuple(members) for members in groups.values() for k in members}
    a, b = company(one), company(other)
    return sum(1 for k in a if a[k] != b[k])


# -- the benchmark's own Spell, re-written from logparser/Spell/Spell.py --------------------------
class TreeNode:
    def __init__(self):
        self.child, self.cluster, self.count = {}, None, 0


class Cluster:
    def __init__(self, template):
        self.template = template


class ReferenceSpell:
    def __init__(self, tau, shortcuts=True):
        self.tau, self.root, self.clusters, self.shortcuts = tau, TreeNode(), [], shortcuts

    @staticmethod
    def lcs(a, b):
        lengths = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
        for i in range(len(a)):
            for j in range(len(b)):
                lengths[i + 1][j + 1] = lengths[i][j] + 1 if a[i] == b[j] else max(lengths[i + 1][j], lengths[i][j + 1])
        result, i, j = [], len(a), len(b)
        while i and j:
            if lengths[i][j] == lengths[i - 1][j]:
                i -= 1
            elif lengths[i][j] == lengths[i][j - 1]:
                j -= 1
            else:
                result.insert(0, a[i - 1])
                i, j = i - 1, j - 1
        return result

    def by_tree(self, node, seq, start):
        for i in range(start, len(seq)):
            if seq[i] in node.child:
                child = node.child[seq[i]]
                if child.cluster is None:
                    return self.by_tree(child, seq, i + 1)
                if len([w for w in child.cluster.template if w != STAR]) >= self.tau * len(seq):
                    return child.cluster
        return None

    def by_loop(self, seq):
        have = set(seq)
        for cluster in self.clusters:
            if len(cluster.template) >= 0.5 * len(seq) and all(t in have or t == STAR for t in cluster.template):
                return cluster
        return None

    def by_subsequence(self, seq):
        longest, best, have = -1, None, set(seq)
        for cluster in self.clusters:
            if len(have & set(cluster.template)) < 0.5 * len(seq):
                continue
            shared = len(self.lcs(seq, cluster.template))
            if shared > longest or (shared == longest and len(cluster.template) < len(best.template)):
                longest, best = shared, cluster
        return best if longest >= self.tau * len(seq) else None

    def into_tree(self, cluster):
        node = self.root
        for token in (w for w in cluster.template if w != STAR):
            if token not in node.child:
                node.child[token] = TreeNode()
            node.child[token].count += 1
            node = node.child[token]
        if node.cluster is None:
            node.cluster = cluster

    def out_of_tree(self, cluster):
        node = self.root
        for token in (w for w in cluster.template if w != STAR):
            if token in node.child:
                found = node.child[token]
                if found.count == 1:
                    del node.child[token]
                    break
                found.count -= 1
                node = found

    @staticmethod
    def generalise(shared, template):
        out, i = [], 0
        if not shared:
            return out
        shared = shared[::-1]
        for token in template:
            i += 1
            if token == shared[-1]:
                out.append(token)
                shared.pop()
            else:
                out.append(STAR)
            if not shared:
                break
        if i < len(template):
            out.append(STAR)
        return out

    def parse(self, lines):
        member = []
        for tokens in lines:
            constants = [w for w in tokens if w != STAR]
            cluster = (self.by_tree(self.root, constants, 0) or self.by_loop(constants)) if self.shortcuts else None
            if cluster is None:
                cluster = self.by_subsequence(tokens)
                if cluster is None:
                    cluster = Cluster(list(tokens))
                    self.clusters.append(cluster)
                    self.into_tree(cluster)
                else:
                    new = self.generalise(self.lcs(tokens, cluster.template), cluster.template)
                    if ' '.join(new) != ' '.join(cluster.template):
                        self.out_of_tree(cluster)
                        cluster.template = new
                        self.into_tree(cluster)
            member.append(cluster)
        return [' '.join(cluster.template) for cluster in member]     # one event per final template text


# -- Drain as three rules on the same loop, without its tree -------------------------------------
class DrainRules:
    """Drain (He, Zhu, Zheng and Lyu 2017, https://doi.org/10.1109/ICWS.2017.13) keeps one template
    per message type and updates it as Spell does. What differs is which type a line may join:

        1. a type whose lines have the line's number of tokens;
        2. whose template starts with the line's first `lead` tokens (a token that holds a digit counts
           as a placeholder, and a placeholder in the template goes with any token);
        3. and, of those, the one whose template holds the line's own token at the most positions, when
           that is at least `threshold` of the positions (ties: more placeholders, then the older type).

    Drain finds the types of rules 1 and 2 with a tree of fixed depth; `lead` is that depth less 3.
    Here every template is looked at. Two things the tree does are not here: it caps the children of a
    node, and a line whose leading token has a branch of its own is compared with the templates on
    that branch only, where rule 2 also lets it join a template that starts with a placeholder."""

    def __init__(self, threshold, lead):
        self.threshold, self.lead, self.templates = threshold, lead, []

    @staticmethod
    def key(token):
        return STAR if token == STAR or any(c.isdigit() for c in token) else token

    def add(self, tokens):
        best, where = None, None
        for k, template in enumerate(self.templates):
            if len(template) != len(tokens):
                continue
            if not all(self.key(a) in (STAR, self.key(b)) for a, b in zip(template[:self.lead], tokens[:self.lead])):
                continue
            key = (sum(1 for a, b in zip(template, tokens) if a != STAR and a == b), sum(1 for a in template if a == STAR), -k)
            if best is None or key > best:
                best, where = key, k
        if where is None or (best[0] / len(tokens) if tokens else 1.0) < self.threshold:
            self.templates.append(list(tokens))
            return len(self.templates) - 1
        self.templates[where] = [a if a == b else STAR for a, b in zip(self.templates[where], tokens)]
        return where


# -- the runs ----------------------------------------------------------------------------------
def run_reference(messages, system):
    return ReferenceSpell(SETTINGS[system][0]).parse([spell_tokens(m) for m in messages])


def run_plain(messages, system):
    return ReferenceSpell(SETTINGS[system][0], shortcuts=False).parse([spell_tokens(m) for m in messages])


def run_paper(messages, system):
    from experiments.baselines import Spell
    parser, member = Spell(SETTINGS[system][0], star=STAR, star_matches=True), []
    for message in messages:
        member.append(parser.add(spell_tokens(message))[0])
    return [' '.join(parser.templates[k]) for k in member]


def run_lone(messages, system):
    from experiments.baselines import Spell
    parser, member = Spell(SETTINGS[system][0], star=STAR, star_matches=True), []
    for message in messages:
        tokens = spell_tokens(message)
        member.append(parser.add(tokens)[0] if len(tokens) > 1 else ('one symbol', tuple(tokens)))
    return [' '.join(parser.templates[k]) if isinstance(k, int) else k for k in member]


def run_on_kato(messages, system):
    from hpcrd.show import digest
    from hpcrd.templates import TemplateReader
    reader, member = TemplateReader(SETTINGS[system][0], parameter=STAR), []
    for message in messages:
        tokens = spell_tokens(message)
        name, _joined, _gaps = reader.read(tokens)
        member.append(reader.kind if name else ('one symbol', tuple(tokens)))     # KATO does not learn one symbol
    run_on_kato.last = reader
    reader.check()
    # a line belongs to its message type; the group is that type's template at the end
    groups = [reader.now(kind) if isinstance(kind, int) else kind for kind in member]
    # one sha1 over every line's group and over the node: the same in-process and through a KATO service
    run_on_kato.digest = hashlib.sha1('\n'.join([str(g) for g in groups] + [digest([('templates', reader.node)])]).encode()).hexdigest()
    return groups


def run_drain(messages, system):
    from drain3 import TemplateMiner
    from drain3.template_miner_config import TemplateMinerConfig
    config = TemplateMinerConfig()
    config.drain_sim_th, config.drain_depth, config.profiling_enabled = SETTINGS[system][1], SETTINGS[system][2], False
    miner, member = TemplateMiner(config=config), []
    for message in messages:
        member.append(miner.add_log_message(message.strip())['cluster_id'])
    templates = {c.cluster_id: c.get_template() for c in miner.drain.clusters}
    return [templates[k] for k in member]


def run_rules(messages, system):
    _tau, threshold, depth, _expressions = SETTINGS[system]
    parser, member = DrainRules(threshold, depth - 3), []
    for message in messages:
        member.append(parser.add(message.strip().split()))
    return [' '.join(parser.templates[k]) for k in member]


def run_rules_on_kato(messages, system):
    from hpcrd.templates import PositionReader
    _tau, threshold, depth, _expressions = SETTINGS[system]
    reader, member = PositionReader(threshold, depth - 3, parameter=STAR), []
    for message in messages:
        tokens = message.strip().split()
        name, _joined, _gaps = reader.read(tokens)
        member.append(reader.kind if name else ('one symbol', tuple(tokens)))     # KATO does not learn one symbol
    run_rules_on_kato.last = reader
    reader.check()
    return [' '.join(reader.template(reader.now(kind))) if isinstance(kind, int) else ' '.join(kind[1]) for kind in member]


RUNS = [('reference', run_reference), ('plain', run_plain), ('paper', run_paper), ('lone', run_lone),
        ('on KATO', run_on_kato), ('Drain', run_drain), ('rules', run_rules), ('rules on KATO', run_rules_on_kato)]
DRAINS = ('Drain', 'rules', 'rules on KATO')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', required=True, help='a directory outside the repository')
    parser.add_argument('--fetch', action='store_true')
    parser.add_argument('--only', nargs='*', help='system names')
    parser.add_argument('--skip', nargs='*', default=[],
                        help='runs to leave out: reference, plain, paper, lone, "on KATO", Drain, rules, "rules on KATO"')
    parser.add_argument('--save')
    args = parser.parse_args()
    data = pathlib.Path(args.data).resolve()
    if ROOT in data.parents or data == ROOT:
        raise SystemExit("keep the data outside the repository")
    if args.fetch:
        fetch(data)
    runs = [(name, function) for name, function in RUNS if name not in args.skip]
    print(f"{'system':12s} {'events':>6s} | {'Spell':>6s} " + ' '.join(f"{name:>9s}" for name, _ in runs if name not in DRAINS)
          + f" | {'Drain':>6s} " + ' '.join(f"{'drain3' if name == 'Drain' else name:>13s}" for name, _ in runs if name in DRAINS)
          + " | templates on KATO (live / stored), seconds")
    saved, totals = {}, Counter()
    for system in args.only or ORDER:
        rows = load(data, system)
        messages, labelled = [m for m, _ in rows], [e for _, e in rows]
        result = {'lines': len(rows), 'labelled events': len(set(labelled)),
                  'published': {'Spell': PUBLISHED[system][0], 'Drain': PUBLISHED[system][1]}}
        note, groupings = '', {}
        for name, function in runs:
            began = time.perf_counter()
            parsed = groupings[name] = function(messages, system)
            result[name] = {'accuracy': round(accuracy(parsed, labelled), 4), 'groups': len(set(parsed)),
                            'seconds': round(time.perf_counter() - began, 1)}
            totals[name] += result[name]['accuracy']
            if name == 'on KATO':
                node = run_on_kato.last.node
                result[name].update(stored=len(node.patterns), retired=len(node.retired), learns=node.learns,
                                    predictions=node.predicts, revived=run_on_kato.last.revived,
                                    merged=run_on_kato.last.merged, digest=run_on_kato.digest)
                note = f"{len(node.patterns) - len(node.retired)} / {len(node.patterns)}, {result[name]['seconds']} s"
            if name == 'rules on KATO':
                node = run_rules_on_kato.last.node
                result[name].update(stored=len(node.patterns), retired=len(node.retired), learns=node.learns,
                                    predictions=node.predicts, revived=run_rules_on_kato.last.revived,
                                    merged=run_rules_on_kato.last.merged)
        for one, others in (('on KATO', ('paper', 'lone')), ('rules', ('Drain',)), ('rules on KATO', ('rules',))):
            for other in others:            # not only the same score: the same groups?
                if one in groupings and other in groupings:
                    label = f"lines grouped otherwise than by {'drain3' if other == 'Drain' else other}"
                    result[one][label] = apart(groupings[one], groupings[other])
                    note += f", {one}: {result[one][label]} {label}"
        totals['n'] += 1
        totals['Spell published'] += PUBLISHED[system][0]
        totals['Drain published'] += PUBLISHED[system][1]
        saved[system] = result
        print(f"{system:12s} {result['labelled events']:6d} | {PUBLISHED[system][0]:6.3f} "
              + ' '.join(f"{result[name]['accuracy']:9.3f}" for name, _ in runs if name not in DRAINS)
              + f" | {PUBLISHED[system][1]:6.3f} " + ' '.join(f"{result[name]['accuracy']:13.3f}" for name, _ in runs if name in DRAINS)
              + f" | {note}", flush=True)
        if args.save:
            pathlib.Path(args.save).write_text(json.dumps({'pins': {k: v for k, v in PINS.items() if k != 'files'},
                                                           'systems': saved}, indent=1, sort_keys=True) + '\n')
    n = totals['n']
    print(f"{'average':12s} {'':6s} | {totals['Spell published'] / n:6.3f} "
          + ' '.join(f"{totals[name] / n:9.3f}" for name, _ in runs if name not in DRAINS)
          + f" | {totals['Drain published'] / n:6.3f} " + ' '.join(f"{totals[name] / n:13.3f}" for name, _ in runs if name in DRAINS))


if __name__ == '__main__':
    sys.exit(main())
