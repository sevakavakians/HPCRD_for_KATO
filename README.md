# HPCRD for KATO

**Hierarchical pattern chunking and rule discovery for [KATO](https://github.com/sevakavakians/kato).**

An experiment, started 24 Nov 2026. The goal is to find or create the KATO capabilities that let it

1. segment patterns automatically,
2. chunk repeated patterns,
3. create rules from patterns,

by reading KATO's prediction ensembles. The data is any sequence of symbols. Text is the first case, one token per event.

Status: a reference sketch with worked examples and tests. No corpus has been run yet.

## The idea in one picture

```
node_0   learns sequences of symbols (rolling windows, or whole sequences)
   |  prediction ensemble
module   reads each prediction's matches / missing / extras
   |-> node_1a   each contiguous match of two or more symbols        -> PTRN|<chunk>
   |-> node_1b   the abstracted sequence: chunk names, single
   |             symbols, VAR|n                                      -> PTRN|<rule>
   |       '-> node_2a   observes PTRN|<rule> names in order
   '-> node_2b   each VAR|n with a value; the values of one rule
                 instance together; VARs that stand side by side
```

From "the cat sat on the mat ." and "the dog sat on the mat ." the module learns the chunk `sat on the mat .`, the rule `[the] [VAR|1] [PTRN|76a6fb]` and the values `cat`, `dog`. A third sentence with `bird` is recognised as the same rule, and node_1b's own prediction binds the value: `missing [[], ["VAR|1"], []]`, `extras [[], ["bird"], []]`.

The write-up with the worked examples is not in the repository yet. `examples/report.txt` is the full output it quotes.

## Layout

| Path | What it is |
|---|---|
| `hpcrd/kato_node.py` | One KATO node in-process, built on KATO's own `Pattern`, `InformationExtractor`, `Prediction`, `score_ensemble` and `rank_predictions`. Mirrors by hand: frequency counting, the node counters, observe order (append, predict, auto-learn), ROLLING/CLEAR, the single-symbol path. |
| `hpcrd/kato_api_node.py` | The same interface over KATO's REST API. Set `KATO_API` and every node lives in a running service. |
| `hpcrd/alignment.py` | Rebuilds the position-level alignment of one prediction from `missing`, `extras`, `past`, `present`, `future` (one symbol per event). |
| `hpcrd/modeler.py` | The module between node_0 and nodes 1a, 1b, 2a, 2b. Every open choice is a field of `Settings`. |
| `hpcrd/show.py` | Printing helpers. |
| `examples/worked_examples.py` | The worked examples. Prints `examples/report.txt`. |
| `examples/explore.py` | Any text, any settings, from the command line. |
| `scripts/check_alignment.py` | The full alignment check: 502,184 of 502,184 predictions. About a minute. |
| `tests/` | The report is reproduced; the alignment is rebuilt; the invariants hold. |

## Set up and run

KATO is read from a checkout, with KATO's own requirements installed in the environment.
Modules go into an environment, never into a system Python.

```sh
git clone https://github.com/sevakavakians/kato.git ../kato     # read at f32bac0 (v7.1.0-34-gf32bac0)
export KATO_REPO=$PWD/../kato
uv venv --python 3.13 .venv
uv pip install --python .venv/bin/python -r $KATO_REPO/requirements.txt pytest

.venv/bin/python -m pytest -q                   # the tests
./run.sh examples/worked_examples.py            # all examples, in-process
./run.sh examples/worked_examples.py 3 5        # examples 3 and 5
./run.sh examples/worked_examples.py --digest   # one sha1 over the whole report
./run.sh scripts/check_alignment.py

# any text, any settings
./run.sh examples/explore.py E4 verbose=1 span=stream markers=. slots=gap recall_threshold=0.5 unexplained=break
```

Through a running KATO service (every node in the service, every call over REST):

```sh
KATO_API=http://127.0.0.1:8000 KATO_API_TAG=run1 ./run.sh examples/worked_examples.py > report_api.txt
diff examples/report.txt report_api.txt         # empty
```

`KATO_API_TAG` names the nodes of the run (`rules_<tag>_<n>_<node>`). Use a new tag for a new run.

## What has been checked

- `examples/report.txt` is 906 lines, sha1 `818a4c2a85c59ff50f9a022777f1d759374371b5`.
  In-process and through a KATO service it is the same, byte for byte (24 Nov 2026: the service
  started from the checkout at f32bac0 with one uvicorn worker, against ClickHouse 26.10.4.207,
  Redis 7.4.12 and Qdrant v1.17.1 in Docker; 3 min 50 s against 2.6 s).
- The report is the same under different `PYTHONHASHSEED` values. Nothing is random and no clock is read.
- With one symbol per event, the alignment KATO computes and does not return is rebuilt from the
  returned fields on 502,184 of 502,184 predictions.

## Licence

Apache 2.0. See `LICENSE` and `NOTICE`.
