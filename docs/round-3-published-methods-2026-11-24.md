# HPCRD for KATO, round 3: what published methods already settle

24 Nov 2026. Follows `round-2-sequences-and-gap-variables-2026-11-24.md`. Branch `claude/published-methods`.

> **Corrected in round 4** (`round-4-log-benchmark-and-outer-loop-2026-11-24.md`). The text below is as it was written.
>
> 1. **Spell's average on the log benchmark.** Sections 1 and 5 quote 0.751, which is what the benchmark paper's Table IV prints. The sixteen values the table gives for Spell average 0.793 (IPLoM: 0.777 printed, 0.806 averaged; Drain: 0.865 and 0.866).
> 2. **The loop on KATO, sections 0, 2 and 3.** Those numbers (933 templates, 749 with two or more lines, 16.1% of slots, 52 un-retires) were measured with ties going to the smaller pattern name, and with a line's type looked up by the name of the pattern it had joined. Ties now go to the older type, as in the benchmark's implementation, and a line stays with its message type: 941 templates, 771 with two or more lines, 15.6% of slots, 54 un-retires.
> 3. **What retiring does, section 3.** "Every read skips it" is not what KATO does. Predictions skip a retired pattern; `GET /pattern/{name}` still returns it. And KATO refuses to learn a retired pattern again until it is un-retired. Both were seen on a running service in round 4, and the in-process node now does the same.
> 4. **"Nothing went through KATO's API"** and weak point 4 are no longer the state of things: round 4 ran the loop on a KATO service.

> **Corrected on 26 Nov 2026.** The scoring of the Spell runs written in Python counted the sentences that joined the very first template as having no rule (the template's number, 0, was read as "none"). Fixed in `experiments/baselines.py`, with a test. No percentage in section 0 changes. In section 2, for Spell at tau 0.5: 16.5% of the slots inside a longer VAR as the lines arrived (not 16.2%), 4,011 VAR spans (not 4,003), and 45.5% inside a longer VAR at the end (not 45.2%). At tau 0.7: 1,686 VAR spans (not 1,682). Drain's rows and the rows for the loop on KATO are as they were. The corrected numbers are in `experiments/results/baselines_2026-11-26.json`.

Round 2 ended with two questions. Your answer to both was the same: decide by prior art, and use what others have shown to work instead of reinventing it. This note does that. Everything ran in-process; nothing went through KATO's API.

## 0. In one screen

| Question | Decision | Whose design it is |
|---|---|---|
| How does node_2b hold a VAR's values? | One pattern per value, the value as its own tokens: VAR 1, then `new`, then `york`. | Spell: a line's parameter is the tokens at the placeholder. ADIOS: a class is a set of members tied to its pattern. Neither stores combinations of alternatives. |
| What decides constant or variable, and when a rule is reused? | Spell's loop: compare a new sequence with the templates, not with every earlier sequence; join the best one; replace that template with its generalisation. | Du and Li (2016) |
| What gives a VAR its identity? | Shared members. | ABL: a constituent seen before keeps its type, and types that cover the same constituent merge. ADIOS: an existing class is adopted when the overlap passes 0.65. |
| How is a VAR refined, and how do chunks nest? | ADIOS: significant patterns, classes of interchangeable units, and patterns becoming units. Not built yet. | Solan, Horn, Ruppin and Edelman (2005) |

**The evidence for the second row.** Spell, as published, on the probe of round 2 (3,873 dialogue sentences, 1,388 annotated slot spans):

| | Slots exactly one VAR | Rules or templates | Of those, used more than once | Seconds |
|---|---|---|---|---|
| Spell, as published (tau 0.5) | 16.1% | 944 | 771 | 1.7 |
| Spell's loop on KATO's matcher | 16.1% | 933 | 749 | 107.0 |
| Round 2: the nearest decide | 16.0% | 1,935 | 251 | 80.7 |
| Round 2: and rules read first | 14.4% | 1,207 | 394 | 29.8 |
| Round 2: and reading inside each VAR | 21.6% | 1,753 | 541 | 190.0 |

A streaming method from 2016 finds as many slots as the two procedures I built in round 2, with fewer rules (944 against 1,207 and 1,935) and more of them reused (771 against 394 and 251). Only the inside reading does better, and that is the part ADIOS addresses. The seconds come from separate runs on a shared machine: read them as orders of magnitude.

**Your yes is needed for one thing:** fetching the log benchmark's sample files (section 5), so that the loop on KATO can be held to Spell's published accuracy.

## 1. The published methods, and what each was shown to do

Read on 24 Nov 2026: the method and results sections of each paper, through one question to each text. None was read through.

| Method | What it does | Shown on | Result as published |
|---|---|---|---|
| **Spell** (Du and Li 2016) | One template per message type. A new line joins the type whose template shares the longest common subsequence with it, if that is at least half the line (tau 0.5; the paper states the boundary both ways; ties go to the shorter template). The template becomes that subsequence, with `*` where the two disagree and adjacent `*` merged. Otherwise the line is a new type. | Two supercomputer logs | Accuracy 0.823 (Los Alamos HPC, 433,490 records) and 0.812 (BlueGene/L, 4,747,963 records) |
| **Drain** (He et al. 2017) | Lines are first grouped by token count. A wildcard is set where a line and its template differ at the same position. | Log benchmark below | Best average of the parsers compared |
| **Log benchmark** (Zhu et al. 2019) | 2,000 sampled lines from each of 16 systems, templates labelled by hand. A line is right only if its template groups it with exactly the lines the labels do. | 16 systems | Average accuracy: Drain 0.865, IPLoM 0.777, AEL 0.754, Spell 0.751, LenMa 0.721 |
| **ABL** (van Zaanen 2000) | Every sentence is aligned with every other by edit distance. The parts that differ are hypothesised constituents of one type. All hypotheses are kept, then overlapping ones are resolved by how often each was seen. | ATIS (716 sentences), OVIS | Non-crossing brackets precision 85.31 and recall 89.31 on ATIS for the best variant. A right-branching baseline scores 82.70 and 92.91. |
| **ADIOS** (Solan et al. 2005) | Sentences are paths in a graph. A pattern is a stretch where paths bundle together, found by a significance test on how many paths stay on it (cutoff eta, level alpha). Units that fill one slot in the same context form an equivalence class; an existing class is adopted when it overlaps by more than 0.65. A pattern becomes a new unit, and the search repeats. | Artificial grammars, ATIS-2, protein sequences | ATIS-2: recall 40% on 343 held-out sentences, precision about 70% as judged by people; perplexity 11.5 against about 14 for a smoothed trigram model. Proteins: 95% correct classification of 6,751 enzymes. |
| **Slot schema induction** (Yu et al. 2022) | Candidate slots come from in-domain language models and unsupervised parse structure, then clustering. | MultiWOZ, SGD | The published method for dialogue slots on this very data set. It depends on language models, so it is not a candidate for KATO. |

Three things follow.

1. **For templates with gap variables there is a benchmark with published numbers.** That is where "proven" can be checked for our code.
2. **On dialogue slots no symbolic method has published numbers that I found.** Our slot agreement on SGD stays our own probe, not a benchmark.
3. **ABL's own baseline is close to it.** Alignment alone is weak evidence for structure in language. ADIOS adds the significance test.

## 2. The same probe, with the published parsers

`experiments/baselines.py`. Drain runs through the `drain3` package (0.9.11) with its defaults. Spell is written from the paper's description, because published implementations read log files; it reproduces the paper's two worked examples and has not been run on the paper's data.

Each sentence is judged against its template as it stood when the sentence arrived, which is how the module was judged in round 2.

| Parser | Templates | With two or more lines | Lines that joined a template | Slots exactly one VAR | Slots tiled by several | Slots inside a longer VAR | VAR spans |
|---|---|---|---|---|---|---|---|
| Drain, threshold 0.4 (default) | 1,722 | 482 | 55.5% | 10.8% | 12.0% | 0 | 6,264 |
| Drain, threshold 0.6 | 2,246 | 451 | 42.0% | 4.9% | 4.3% | 0 | 2,410 |
| Spell, tau 0.5 (default) | 944 | 771 | 75.6% | 16.1% | 0 | 16.2% | 4,003 |
| Spell, tau 0.7 | 1,742 | 825 | 55.0% | 9.2% | 0 | 3.0% | 1,682 |
| Spell's loop on KATO, tau 0.5 | 933 | 749 | 74.8% | 16.1% | 0 | 15.9% | 4,040 |
| Spell's loop on KATO, tau 0.7 | 1,737 | 806 | 54.1% | 9.2% | 0 | 3.0% | 1,691 |

1. **Spell does on dialogue text what round 2's nearest-and-rules-first did**, with one template per type instead of one rule per pair of sentences.
2. **Drain shows the limit of one variable per position again.** `new york` and `boston` are lines of different length, so they never share a template. Its slots are mostly tiled.
3. **Spell's templates wear down.** Judged against the templates at the end of the run, 45.2% of the slots sit inside a longer parameter (16.2% as the lines arrived). Every line that joins can only remove constants. Spell has no step that splits a type again.

## 3. Spell's loop on a KATO node

`hpcrd/templates.py`, 62 tests passing.

| Spell | KATO |
|---|---|
| Longest common subsequence of line and template | The matcher: `matches`, with `missing` and `extras` for what each side has in the gaps |
| A template | A pattern of tokens and one placeholder symbol |
| Replace the template with its generalisation | Learn the new pattern and **retire** the old one |

**Retire is KATO's own.** `POST /sessions/{id}/patterns/retire` puts a tombstone on a pattern: it stays stored, every read skips it, and `un-retire` brings it back. So a rule is edited as data arrives, and every earlier version of it is kept.

```
Temperature (41C) exceeds warning threshold        learned as 7b3e76
Temperature (42C, 43C) exceeds warning threshold   joins it:  056391 = [Temperature] [VAR|*] [exceeds] [warning] [threshold]
                                                   7b3e76 is retired, still stored
Temperature (41C) exceeds warning threshold        joins 056391, frequency 2, its parameter is (41C)
```

On the probe, at tau 0.5: 3,841 learns and 3,841 predictions; 2,193 patterns stored, 1,260 of them retired, 933 live. The result is Spell's own to within tie-breaks: 16.1% against 16.1%, 933 templates against 944.

**What is not Spell's here.**

1. KATO returns the templates above the node's `recall_threshold` (0.1 here); Spell looks at all of them.
2. Ties go to the shorter template, then to the smaller pattern name. Spell leaves the second tie open.
3. Spell's test is matches over the line's length. KATO's gate is the symmetric similarity. The reader computes Spell's test from `matches`.

**What is awkward.**

1. **A pattern's name is its content.** When a template generalises to content that was a template once and was retired, it is the same pattern, and has to be un-retired. That happened 52 times.
2. **KATO does not record which pattern replaced which.** The reader keeps that link itself.
3. **Cost.** 107 s in-process against 1.7 s for Spell alone. The in-process node builds a full prediction for every candidate.

## 4. What this replaces in round 2

| Round 2 | Replaced by |
|---|---|
| `fold='all'` and `fold='nearest'` (which earlier sentences decide) | Nothing decides by vote. A sequence is compared with templates, and joins one. |
| `topdown`, node_1t and `rule_of` (a rule reads a sequence first) | The template node is the rule store. Reading by rule is the loop itself. |
| A new rule whenever a sentence is generalised against its neighbour | The joined template is edited: learn the new one, retire the old one. |
| Rule-scoped VAR ids | Classes by shared members (ABL, ADIOS). Not built. |
| `inside=True` (my first cut) | ADIOS: significance test, classes, patterns as units. Not built. |

What stays: whole sequences, one VAR per gap, values as tokens in node_2b, chunks in node_1a, rule names in node_2a.

One open point of design. Spell needs no node of raw sequences: a type's first line is its template. ADIOS does need every sequence, as a path. Your node_0 is what ADIOS would read.

## 5. For you to decide

1. **The log benchmark.** I would like to fetch the 2,000-line samples with their hand-labelled templates (`data/loghub_2k` in `github.com/logpai/logparser`) and hold the loop on KATO to the published per-system accuracy: Spell 1.000 on HDFS, 0.787 on BGL, 0.751 on average. The benchmark paper gives no licence; it says the data sets are "freely accessible for research purposes". The files would be fetched at run time, pinned by hash and kept out of the repository, as with SGD. Yes or no?
2. **The order.** First, Spell's loop becomes the module's outer loop and round 2's `fold` and `topdown` go. Second, ADIOS for classes and nesting. I would not start the second before the first matches its published numbers.
3. **Pull requests.** PR 1 (round 2) and PR 2 (this) are drafts. Nothing is merged without your say.

## 6. Where this note is weak

1. **Spell on dialogue is outside what its authors showed.** The probe says it does no worse than my own procedures there. It does not say it is right for language.
2. **My Spell is from the paper's description.** It matches the paper's two examples. Until it is run on the benchmark, "as published" means "as described".
3. **ADIOS is described, not built.** Its criterion needs counts of how many sequences pass through each stretch, and four parameters. That is real work, and its best published result on the large artificial grammar combines 150 learners.
4. **The retire mirror is not checked against a running KATO.** It follows the endpoint's own description.
5. **Tau 0.5 comes from logs.** On the probe 0.7 finds fewer slots (9.2%). No value has been tuned.

## 7. Sources

- Du and Li (2016), "Spell: Streaming Parsing of System Event Logs", ICDM 2016, 859-864. https://doi.org/10.1109/ICDM.2016.0103 Authors' copy: https://users.cs.utah.edu/~lifeifei/papers/spell.pdf
- He, Zhu, Zheng and Lyu (2017), "Drain: An Online Log Parsing Approach with Fixed Depth Tree", ICWS 2017, 33-40. https://doi.org/10.1109/ICWS.2017.13
- Zhu et al. (2019), "Tools and Benchmarks for Automated Log Parsing". https://arxiv.org/abs/1811.03509
- van Zaanen (2000), "ABL: Alignment-Based Learning", COLING 2000. https://aclanthology.org/C00-2139/ Same paper: https://arxiv.org/abs/cs/0104006
- Solan, Horn, Ruppin and Edelman (2005), "Unsupervised learning of natural languages", PNAS 102(33), 11629-11634. https://doi.org/10.1073/pnas.0409746102 Full text: https://pmc.ncbi.nlm.nih.gov/articles/PMC1187953
- Yu, Wang, Cao, Shafran, El Shafey and Soltau (2022), "Unsupervised Slot Schema Induction for Task-oriented Dialog", NAACL 2022, 1174-1193. https://aclanthology.org/2022.naacl-main.86
- KATO, `kato/api/endpoints/sessions.py` at `f32bac0`: the retire and un-retire endpoints.

## 8. Checks and how to rerun

1. 62 tests pass, in-process. The round 1 and round 2 reports are unchanged.
2. Spell as written here, and the loop on KATO, both give the paper's two worked templates (`tests/test_templates.py`).
3. The baseline numbers are in `experiments/results/baselines_2026-11-26.json`; round 2's are in `sgd_probe_2026-11-24.json`.

```sh
uv pip install --python .venv/bin/python drain3
./run.sh experiments/baselines.py --data ../sgd-data --save out.json
.venv/bin/python -m pytest -q tests/test_templates.py
```
