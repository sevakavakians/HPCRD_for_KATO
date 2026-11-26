# HPCRD for KATO

**Hierarchical pattern chunking and rule discovery for [KATO](https://github.com/sevakavakians/kato).**

**New here? Read [the summary](docs/summary-2026-11-26.md) first.** It says in plain words what was done, shows the accuracy tables, and says what the numbers mean. The notes below call its four steps "rounds". [The register](docs/methods-register.md) lists every published method that was looked at, and which are to be built for KATO.

An experiment, started 24 Nov 2026. The goal is to find or create the KATO capabilities that let it

1. segment patterns automatically,
2. chunk repeated patterns,
3. create rules from patterns,

by reading KATO's prediction ensembles. The data is any sequence of symbols. Text is the first case, one token per event.

Status: a reference sketch with worked examples, tests, one small probe on annotated text and one
published benchmark (`experiments/`). On the probe about one annotated slot in five is found
exactly, at best. On the benchmark, a published log parser's loop run on KATO's matcher gives that
parser's accuracy.

## The idea in one picture

```
node_0   learns sequences of symbols (rolling windows, or whole sequences)
   |  prediction ensemble
module   reads each prediction's matches / missing / extras
   |-> node_1a   each contiguous match of two or more symbols        -> PTRN|<chunk>
   |-> node_1b   the abstracted sequence: chunk names, single
   |             symbols, VAR|n                                      -> PTRN|<rule>
   |       '-> node_2a   observes PTRN|<rule> names in order
   |-> node_2b   each VAR|n with a value; the values of one rule
   |             instance together; VARs that stand side by side;
   |             what a VAR is made of
   '-> node_1t   (optional) each rule with its chunks spelled out, so
                 that a learned rule can read a new sequence
```

From "the cat sat on the mat ." and "the dog sat on the mat ." the module learns the chunk `sat on the mat .`, the rule `[the] [VAR|1] [PTRN|76a6fb]` and the values `cat`, `dog`. A third sentence with `bird` is recognised as the same rule, and node_1b's own prediction binds the value: `missing [[], ["VAR|1"], []]`, `extras [[], ["bird"], []]`.

Four rounds so far:

- Round 1. Rolling windows at node_0, one VAR per position, six worked examples (`examples/worked_examples.py`).
- Round 2. Whole sequences at node_0, one VAR per gap, reading inside a VAR, a learned rule reading a new
  sequence (`examples/sequences.py`), and a probe on annotated dialogue text (`experiments/sgd_probe.py`).

- Round 3. What published methods already settle: Spell's loop (Du and Li 2016) on a KATO node
  (`hpcrd/templates.py`), and two published log parsers on the same probe (`experiments/baselines.py`).
- Round 4. Spell's loop on KATO held to the published log-parsing benchmark
  (`experiments/log_benchmark.py`), made the module's outer loop (`loop='templates'`), and checked
  through a running KATO service, where a rule is edited by learning the new pattern and retiring the old one.
- 26 Nov, a follow-up. Drain's rule on a KATO node (`hpcrd/templates.py`, `PositionReader`), held to the same
  benchmark. And what entropy can and cannot do about one rule for a whole sentence: KATO's weight of evidence
  as a floor on joining a rule, two published rules for cutting by branching entropy
  (`experiments/branching.py`), and rules for parts of sentences (`experiments/entropy_probe.py`).

The write-ups are in `docs/`: `summary-2026-11-26.md` (all four rounds, for a new reader), `worked-examples-2026-11-24.md` (round 1),
`round-2-sequences-and-gap-variables-2026-11-24.md` (round 2),
`round-3-published-methods-2026-11-24.md` (round 3) and
`round-4-log-benchmark-and-outer-loop-2026-11-24.md` (round 4), `entropy-and-rule-units-2026-11-26.md` (the follow-up)
and `methods-register.md` (the methods looked at, and what is to be built). `examples/report.txt` and
`examples/report_sequences.txt` are the full outputs the first two quote, and `experiments/results/` has the numbers.

## Layout

| Path | What it is |
|---|---|
| `hpcrd/kato_node.py` | One KATO node in-process, built on KATO's own `Pattern`, `InformationExtractor`, `Prediction`, `score_ensemble` and `rank_predictions`. Mirrors by hand: frequency counting, the node counters, observe order (append, predict, auto-learn), ROLLING/CLEAR, the single-symbol path, retire and un-retire. |
| `hpcrd/kato_api_node.py` | The same interface over KATO's REST API, retire and un-retire included. Set `KATO_API` and every node lives in a running service. |
| `hpcrd/alignment.py` | Rebuilds the position-level alignment of one prediction from `missing`, `extras`, `past`, `present`, `future` (one symbol per event). |
| `hpcrd/modeler.py` | The module between node_0 and nodes 1a, 1b, 2a, 2b. Every open choice is a field of `Settings`. |
| `hpcrd/templates.py` | Spell's loop on a KATO node (`TemplateReader`): one template per message type, edited by learning the new pattern and retiring the old one. A line belongs to its type, whatever its template becomes. `PositionReader` is the same loop with Drain's rule for joining: a symbol carries its position, so that KATO's matches are Drain's count. `evidence` is an optional floor on KATO's weight of evidence for a join; it is off unless asked for. |
| `hpcrd/show.py` | Printing helpers. |
| `examples/worked_examples.py` | Round 1's worked examples (1 to 6). Prints `examples/report.txt`. |
| `examples/sequences.py` | Round 2's examples (7 to 12). Prints `examples/report_sequences.txt`. |
| `experiments/baselines.py` | Drain (through `drain3`), Spell (from the paper's description) and Spell's loop on KATO, on the same probe. `--sweep`: Spell alone over its threshold. |
| `experiments/log_benchmark.py` | The published log-parsing benchmark (Zhu et al. 2019): the benchmark's own Spell re-written, the same without its two shortcuts, Spell as its paper describes it, Spell's loop on KATO, `drain3`, Drain as three rules without its tree, and those rules on KATO. The data is fetched at run time, pinned by sha256 (`loghub_pins.json`), and kept outside the repository. |
| `experiments/sgd_probe.py` | VAR spans against annotated slot spans on pinned Schema-Guided Dialogue files. The data is fetched at run time and kept outside the repository; `experiments/results/` holds numbers only. |
| `experiments/branching.py` | Branching entropy over token sequences, and two published rules for cutting by it (Jin and Tanaka-Ishii 2006). Counts only; no KATO. |
| `experiments/entropy_probe.py` | On the same dialogue sentences: KATO's weight of evidence as a floor on joining a rule, entropy at the edges of the marked values, the two cutting rules, rules for parts of sentences, what stood at Spell's placeholders, and the entropy of KATO's own next-event distribution. |
| `examples/explore.py` | Any text, any settings, from the command line. |
| `scripts/check_alignment.py` | The full alignment check: 502,184 of 502,184 predictions. About a minute. |
| `tests/` | The reports are reproduced; the alignment is rebuilt; the invariants hold; the loop's templates, types and retirements are what they should be. The tests marked `through_api` also run against a KATO service. |
| `docs/` | Write-ups, dated. |

## Set up and run

KATO is read from a checkout, with KATO's own requirements installed in the environment.
Modules go into an environment, never into a system Python.

```sh
git clone https://github.com/sevakavakians/kato.git ../kato     # read at f32bac0 (v7.1.0-34-gf32bac0)
export KATO_REPO=$PWD/../kato
uv venv --python 3.13 .venv
uv pip install --python .venv/bin/python -r $KATO_REPO/requirements.txt pytest

.venv/bin/python -m pytest -q                   # the tests
./run.sh examples/worked_examples.py            # examples 1 to 6, in-process
./run.sh examples/worked_examples.py 3 5        # examples 3 and 5
./run.sh examples/worked_examples.py --digest   # one sha1 over the whole report
./run.sh examples/sequences.py                  # examples 7 to 12
./run.sh scripts/check_alignment.py
./run.sh experiments/sgd_probe.py --data ../sgd-data --fetch    # the probe; a directory outside the repository
uv pip install --python .venv/bin/python drain3                 # only for the next three lines
./run.sh experiments/baselines.py --data ../sgd-data            # published parsers on the same probe
./run.sh experiments/baselines.py --data ../sgd-data --sweep    # Spell alone, over its threshold
.venv/bin/python -I experiments/log_benchmark.py --data ../loghub-data --fetch   # the log benchmark (-I: it reads downloaded files)
./run.sh experiments/sgd_probe.py --data ../sgd-data --only 23 24               # the probe with Spell's loop as the outer loop
.venv/bin/python -I experiments/entropy_probe.py --data ../sgd-data             # the entropy measurements; about five minutes
.venv/bin/python -I experiments/entropy_probe.py --data ../sgd-data --only kato # KATO's own next-event entropy; about 45 minutes

# any text, any settings
./run.sh examples/explore.py E4 verbose=1 span=stream markers=. slots=gap recall_threshold=0.5 unexplained=break
./run.sh examples/explore.py "play yesterday . play imagine ." span=sequence markers=. slots=gap values=sequence
./run.sh examples/explore.py "book for two at seven . book for six at seven . book for six at nine ." \
    span=sequence markers=. slots=gap values=sequence loop=templates
```

Through a running KATO service (every node in the service, every call over REST):

```sh
KATO_API=http://127.0.0.1:8000 KATO_API_TAG=run1 ./run.sh examples/worked_examples.py > report_api.txt
diff examples/report.txt report_api.txt         # empty
```

`KATO_API_TAG` names the nodes of the run (`rules_<tag>_<n>_<node>`). Use a new tag for a new run.

The tests that say the same of the in-process node and of the service, and one benchmark system:

```sh
KATO_API=http://127.0.0.1:8000 KATO_API_TAG=check1 .venv/bin/python -m pytest -q
KATO_API=http://127.0.0.1:8000 KATO_API_TAG=check2 .venv/bin/python -I experiments/log_benchmark.py \
    --data ../loghub-data --only HealthApp --skip reference plain paper Drain --save service.json
```

The saved `digest` is one sha1 over every line's group and every pattern of the node (name,
frequency, retired). It has to equal the in-process run's.

## What has been checked

- `examples/report_sequences.txt` (round 2) is 554 lines, sha1 `7c8150fb9ad947329d60a91b6b6d8a2ad06cf8de`,
  in-process, the same under `PYTHONHASHSEED` 0 and 7. Through a KATO service it is the same, byte for
  byte (24 Nov 2026, the setup of the next point).
- `examples/report.txt` is 906 lines, sha1 `818a4c2a85c59ff50f9a022777f1d759374371b5`.
  In-process and through a KATO service it is the same, byte for byte (24 Nov 2026: the service
  started from the checkout at f32bac0 with one uvicorn worker, against ClickHouse 26.10.4.207,
  Redis 7.4.12 and Qdrant v1.17.1 in Docker; 3 min 50 s against 2.6 s).
- The report is the same under different `PYTHONHASHSEED` values. Nothing is random and no clock is read.
- With one symbol per event, the alignment KATO computes and does not return is rebuilt from the
  returned fields on 502,184 of 502,184 predictions.
- The log benchmark (round 4). The benchmark's own Spell, re-written in the harness, is within 0.001
  of the published accuracy on 16 of 16 systems. Spell's loop on KATO puts all 32,000 lines into the
  same groups as Spell as its paper describes it, once that version too keeps a line of one token as
  a type of its own (KATO does not learn a pattern of one symbol).
- Retiring a pattern (round 4), on a KATO service with the setup above: predictions skip a retired
  pattern, it can still be read by name, and learning it again is refused until it is un-retired.
  The in-process node does the same. 19 tests pass in-process and through the service. Two benchmark
  systems (HealthApp, Mac) and the first 300 probe sentences with `loop='templates'` give the same
  digest both ways: every line's group, and every pattern's name, frequency and retirement.
  The full benchmark and the full probe have run in-process only.
- Drain's rule (26 Nov). As three rules without its tree it scores 0.865 on the log benchmark, where the
  published figure is 0.866, and equals the published figure on each of the 16 systems after rounding. On
  KATO (`PositionReader`) all 32,000 lines are grouped as by those rules. Spell's loop on KATO gives the
  digests of 24 Nov on all 16 systems after the two readers were given one shared replace step.
- The follow-up through a KATO service (26 Nov, the setup above): 34 tests pass in-process and through
  the service. Drain's rule on two benchmark systems (Apache, HDFS) gives the same groups and the same
  patterns, stored and retired, both ways. The entropy of KATO's next-event distribution on the first 150
  probe sentences is the same both ways, number for number. A service takes `max_predictions` up to 10000
  only; the in-process node now refuses a larger one too. The rest of the follow-up has run in-process only.

## Licence

Apache 2.0. See `LICENSE` and `NOTICE`.
