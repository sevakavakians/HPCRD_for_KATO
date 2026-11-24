# HPCRD for KATO, round 2: whole sequences, one VAR per gap, and what real text does to both

24 Nov 2026. Follows `claude/kato-chunks-rules-examples.md` (round 1, the six worked examples).

Code: `HPCRD_for_KATO`. `main` holds round 1 as a package with tests; the branch `claude/sequences-and-gap-variables` holds this round. KATO read at `main` `f32bac0` (v7.1.0-34-gf32bac0). Everything below ran in-process on KATO's own matcher, `Pattern` and scoring classes. Nothing in this round went through KATO's API.

## 0. In one screen

Your six points, numbered as in your message.

| # | Your point | What I built | Result |
|---|---|---|---|
| 1 | Whole sentences at node_0 | `span='sequence'` | Works. One pattern and one prediction per sentence instead of per token, with the same rule on text 1 and fewer, cleaner rules on text 5. No echoes, no record kept by the module. Costs: the boundary comes from the application, and comparison is no longer local. |
| 2, 3 | A gap is one VAR; refine it over time | `slots='gap'`, `values='sequence'`, `inside=True` | Works on the examples: `new york` is one value, counted (f=2). Start long. Refine inside the VAR, not in the rule. On real text it needs two more things (below). |
| 4 | Adjust `recall_threshold` | swept | Example texts: 0.7. Real text: it depends on which readings decide (section 6 and 8). |
| 5 | One pattern per VAR combination | three layouts compared | A pattern per combination of values grows with every instance and cannot be looked up by name. A pattern per value, spelled out as its tokens, does what the combination was for. I need to know which of two readings you meant (section 7). |
| 6 | Close analogs | solved by 1 | The "says meow" text gives its rule (f=3). |

Two things I added that you did not ask for, both off by default, because the probe on real text showed your plan needs them:

- **`fold='nearest'`**: only the most similar earlier sentences decide what is constant and what varies.
- **`topdown=True`**: a learned rule reads a new sentence before node_0 is asked.

**The probe** (section 8): 3,873 user sentences of the Schema-Guided Dialogue set, 1,388 annotated slot spans.

| | slot spans that are exactly one VAR | rules | rule instances of a known rule |
|---|---|---|---|
| One VAR per gap, every recalled sentence decides, 0.5 | 6.4% | 798 | 67% |
| ... the nearest decide | 16.0% | 1,935 | 21% |
| ... and learned rules read first | 14.4% | 1,207 | 64% |
| ... and each value is read inside its VAR | **21.6%** | 1,753 | 64% |

On the first 1,200 sentences, round 1's rolling windows with one VAR per position reach 17.8%, the best whole-sentence setting 17.5%. The windows take 158 s, 3,383 VAR spans and 2,775 VAR ids to do it; the whole sentences 14 s, 1,234 and 775.

**What I think.** Whole sentences and gap variables are the right base. They are not enough on real text: about one annotated slot in five is found exactly, at best. The gain came from reading inside VARs, which is your "refine over time", so that is where the next work belongs.

## 1. What changed in the code

Every choice is still a field of `Settings`. The defaults are round 1's, and `examples/report.txt` is unchanged (906 lines, same sha1).

| Setting | Values | What it does |
|---|---|---|
| `span` | `window`, `stream`, **`sequence`** | `sequence`: node_0 learns whole sequences. A marker token or `cut()` ends one. |
| `slots` | `position`, `gap` | Unchanged. `gap` is now the one to use with whole sequences. |
| `values` | `name`, **`sequence`** | How node_2b holds a value of several tokens: the name of a node_1a chunk, or its own tokens. |
| `fold` | `all`, **`nearest`** | Which readings label a position constant or variable. |
| `inside` | off, **on** | Read each new value against its VAR's earlier values. |
| `topdown`, `rule_threshold` | off, **on** | node_1t holds each rule spelled out; a rule that fits reads the sequence. |

`alignment.read(prediction, stm, whole=True)` reads two complete sequences end to end.

## 2. Whole sequences at node_0 (your point 1, and 6)

**Mechanism.** The module asks node_0 for predictions on the whole sentence, reads them, and only then lets node_0 learn the sentence. Three things follow.

1. **Nothing echoes.** The sentence is not in node_0 when it is read. Round 1 held out the windows learned in the last six steps and kept its own log of where each window was learned. Both are gone: a pattern's `frequency` is the number of earlier places it stands for.
2. **No edges.** Two whole sentences start together and end together. What stands before the first match or after the last one is a gap like any other, so `missing` and `extras` cover the whole sentence.
3. **No window limit on a chunk.**

```
sequence  the dog sat on the mat .
      ensemble  1 prediction.  node_0 then learns the sequence as PTRN|1a3d0c
        a3719f  the cat sat on the mat .      x1 | =  ~cat  =  =  =  =  =
      node_1a   PTRN|76a6fb = [sat on the mat .]
      node_1b   PTRN|16f905 = [the] [VAR|1] [PTRN|76a6fb(sat on the mat .)]   frequency 1
sequence  the bird sat on the mat .                                           -> RECOGNISED, frequency 2
```

The chunk and the rule have the same names as in round 1. A name is the hash of the content, so the same content found another way is the same pattern.

**The same texts three ways** (window 7, `recall_threshold` 0.5, one VAR per position):

| | Text 1 (21 tokens) | | | Text 5 (72 tokens) | | |
|---|---|---|---|---|---|---|
| | per window | stitched | whole | per window | stitched | whole |
| node_0 patterns | 15 | 15 | 3 | 63 | 63 | 9 |
| node_0 symbols stored | 105 | 105 | 21 | 441 | 441 | 72 |
| node_0 predictions asked | 21 | 21 | 3 | 72 | 72 | 9 |
| records kept by the module | 15 | 15 | 0 | 63 | 63 | 0 |
| node_1a chunks | 9 | 1 | 1 | 38 | 5 | 6 |
| node_1b rules | 5 | 1 | 1 | 25 | 4 | 3 |
| rules seen again | 1 | 1 | 1 | 7 | 3 | 3 |
| VARs | 5 | 1 | 1 | 19 | 4 | 3 |

Texts 2 and 4 are in the report. Text 2 gives the chunk `[sat on the mat by the door .]`, eight tokens, as one contiguous match.

**Close analogs (point 6).** `the cat says meow . the dog says woof .` twice. Windows of 7 found no rule. Whole sentences:

```
node_1b  PTRN|0c8fce = [the] [VAR|1] [says] [VAR|2] [.]   f=3
node_2b  [VAR|1] [dog] [VAR|2] [woof] f=2    [VAR|1] [cat] [VAR|2] [meow] f=2
```

**What it costs.**

1. **The boundary is given.** A sentence end, a line, a turn. The system no longer segments the stream at that level. Goal 1 then lives inside the sequence (chunks) and above it (node_2a over rule names). Data with no natural boundary still needs rolling windows or the learned cuts. `span` keeps all three.
2. **Comparison is no longer local.** Similarity is measured over the whole sentence. Two long sentences that share one phrase are not recalled. Rolling windows compare seven tokens with seven tokens wherever they stand. Section 8 shows the price: in the best run 16% of the annotated slots sit in sentences that got no rule at all.
3. **A short rule with a long value fails the gate.** `play the long and winding road .` against `play imagine .` is 2·2/(7+3) = 0.40. Section 5 handles that case.

## 3. One VAR per gap, its value kept whole (your points 2 and 3)

**Your plan, as built.** A run of positions that vary is one VAR, whatever its length (`slots='gap'`). node_2b holds the value as its own tokens, `[VAR|1] [new] [york]` (`values='sequence'`). Learning it again raises its frequency, so a value seen several times is counted: that is your "ground truth".

```
show flights from boston / dallas / new york / los angeles / new york / new york city / new jersey to denver .

node_1b  PTRN|27641b = [PTRN|ac5190(show flights from)] [VAR|1] [PTRN|c97f0b(to denver .)]   f=6
node_2b  [VAR|1] [new] [york]         f=2
         [VAR|1] [new] [york] [city]  f=1
         [VAR|1] [new] [jersey]       f=1
         [VAR|1] [los] [angeles]      f=1
         [VAR|1] [dallas]  f=1        [VAR|1] [boston]  f=1
```

One rule, one VAR, six instances. With one VAR per position the same text gives three rules and three VARs. The first `new york` is dropped as noise (two tokens against one), and so is `city`.

**KATO binds the value itself.** node_1b's own prediction, as returned:

```
observe at node_1b: [PTRN|ac5190] [new] [york] [city] [PTRN|c97f0b]
    matches  ["PTRN|ac5190", "PTRN|c97f0b"]
    missing  [[], ["VAR|1"], []]
    extras   [[], ["new"], ["york"], ["city"], []]
    one gap: 3 extras against 1 missing -> [VAR|1] <- [new york city]
```

**The sketch text of your first brief**, whole sentences:

```
one VAR per position:  [VAR|1] [book a table for] [VAR|2] [VAR|3] [VAR|4] [at seven] [VAR|5] [.]   5 VARs, 18 node_2b patterns
one VAR per gap:       [VAR|1] [book a table for] [VAR|2] [at seven] [VAR|3] [.]                   3 VARs, 10 node_2b patterns
```

`two quiet adults`, `six hungry diners` and `four tired guests` never recombine in that text. Nothing in it says the value is three variables. One VAR per position invented them, and round 1 then needed "values that go together" to tie them back.

## 4. Start long, refine inside (your "refine it over time")

**Would your plan work?** Yes for values that recur whole. On real text most values occur once, so "seen multiple times" cannot be the only evidence. The routine for the rest has to work from parts that a value shares with other values of the same VAR.

**Start long or start small?** Start long. Four reasons.

1. **It is what KATO returns.** A gap between two matches is one unit in `missing` and `extras`. Pairing positions inside a gap is the module's own addition, and it is only defined when both sides have the same length.
2. **Nothing is lost.** The value is stored whole, so it can be cut later. A value of another length that was dropped as noise cannot be merged back.
3. **The rule stays the same rule.** If refining rewrites the rule, every refinement makes a new node_1b pattern, leaves the old one behind, and breaks node_2a's sequences of rule names. If refining describes the inside of the VAR, the rule's name never changes.
4. **The routine already exists.** node_2b holds each value as `[VAR, token, ...]`. Asked about a new value, its ensemble lines the value up with the VAR's earlier values, the way node_0 lines a sentence up with earlier sentences. The VAR symbol is a matched anchor at the start.

**What the reading says about a new value** (`inside=True`, before the value is learned):

| An earlier value of the same VAR | Says |
|---|---|
| the same | the value is a unit, seen whole before |
| shares no token | another unit; silent about the inside |
| shares some tokens | the shared parts and the differing parts are the value's own constants and slots |

A value with two or more parts, one of them varying, is recorded as what the VAR is made of: an inner rule in node_1b, and `[VAR, PTRN|<inner rule>]` in node_2b.

**Parts that recombine.**

```
book a table for two quiet adults / four hungry diners / two hungry diners / four quiet adults at seven .

node_1b  PTRN|ab1799 = [PTRN|6454f3(book a table for)] [VAR|1] [PTRN|6bb8f0(at seven .)]   f=3    the rule, unchanged throughout
         PTRN|d9bcdc = [VAR|2] [VAR|3]                                                      f=2    what VAR|1 is made of
node_2b  [VAR|1] [PTRN|d9bcdc]  f=2
         [VAR|2] [two]  [VAR|2] [four]        [VAR|3] [quiet] [adults]  [VAR|3] [hungry] [diners]
         [VAR|1] [two] [quiet] [adults] ...   the four values seen whole, each f=1
```

The third sentence is partly like both earlier ones: `two` is shared with one, `hungry diners` with the other. That is the cut. The fourth sentence finds the inner rule already there.

**Units, and values that share a part** (the cities text):

```
[new york]        seen whole 1 time before                      a unit
[new york city]   partly like [new york] x2     -> [PTRN|86a351(new york)] [VAR|2]      VAR|2: city
[new jersey]      partly like [new york] x2,    -> [new] [VAR|3]                        VAR|3: jersey, york, york city
                  [new york city] x1
[los angeles]     shares no token with any                      a unit, seen once
```

`[new] [VAR|3]` is true of the form and says nothing of the meaning. Whether one shared token is enough is `min_support`'s job. I left it at 1.

**Parts that never recombine stay one value.** The sketch text gives no inner rule.

**What starting small does well.** Merging is how repeated material becomes a unit, and node_1a already does it: a contiguous match is a chunk. So both directions are in the design. Chunks merge upward by repetition. VARs split downward by contrast.

## 5. A learned rule reads a new sequence

Not in your message. Section 8 is why it is here.

**Mechanism.** node_1t holds each rule with its chunks spelled out: `[show] [flights] [from] [VAR|1] [to] [denver] [.]`. KATO lines the raw sentence up with those. A rule fits when every constant is matched, in order, and what is left stands, gap for gap, against exactly one VAR. Of the rules that fit, the one with the most constants reads the sentence. If none fits, node_0 is asked as before.

```
sequence  play the long and winding road .
      node_1t   d3e564  play VAR|2 .  x1 | =  u  u  u  u  u  =
      node_1b   PTRN|d3e564 = [play] [VAR|2] [.]   frequency 2
      node_2b   [VAR|2] [the long and winding road]   (new value)
sequence  show me flights from boston to denver .     `me` stands against no VAR: the rule does not fit, node_0 is asked
```

A rule needs no earlier sentence of the same length. A sentence compared with sentences needs one that is close.

node_1t exists because a name inside a pattern is opaque to matching (Language Lab finding 60). It holds nothing KATO does not already hold: each of its patterns is a node_1b rule with its names unravelled through node_1a.

## 6. `recall_threshold` (your point 4)

With one symbol per event, KATO's similarity is 2 · matches / (pattern length + observed length). For two 7-token sentences: one token differs 0.857, two differ 0.714, three differ 0.571. With whole sentences the threshold is an edit budget relative to sentence length.

Example texts, one VAR per gap. Cells are rules / rules seen again / VARs.

| Text 5 | 0.1 | 0.3 | 0.5 | 0.7 | 0.9 |
|---|---|---|---|---|---|
| every recalled sentence decides | 5 / 1 / 7 | 4 / 2 / 6 | 5 / 3 / 8 | **3 / 3 / 3** | 0 / 0 / 0 |
| the nearest decide | 5 / 3 / 6 | 5 / 3 / 6 | 5 / 3 / 6 | **3 / 3 / 3** | 0 / 0 / 0 |

At 0.1 with every sentence deciding, text 5's most frequent rule is `[the] [VAR|6] [.]` (f=4) and text 4's is `[VAR|4] [the] [VAR|5] [.]` (f=4). At 0.7 text 5 gives its three rules, each seen twice.

On real text the answer changes with `fold` (section 8):

- Every recalled sentence decides: best at 0.6, and poor everywhere.
- The nearest decide: lower is better (0.4 and 0.5), because the threshold then only removes candidates.
- Rules read first: `rule_threshold` 0.5 to 0.6.

## 7. node_2b: a pattern per VAR combination (your point 5)

I can read your example `[[VAR|1],[a1],[a2],[a3]]`, `[[VAR|1],[a2],[a4],[a5]]` two ways.

- **K, a combination of values.** a1, a2, a3 are alternatives seen together, for example in one ensemble. A new combination is a new pattern.
- **S, a value spelled out.** a1 a2 a3 are the tokens of one value, `[VAR|1] [new] [york] [city]`.

I took K as what you meant and built both. P is round 1's layout: one pattern per VAR and value, a value of several tokens by its chunk name.

Cities text, six instances of one rule:

| | Patterns | Symbols stored | Is `new york` a value of VAR\|1? | Which values are like `new jersey`? | How often did a value stand there? |
|---|---|---|---|---|---|
| P | 6 | 12 | one lookup by name | nothing: names are opaque | frequency |
| S | 6 | 17 | one lookup by name | `new york` x2 (`= = ~york`), `new york city` x1 | frequency |
| K | 5 | 25 | no name to look up; 4 combinations hold it | nothing | no: frequency counts combinations |

K in sorted order, as the instances arrive: 2, 3, 4, 4, 5, 6 values. Each new value makes a new, longer pattern, so n values cost about n²/2 symbols. Replayed in the reverse order with the VAR held fixed, the six instances give S the same 5 patterns (the five values that were observed) and K 1 of 5.

**Recommendation.** S for a VAR's values. It is what section 4 reads. Keep "values together" for the case a combination is really needed: the values of different VARs in one instance (`[VAR|1] [dog] [VAR|2] [woof]`).

## 8. A probe on real text

**Data.** User turns of the Schema-Guided Dialogue set (Rastogi, Zang, Sunkara, Gupta and Khaitan 2020; CC BY-SA 4.0). Three files of the train split, pinned by commit `e852981` and sha256, fetched from the original host at run time, kept out of the repository. 384 dialogues, 2,967 user turns, services Restaurants_1 and Media_1.

**Preparation.** Tokens are words and punctuation marks, lower-cased. A sentence ends after `.`, `?` or `!`. 3,873 sentences, 30,373 tokens, median 7 tokens. 1,388 annotated slot spans fall inside one sentence (5 are cut by a sentence end and set aside).

**Measure.** A slot span counts as found when one VAR covers exactly its tokens. The annotation marks non-categorical slots only (city, time, cuisine, date, restaurant name, title). A VAR on anything else, a party size or a turn of phrase, counts as "no annotated slot". So the slot side is firm and the VAR side is a floor.

All sentences. Seconds are in-process on a shared two-core machine: compare within a table.

| Setting (whole sentences, one VAR per gap unless said) | Sentences with a rule | Slots exactly one VAR | Slots inside a longer VAR | VAR spans | VARs exactly a slot | Rules | Seen again | Instances of a known rule | VAR ids |
|---|---|---|---|---|---|---|---|---|---|
| one VAR per position, 0.6 | 66.1% | 9.9% (+7.8% tiled) | 0 | 6,349 | 2.2% | 1,657 | 282 | 35.8% | 3,796 |
| all decide, 0.5 | 62.5% | 6.4% | 51.0% | 3,454 | 2.6% | 798 | 171 | 67.0% | 1,373 |
| all decide, 0.6 | 65.7% | 7.9% | 25.1% | 3,882 | 2.8% | 1,157 | 215 | 54.5% | 1,835 |
| all decide, 0.7 | 49.7% | 6.6% | 6.6% | 2,697 | 3.4% | 1,006 | 231 | 47.7% | 1,285 |
| nearest decide, 0.4 | 68.8% | 17.4% | 25.9% | 3,085 | 7.8% | 2,110 | 269 | 20.9% | 2,483 |
| nearest decide, 0.5 | 63.4% | 16.0% | 20.5% | 2,715 | 8.2% | 1,935 | 251 | 21.1% | 2,162 |
| nearest decide, 0.7 | 33.1% | 5.9% | 3.0% | 1,116 | 7.3% | 980 | 161 | 23.5% | 803 |
| nearest 0.5, rules first 0.5 | 87.1% | 14.4% | 31.7% | 3,941 | 5.1% | 1,207 | 394 | 64.2% | 1,473 |
| nearest 0.5, rules first 0.6 | 83.9% | 15.1% | 26.4% | 3,542 | 5.9% | 1,493 | 419 | 54.0% | 1,788 |
| nearest 0.5, rules first 0.5, inside | 87.1% | **21.6%** | 19.2% | 4,404 | 6.8% | 1,753 | 541 | 64.3% | 2,317 |

The first 1,200 sentences (377 slot spans), with round 1's rolling windows:

| Setting | Slots exactly one VAR | VAR spans | Rules | Instances of a known rule | VAR ids | Seconds |
|---|---|---|---|---|---|---|
| windows of 7, one VAR per position, 0.5 (round 1) | 17.8% (+7.7% tiled) | 3,383 | 861 | 16.3% | 2,775 | 158.4 |
| windows of 7, one VAR per gap, 0.5 | 12.7% | 1,530 | 592 | 36.2% | 1,081 | 152.2 |
| sentences, one VAR per position, 0.6 | 5.8% (+1.6% tiled) | 1,256 | 475 | 28.0% | 831 | 4.3 |
| sentences, all decide, 0.5 | 8.0% | 1,235 | 353 | 58.2% | 604 | 8.4 |
| sentences, nearest 0.5 | 12.7% | 869 | 643 | 18.1% | 720 | 7.1 |
| sentences, nearest 0.5, rules first 0.5 | 12.2% | 1,128 | 435 | 54.6% | 539 | 4.3 |
| sentences, nearest 0.5, rules first 0.5, inside | 17.5% | 1,234 | 598 | 54.6% | 775 | 13.9 |

**What the numbers say.**

1. **Every recalled sentence deciding collapses.** A position is variable if any earlier sentence has something else there. With enough sentences that is every position but the punctuation. The most frequent rules at 0.5 are `[VAR] [?]` (f=222), `[VAR] [.]` (f=181) and `[i] [VAR] [.]` (f=76). Half the slots sit inside a longer VAR. Round 1 folded the same way; its toy texts were too small to show it.
2. **The nearest deciding gives real frames**, for example `[do they serve] [VAR] [?]`, `[i want to watch] [VAR] [.]`, `[how expensive is] [VAR] [?]`. It also gives 1,935 rules of which 251 are ever seen again, because each sentence is generalised against its own nearest neighbour.
3. **Rules reading first consolidates.** Instances of a known rule go from 21% to 64%, sentences with a rule from 63% to 87%, and the run gets faster. It does not find more slots, because the rule that fits is often a short frame with one long VAR: `[i would like] [VAR] [.]`.
4. **Reading inside the VAR is what finds them.** 14.4% to 21.6%. In `i ' m in the mood for some chinese food tonight , preferably in millbrae .` the rule's VAR held everything after `for`. The inside reading cut it into `chinese`, `tonight` and `preferably in millbrae`. `chinese` is the annotated cuisine; the annotated city is still inside the third part.
5. **Whole sentences do not beat windows at finding slots. They match them at a fraction of the cost.** 17.5% against 17.8% on the same 1,200 sentences, with about a third of the VAR spans, under a third of the ids and a tenth of the time. Whole sentences with round 1's other choices are worse than windows (5.8% and 8.0%).
6. **A VAR id nearly always holds one kind of slot, and one kind of slot is spread over many ids.** In the best run 211 ids hold exactly a slot, 202 of them one slot name only. `city` is spread over 72 ids. Ids come from rules, and there are many rules.

**Where the other slots went** (best run, 1,388 spans): 300 exactly one VAR, 3 tiled by several VARs, 266 inside a longer VAR, 312 partly in a VAR, 281 constant in a rule or dropped, 226 in a sentence with no rule. Three things recur in the misses.

- **The annotation and the patterns cut differently.** `11 : 30 in the morning` is one annotated time. The module finds `[VAR] [: 30 in the morning]`, because `in the morning` recurs and the hour varies.
- **Tokenisation.** `10:30` is three tokens here, and `:` is a constant. Keeping such tokens whole (`--joined`) moved the exact share up by one to three points on the first 1,200 sentences: 12.7% to 15.6% with the nearest deciding, 17.5% to 18.3% in the best setting. Not the main factor.
- **Most variation in dialogue is wording, not slots.** `find me a sushi place` and `look for burger restaurants` differ in more than the cuisine.

**Limits of the probe.** One pass, three files, two services, in-process. No comparison with a published parser. Slot agreement is a narrow measure of rule quality.

## 9. Earlier work (your "there must be prior art")

Links checked on 24 Nov 2026. I read the abstracts and, for Drain, asked one question of the paper. None was read through.

**One variable per position against one per gap. Log parsing has both.**

- He, Zhu, Zheng and Lyu (2017), "Drain: An Online Log Parsing Approach with Fixed Depth Tree", ICWS 2017, 33-40. https://doi.org/10.1109/ICWS.2017.13 The first layer of its tree groups lines by token count, on the assumption that lines of one event have one length, and a wildcard is set where a line and its template differ at the same position. That is one VAR per position, with the limit round 1 ran into.
- Du and Li (2016), "Spell: Streaming Parsing of System Event Logs", ICDM 2016, 859-864. https://doi.org/10.1109/ICDM.2016.0103 Templates are longest common subsequences, kept up to date as lines arrive. In the authors' example `Temperature (41C) exceeds warning threshold` and `Temperature (42C, 43C) exceeds warning threshold` give `Temperature * exceeds warning threshold`: one placeholder for a gap of any length. KATO's similarity is the same subsequence, so `slots='gap'` is Spell's reading of it. Both parsers match a new line against templates first, which is section 5.

**The formal side.**

- Kutsia, Levy and Villaret (2014), "Anti-unification for Unranked Terms and Hedges", Journal of Automated Reasoning 52(2), 155-190. https://doi.org/10.1007/s10817-013-9285-6 Two kinds of variable: a term variable stands for one term, a hedge variable fills a gap. Their faster algorithm takes a common subsequence of the two inputs as the skeleton (a "rigidity function" chooses it) and generalises between its members. A rule with gap VARs is that construction, and "least general generalisation" is what `fold='nearest'` approximates.
- Angluin (1980), "Finding patterns common to a set of strings", Journal of Computer and System Sciences 21(1), 46-62. https://doi.org/10.1016/0022-0000(80)90041-0 Patterns of constants and variables, and the search for one that a set of strings has in common. The learnability results for such patterns are the place to look before claiming anything general about rules.

**Start small and merge.**

- Mikolov, Sutskever, Chen, Corrado and Dean (2013), "Distributed Representations of Words and Phrases and their Compositionality", NIPS 2013. https://arxiv.org/abs/1310.4546 Words that occur together often and apart seldom are replaced by one token before training. Bottom-up, by count.
- Nevill-Manning and Witten (1997), "Identifying Hierarchical Structure in Sequences: A linear-time algorithm", JAIR 7, 67-82. https://doi.org/10.1613/jair.374 SEQUITUR replaces a repeated phrase with a rule and repeats that on the result, incrementally. This is node_1a's direction: chunks by repetition, chunks of chunks.

**Deciding where a unit divides.**

- Goldsmith (2001), "Unsupervised Learning of the Morphology of a Natural Language", Computational Linguistics 27(2), 153-198. https://aclanthology.org/J01-2001/ Words are cut into parts by minimum description length. Section 4 asks a similar question of a value: do its parts recombine with other parts often enough to be worth describing separately. A description-length criterion would be the principled replacement for `min_support`. That link is mine, not the paper's.
- van Zaanen (2000), Mintz (2003) and Solan et al. (2005) are in the first write-up.

**Data with template ground truth, beyond language.**

- Zhu, He, He, Liu and Lyu (2023), "Loghub: A Large Collection of System Log Datasets for AI-driven Log Analytics", ISSRE 2023. https://arxiv.org/abs/2008.06448 Data: https://github.com/logpai/loghub Logs from 19 systems. Annotated templates exist for 2,000 sampled lines per system. A log line is a constant frame with parameters by construction, so "did it find the rule and the variables" has an exact answer. I have not checked the licences of the individual logs.
- Rastogi, Zang, Sunkara, Gupta and Khaitan (2020), "Towards Scalable Multi-domain Conversational Agents: The Schema-Guided Dialogue Dataset", AAAI 34(05), 8689-8696. https://arxiv.org/abs/1909.05855 The data of section 8.

## 10. What KATO already does here, and what is missing

**Found this round.**

| Capability | Used for |
|---|---|
| Predict on a sequence, then learn it | whole sequences at node_0 without any hold-out |
| `frequency` of a predicted pattern | the number of earlier places; the module's own log is no longer needed |
| `missing` of one VAR against `extras` of several tokens | binding a value of any length (node_1b, node_1t) |
| A symbol that starts every value of a VAR | node_2b serving as "node_0 for the values" of every VAR at once |
| `evidence` (matches / pattern length) on every prediction | not used yet; see 2 below |

**Missing or awkward.**

1. **A name inside a pattern is opaque to matching.** Round 1 met it as `rejoin`. Here it costs a whole node: node_1t is every rule again, spelled out. Matching through names would remove it.
2. **The recall gate is symmetric.** `recall_threshold` gates on similarity, 2 · matches / (pattern length + observed length). A rule whose every constant is present still fails the gate when its value is long. A gate on `evidence` would suit a rule reading a sequence.
3. **One alignment per prediction.** When a constant of a rule also occurs inside a value, KATO returns one of the possible alignments, and the rule may not fit under that one.
4. **At most 10,000 predictions per request**, as before.

## 11. Where this round is weak

1. **Real text.** One annotated slot in five, at best. Section 8.
2. **The inside reading is a first cut.** It folds every partly alike value, which is the fold that collapsed at node_0. It has no rules-first step of its own. Inner rules with no constant are told apart only by the VAR they belong to.
3. **`fold='nearest'` fragments.** Rules of every degree of generality coexist, and "most constants wins" is a rule of thumb.
4. **Arrival order.** Which rules exist and which ids they carry depends on the order of the text. The same events in the same order give the same result (the report is identical under two hash seeds).
5. **Not run through KATO.** Round 1's report was checked through a running service. This round's was not.
6. **node_1t and `rule_of`.** A duplicate of node_1b, and a link kept by the module. Both are derivable from KATO.
7. **Whole sequences only read whole.** A rule must fit the entire sentence. Rules for parts of a sentence, with node_2a over their names, are your original hierarchy and are not built for whole sequences.
8. **`min_support` is 1 throughout.**

## 12. For you to decide

1. **Point 5.** Did you mean K (a combination of values) or S (a value's own tokens)?
2. **The repository.** Settled on 24 Nov: `sevakavakians/HPCRD_for_KATO` is public and holds both branches, and both write-ups are in `docs/` as written, at your say.
3. **What comes next.** My order:
   1. Make the inside reading the same procedure as the outside one (nearest, rules first), since it is what moved the number.
   2. Rules for parts of a sequence, so that local comparison comes back without rolling windows.
   3. A second data set whose ground truth is templates. Loghub's annotated samples, after a licence check.
   4. This round's report through a KATO service.
4. **The data rule.** I followed the lab's proposed rule here (fetch at run time, pin by hash, numbers only in the results file). It is still yours to decide. This write-up quotes a handful of short utterances from the set, with its name and licence. Say if the rule should exclude that too.

**Answered on 24 Nov.** Points 1 and 3: decide by prior art, and use what others have shown to work. `round-3-published-methods-2026-11-24.md` does that.

## 13. Checks and how to rerun

**Checks (24 Nov 2026).**

1. `examples/report.txt` (round 1) is unchanged: 906 lines, sha1 `818a4c2a85c59ff50f9a022777f1d759374371b5`.
2. `examples/report_sequences.txt` (this round): 554 lines, sha1 `7c8150fb9ad947329d60a91b6b6d8a2ad06cf8de`, the same under `PYTHONHASHSEED` 0 and 7.
3. 57 tests pass, in-process. On 19 whole-sequence runs: the module keeps no record; node_0 holds one pattern per distinct sentence with the right frequency; every rule instance gives back its tokens, whichever way it was read; every inner rule gives back its value; every name resolves; every VAR of a rule has a value.
4. The probe's numbers are in `experiments/results/sgd_probe_2026-11-24.json`, with the pins.

**Not shown.** Nothing through KATO's API. No timing beyond the probe's seconds. No corpus beyond three files. Events of one symbol only.

```sh
export KATO_REPO=/path/to/kato
.venv/bin/python -m pytest -q
./run.sh examples/sequences.py                      # examples 7 to 12
./run.sh examples/sequences.py --digest
./run.sh experiments/sgd_probe.py --data ../sgd-data --fetch --save out.json
./run.sh examples/explore.py "play yesterday . play imagine ." span=sequence markers=. slots=gap values=sequence
```
