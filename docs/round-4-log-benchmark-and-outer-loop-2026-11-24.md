# HPCRD for KATO, round 4: Spell's loop against its benchmark, on a KATO service, and as the outer loop

24 Nov 2026. Follows `round-3-published-methods-2026-11-24.md`. Branch `claude/templates-as-outer-loop`, draft PR 3.

Two things were agreed: fetch the log benchmark and hold Spell's loop on KATO to its published numbers, then make that loop the module's outer loop. Both are done. A third was added on the way. The loop edits a rule by retiring a pattern, and until now only my in-process stand-in had done that, so the loop was run on a KATO service.

## 0. In one screen

1. **The harness measures what the benchmark measured.** The benchmark's own Spell, re-written here, is within 0.001 of the published accuracy on all 16 systems.
2. **Spell's loop on KATO is Spell.** It puts all 32,000 lines into exactly the groups that Spell, as its paper describes it, does once that version too keeps a line of one token as a type of its own. KATO does not learn a pattern of one symbol. That is the only difference, and it accounts for 515 lines in 3 systems.
3. **The published numbers are not quite that algorithm's.** The benchmark's implementation tries two shortcuts before the subsequence step. They put HealthApp at 0.639 where the algorithm alone gives 0.759, and OpenSSH at 0.554 where it gives 0.484.
4. **It runs on KATO itself.** Through a KATO service at `f32bac0`, 19 tests, two benchmark systems and 300 probe sentences give what they give in-process, pattern for pattern. The check found two things my in-process node had wrong. Both are fixed. Round 2's report also came out byte for byte the same.
5. **It is the module's outer loop now** (`loop='templates'`). A rule is edited in place: learn the new pattern, retire the old one. A VAR keeps its symbol through edits.
6. **On the dialogue probe it does not beat round 2.** 15.6% of annotated slots found exactly, 18.0% with the inside reading, against 14.4% and 21.6%. The reason is measured: half the slots are in sentences that join no template when they arrive, and no threshold changes that.
7. **Two corrections.** Round 3 quoted 0.751 as Spell's benchmark average; the paper's own sixteen values average 0.793. And my first benchmark run (commit `12b2ad3`) had Mac at 0.777 for the loop on KATO. It is 0.749.

## 1. The benchmark

Zhu et al. (2019): 2,000 sampled lines from each of 16 systems, templates labelled by hand. A line is right only if its template groups it with exactly the lines the labels do.

The data are the Loghub samples distributed with `logpai/logparser`, at commit `d9d4180`: fetched at run time, pinned by sha256, kept out of the repository. Loghub's terms: free for research or academic work, with a reference to the Loghub repository and its paper (section 8). The settings for each system (tau, Drain's threshold and depth, the preprocessing expressions) are the ones in logparser's own benchmark scripts.

Six parsers ran in one harness, `experiments/log_benchmark.py`:

1. **Reference**: the benchmark's Spell, re-written from `logparser/Spell/Spell.py` (Apache 2.0). It tries a prefix tree, then a set-containment test, and only then the longest common subsequence.
2. **Plain**: the reference without those two shortcuts.
3. **Paper**: Spell as its paper describes it: the subsequence step alone.
4. **Lone**: the paper version with one rule added: a line of one token is a type of its own.
5. **On KATO**: the same loop on KATO's matcher (`hpcrd/templates.py`).
6. **drain3**: the Drain package, as a second check of the harness.

"Otherwise" is the number of the 2,000 lines that On KATO puts with a different set of lines than Paper does.

| System | Spell, published | Reference | Plain | Paper | On KATO | Otherwise | Drain, published | drain3 |
|---|---|---|---|---|---|---|---|---|
| HDFS | 1.000 | 1.000 | 0.998 | 0.998 | 0.998 | 0 | 0.998 | 0.998 |
| Hadoop | 0.778 | 0.777 | 0.778 | 0.777 | 0.777 | 0 | 0.948 | 0.948 |
| Spark | 0.905 | 0.905 | 0.905 | 0.905 | 0.905 | 0 | 0.920 | 0.920 |
| Zookeeper | 0.964 | 0.964 | 0.964 | 0.964 | 0.964 | 0 | 0.967 | 0.967 |
| OpenStack | 0.764 | 0.764 | 0.764 | 0.764 | 0.764 | 0 | 0.733 | 0.733 |
| BGL | 0.787 | 0.786 | 0.800 | 0.797 | 0.797 | 0 | 0.963 | 0.963 |
| HPC | 0.654 | 0.654 | 0.652 | 0.652 | **0.904** | 504 | 0.887 | 0.887 |
| Thunderbird | 0.844 | 0.844 | 0.846 | 0.846 | 0.847 | 7 | 0.955 | 0.955 |
| Windows | 0.989 | 0.989 | 0.989 | 0.989 | 0.989 | 0 | 0.997 | 0.997 |
| Linux | 0.605 | 0.605 | 0.605 | 0.605 | 0.605 | 0 | 0.690 | 0.690 |
| Mac | 0.757 | 0.756 | 0.756 | 0.749 | 0.749 | 0 | 0.787 | 0.786 |
| Android | 0.919 | 0.918 | 0.908 | 0.908 | 0.908 | 0 | 0.911 | 0.831 |
| HealthApp | 0.639 | 0.639 | 0.759 | 0.759 | 0.760 | 4 | 0.780 | 0.780 |
| Apache | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 0 | 1.000 | 1.000 |
| OpenSSH | 0.554 | 0.554 | 0.484 | 0.484 | 0.484 | 0 | 0.788 | 0.787 |
| Proxifier | 0.527 | 0.526 | 0.526 | 0.526 | 0.526 | 0 | 0.527 | 0.526 |
| Mean of the 16 | 0.793 | 0.793 | 0.796 | 0.795 | 0.811 | 515 in all | 0.866 | 0.860 |

**Reading it.**

1. **Reference against published: within 0.001 on 16 of 16.** drain3 against published Drain: 15 of 16. Android is 0.831 against 0.911; drain3 is not the benchmark's Drain.
2. **On KATO against Paper: the same groups on 13 systems.** Not the same score only. Every one of the 2,000 lines is with the same lines.
3. **The other 515 lines all come from lines of one token.** Spell joins such a line to a template that holds its token: `warning` goes into `<*> warning <*>`, which the labels count as wrong, and that template then reads later lines differently. KATO does not learn a pattern of one symbol, so the reader keeps such a line as a type of its own. With that rule added to the paper version (Lone), not one of the 32,000 lines is grouped otherwise.
4. **HPC's 0.904 is that rule, not a better loop.** 497 of HPC's 2,000 lines are the one-token messages `ambient<*>` and `warning`. Without HPC, the mean is 0.805 for Paper and for On KATO.
5. **Published against Paper: five systems differ by more than 0.003.** The two shortcuts account for HealthApp, OpenSSH and Android entirely, and for most of BGL: compare Reference with Plain. Mac's 0.008 is in the rest of the benchmark's code, which skips a template that shares fewer than half the line's tokens whatever tau is, and updates a template position by position.

So the chain is: Reference reproduces the published numbers; Plain shows what its shortcuts add; Paper is Plain to within 0.008; On KATO is Paper, line for line, but for lines of one token.

**What the benchmark found in my code.**

1. **Ties.** Ties between equally good templates first went to the smaller pattern name. On HealthApp that gave 0.449. The benchmark's implementation gives ties to the older type. The reader does the same now.
2. **A line belongs to a message type, not to a pattern.** My first run looked a line's type up by the name of the pattern it had joined. A pattern's name is the hash of its content. When a type's template has worn down and its first line arrives again, that text is a new type, on the very pattern KATO retired earlier, and the earlier lines went with it. That gave Mac 0.777, BGL 0.801 and a mean of 0.813 in commit `12b2ad3`: closer to the labels, and not Spell. The reader now numbers the types and keeps each line with its type. Mac is 0.749, as for Paper.

**KATO's side of the run.** 32,000 lines; 30,732 learns and as many predictions, because 1,268 lines are one token. 2,961 patterns stored, 604 of them retired. 19 times a retired content was learned again and un-retired first. 8 times an edit gave a template the content of another live one, and the two types became one pattern. 121.8 s in-process against 2.5 s for Paper alone.

**The correction to round 3.** Table IV of the benchmark paper prints 0.751 as Spell's average. The sixteen values the table gives for Spell average 0.793 (IPLoM: 0.777 printed, 0.806 averaged; Drain: 0.865 and 0.866). The paper gives no formula for the row. The per-system values are what this harness reproduces.

## 2. On a KATO service

The loop edits a rule by retiring a pattern. My in-process node uses KATO's own classes for matching and mirrors storage by hand, so the retire calls were the part most likely to be wrong. They were.

The service: KATO at `f32bac0`, started from the checkout with one uvicorn worker, against ClickHouse 26.10.4.207, Redis 7.4.12 and Qdrant v1.17.1 in Docker. The same setup as round 1's check.

**What KATO does with a retired pattern**, call by call:

| Call | What comes back |
|---|---|
| `POST /sessions/{id}/patterns/retire` | 200. The id is under `retired`, and under `already_retired` the second time. With or without `PTRN\|`. |
| Predictions afterwards | The pattern is not in them, for an STM of one symbol too. |
| `GET /pattern/{name}` | The pattern, frequency included. |
| `observe-sequence` with `learn_at_end`, the same sequence again | 200, `status: completed`, `final_learned_pattern: null`. The sequence stays in the session's STM. |
| `POST /sessions/{id}/learn` on that STM | 409, `RETIRED_PATTERN`. |
| `POST /sessions/{id}/patterns/un-retire`, then the sequence again | 200, `un_retired`. Then it is learned under the same name, frequency 2. |
| Retire an id the node does not hold | 200. It is tombstoned all the same. |
| A malformed id | 422. |

**What my in-process node had wrong.**

1. **It let a retired pattern be learned again.** KATO refuses. The reader learned first and un-retired second. On a service that is a learn that does not happen. The reader un-retires first now, and the in-process node refuses as KATO does.
2. **It read a retired pattern's frequency as 0.** KATO still returns the pattern by name.

Neither changed a number in this note. The first would have stopped the loop on a service at the first template whose content came back.

**The same results through the service.** A **digest** is one sha1 over every line's group and every pattern of every node: its name, which is the hash of its content, its frequency, and whether it is retired.

| Run | In-process | Through the service | What is the same |
|---|---|---|---|
| The 19 tests marked `through_api` | pass | pass | |
| Benchmark, HealthApp | 0.760, 2.3 s | 0.760, 463 s | the digest |
| Benchmark, Mac | 0.749, 4.7 s | 0.749, 329 s | the digest |
| Benchmark, Apache | 1.000, 0.7 s | 1.000, 112 s | accuracy and pattern counts (run before the digest existed) |
| Probe, first 300 sentences, `loop='templates'` | 1.2 s | 196 s | every number and the digest |
| The same with the inside reading | 1.3 s | 223 s | every number and the digest |
| Round 2's report, `examples/sequences.py` | 554 lines, 2.2 s | 554 lines | byte for byte, sha1 `7c8150fb` |

About 58,000 requests. None was answered with a 5xx, and the only refusals were the ones the checks asked for. Through REST the loop is 70 to 200 times slower, on one worker with runs overlapping.

**Two things in KATO for you to judge.** I changed nothing in KATO.

1. **`observe-sequence` hides a refused learn.** The learn at its end sits in an `except Exception` that logs a warning (`kato/api/endpoints/sessions.py`, lines 907 to 916 at `f32bac0`). So a retired pattern gives a 200 with no pattern name, and the sequence is left in the session's STM for the next call to build on. `POST /sessions/{id}/learn` answers the same case with a 409. A caller that does not look at `final_learned_pattern` has a learn that silently did not happen.
2. **A retired pattern can still be read by name.** The retire endpoint's docstring says every read path filters it. `GET /pattern/{name}` does not: `pattern_operations.get_pattern` reads the stored row and does not ask the registry. That may be what an audit wants. Then the docstring is the thing to change.

## 3. The loop as the module's outer loop

`Settings(loop='templates', tau=0.5)`, with whole sequences, one VAR per gap and values as tokens.

1. A sequence goes to the template node. It joins the type it shares the longest common subsequence with, if that is at least `tau` of the sequence.
2. The template is edited: the new pattern is learned and the old one retired. Each placeholder is a VAR symbol of its own, and a gap that holds an earlier VAR keeps that VAR's symbol.
3. The nodes above are fed from the template. Runs of constants are chunks (node_1a). The template with chunk names in place of the runs is the rule (node_1b). When the template is edited, the old rule is retired there too. Each VAR's value goes to node_2b, and so does what the template held at a new gap before the edit.
4. node_0 still learns the raw sequence. Nothing reads it yet. ADIOS will.

Real output, shortened (`examples/explore.py`, the command is in section 9):

```
sequence  book for two at seven .
      templates a new type: the sequence is its own template, PTRN|84352e
sequence  book for six at seven .
      templates PTRN|a6a2c6 = [book for VAR|1 at seven .]   (edited; it was [book for two at seven .], now retired)
      node_1b   PTRN|a5a093 = [PTRN|7bf527(book for)] [VAR|1] [PTRN|6bb8f0(at seven .)]   frequency 1
      node_2b   [VAR|1] [six]   (new value; earlier: two x1)
      node_2b   [VAR|1] [two]   (value a learned pattern has there)
sequence  book for six at nine .
      templates PTRN|614c06 = [book for VAR|1 at VAR|2 .]   (edited; it was [book for VAR|1 at seven .], now retired)
      node_1b   PTRN|6d91d6 = [PTRN|7bf527(book for)] [VAR|1] [at] [VAR|2] [.]   frequency 1
      node_2b   [VAR|1] [six]   (known value)
      node_2b   [VAR|2] [nine]   (new value; earlier: seven x1)
      node_2b   [VAR|2] [seven]   (value a learned pattern has there)
      node_1b   retired: [PTRN|7bf527(book for)] [VAR|1] [PTRN|6bb8f0(at seven .)]

  templates: 3 patterns, 3 learns, 2 retired
    PTRN|614c06  f=1  [book] [for] [VAR|1] [at] [VAR|2] [.]
    PTRN|84352e  f=1  [book] [for] [two] [at] [seven] [.]   (retired)
    PTRN|a6a2c6  f=1  [book] [for] [VAR|1] [at] [seven] [.]   (retired)
```

Every earlier version of the rule is still stored, and un-retire brings it back.

`fold` and `topdown` from round 2 are not used by this loop. They are still in the code, so that round 2's report stays reproducible.

## 4. The dialogue probe again

3,873 user sentences of the Schema-Guided Dialogue set, 1,388 annotated slot spans, each sentence judged against its rule as it stood when the sentence arrived.

| | Slots that are exactly one VAR | Slots inside a longer VAR | Slots in a sentence with no rule yet | Exact, of the slots in a sentence with a rule |
|---|---|---|---|---|
| Spell alone, tau 0.5 | 16.1% | 16.2% | 48.5% | 31.2% |
| Spell's loop on KATO | 15.6% | 16.5% | 48.7% | 30.3% |
| Module, `loop='templates'` | 15.6% | 16.5% | 48.3% | 30.1% |
| ... with the inside reading | 18.0% | 12.9% | 48.3% | 34.9% |
| Round 2: nearest reading, rules read first | 14.4% | 31.7% | 16.3% | 17.2% |
| ... with the inside reading | 21.6% | 19.2% | 16.3% | 25.8% |

The module holds 942 live templates here, and the loop alone 941: with one placeholder symbol two templates once became the same text, and with numbered VARs they cannot. A sentence that joins a template with nothing in a gap counts as "no rule" for the loop alone and as a rule without VARs in the module: 5 slots.

**Why it is behind.** Spell asks one template to cover at least half of the sentence. That suits a log line, which is one message. A sentence that holds a slot is usually several pieces put together: what is wanted, where, when, for how many. No single earlier sentence shares half of it.

1. **Where a sentence has a rule, the loop is the more exact.** 30% of those slots are exactly one VAR, against 17% for round 2. With the inside reading, 35% against 26%.
2. **But 48% of the slots are in a sentence that has no rule yet.** In round 2 it was 16%.
3. **The threshold does not buy it back.** Spell alone, over tau:

| tau | Sentences that join | Exact | Inside a longer VAR | No rule yet | Exact, at the end of the run | Inside a longer VAR, at the end |
|---|---|---|---|---|---|---|
| 0.2 | 93.9% | 13.2% | 52.9% | 15.6% | 9.5% | 69.1% |
| 0.3 | 88.1% | 13.3% | 41.3% | 25.9% | 12.8% | 61.9% |
| 0.4 | 81.8% | 15.8% | 26.2% | 37.1% | 15.2% | 52.2% |
| 0.5 | 75.6% | 16.1% | 16.2% | 48.5% | 16.1% | 45.2% |
| 0.6 | 65.9% | 13.4% | 7.8% | 63.4% | 16.4% | 31.3% |
| 0.7 | 55.0% | 9.2% | 3.0% | 76.4% | 11.9% | 18.4% |
| 0.8 | 45.5% | 5.2% | 0.4% | 88.3% | 6.8% | 10.6% |

Lower the threshold and more sentences join, but the templates wear down and the slots end up inside longer VARs. Raise it and the VARs are tighter, but most sentences that hold a slot have no template. No value passes 16.4%. A template only ever loses constants, so by the end of the run 45% of the slots sit inside a longer VAR at tau 0.5.

The limit is the unit, one template for a whole sentence, and not a setting. That is what ADIOS is for: its patterns are parts of sentences, shared between sentences.

## 5. What KATO did here, and what was awkward

**Did.**

1. The matcher is the subsequence. `missing` and `extras` give each gap.
2. Retire and un-retire are the edit, and they hold on a service.
3. A pattern's name is its content. Two types whose templates become the same text are one pattern, which the benchmark does with a hash of the text.

**Awkward.**

1. **No order of learning in a prediction.** The tie rule needs it. The reader numbers the types.
2. **No record of what replaced what.** The reader keeps that too.
3. **A message type is not a pattern.** Content comes back, and then one pattern name has stood for two types. KATO counts the content: a template that comes back starts from its earlier frequency.
4. **One symbol is not a pattern.** 1,268 of the 32,000 log lines.
5. **A rule's frequency restarts at every edit**, because the edited rule is a new pattern. The count of a type's lines is spread over its versions.
6. **node_2a learns the names of rule versions**, some of them retired later.
7. **Through REST the loop is 70 to 200 times slower.** A read is four calls and a learn is one.

## 6. Where this round is weak

1. **Dialogue.** Section 4. A method shown on logs is at home on logs.
2. **A VAR belongs to one template.** 2,096 VAR ids on the probe (round 2: 1,473 with rules read first, 2,162 without). Identity by shared members is not built.
3. **The service checks are samples.** Two of 16 systems with a digest and 300 of 3,873 sentences. The full benchmark and the full probe ran in-process.
4. **Paper is my code.** I wrote it from the paper's description. It is checked against the benchmark's code without its shortcuts (equal on 13 systems, within 0.008 on three), not against the authors' own code or data.
5. **HPC flatters the loop on KATO**, for the reason in section 1.
6. **Tau is the benchmark's per system.** Nothing was tuned on the logs. On dialogue the sweep says tuning would not help.
7. **Round 2's `fold` and `topdown` are still in the code.**

## 7. Next, as agreed

ADIOS, for what Spell does not do: patterns that are parts of a sequence, when a gap is a slot at all (its significance test), which VARs are one class (shared members), and how patterns nest.

Two things about it to settle with the design, before code:

1. **A yardstick.** Its paper measures precision and recall against an artificial grammar it knows, and recall on ATIS. I will propose one of those to hold the KATO version to, as the log benchmark held this round.
2. **It is a batch method.** It passes over a corpus several times and its result depends on the order of the sentences. KATO learns as data arrives and uses no random seed. The design has to say what is kept of ADIOS when the order is fixed and the data arrives once.

## 8. Sources

- Zhu et al. (2019), "Tools and Benchmarks for Automated Log Parsing". https://arxiv.org/abs/1811.03509 (Table IV)
- Du and Li (2016), "Spell: Streaming Parsing of System Event Logs", ICDM 2016, 859-864. https://doi.org/10.1109/ICDM.2016.0103
- He, Zhu, Zheng and Lyu (2017), "Drain: An Online Log Parsing Approach with Fixed Depth Tree", ICWS 2017, 33-40. https://doi.org/10.1109/ICWS.2017.13
- logparser, https://github.com/logpai/logparser at commit `d9d4180`: `logparser/Spell/Spell.py`, the benchmark scripts, `data/loghub_2k`.
- Loghub, https://github.com/logpai/loghub. The Loghub paper: Zhu, He, He, Liu and Lyu (2023), https://arxiv.org/abs/2008.06448
- KATO at `f32bac0`: `kato/api/endpoints/sessions.py` (retire, un-retire, observe-sequence, learn), `kato/informatics/knowledge_base.py` (`learnPattern`), `kato/workers/pattern_operations.py` (`get_pattern`), `kato/storage/redis_writer.py` (the retired-pattern registry).

## 9. Checks and how to rerun

1. 81 tests pass in-process. 19 of them also pass through a KATO service.
2. The reports of rounds 1 and 2 are unchanged: sha1 `818a4c2a` and `7c8150fb`.
3. Numbers, in `experiments/results/`: `log_benchmark_2026-11-24.json`, `baselines_2026-11-24.json`, `spell_tau_sweep_2026-11-24.json`, `sgd_probe_templates_loop_2026-11-24.json`, and the service runs in `log_benchmark_through_a_kato_service_2026-11-24.json` and the two `sgd_probe_first_300_*` files.

```sh
.venv/bin/python -I experiments/log_benchmark.py --data ../loghub-data --fetch
./run.sh experiments/baselines.py --data ../sgd-data
./run.sh experiments/baselines.py --data ../sgd-data --sweep
./run.sh experiments/sgd_probe.py --data ../sgd-data --only 23 24
./run.sh examples/explore.py "book for two at seven . book for six at seven . book for six at nine ." \
    span=sequence markers=. slots=gap values=sequence loop=templates

# through a running KATO service; a new tag for every run
KATO_API=http://127.0.0.1:8000 KATO_API_TAG=check1 .venv/bin/python -m pytest -q
KATO_API=http://127.0.0.1:8000 KATO_API_TAG=check2 .venv/bin/python -I experiments/log_benchmark.py \
    --data ../loghub-data --only Mac --skip reference plain paper lone Drain --save service.json
KATO_API=http://127.0.0.1:8000 KATO_API_TAG=check3 ./run.sh examples/sequences.py > report_service.txt
```
