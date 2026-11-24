# KATO segments, chunks and rules: worked examples

> **Note added when this write-up entered the repository (24 Nov 2026).** The text below is as written, before
> the code had a home. The scripts it names are now here: `examples.py` is `examples/worked_examples.py`,
> `explore2.py` is `examples/explore.py`, `check_examples.py` is `tests/test_invariants.py`,
> `check_alignment.py` is `scripts/check_alignment.py`, and the other modules are in `hpcrd/`.
> `claude/...` paths are documents of the KATO Lab project.

Written 24 Nov 2026. Workstream: CORE, as an experiment. Nothing in the KATO repo was changed.

**What this is.** Sevak's brief of 24 Nov 2026 opens a new experiment: find or create the KATO capabilities that let it (1) segment patterns automatically, (2) chunk repeated patterns and (3) create rules from patterns, by reading the prediction ensembles of a rolling-window node. The brief gives one sketch and asks for comprehensive, complete examples to build on. This document is those examples. Working name: **chunks and rules**.

**Status.** Six worked examples, a reference sketch of the module, two check scripts. Every block of output below is printed by `examples.py`. No corpus was run, nothing was measured at scale, and no repository holds the code.

**What ran where.** KATO `main` at `f32bac0` (v7.1.0 plus 34 commits). The examples run in-process on KATO's own matcher, `Pattern`, `Prediction` and scoring code, and again with every node inside a running KATO service, every call over REST. The two reports are the same 906 lines, byte for byte (sha1 `818a4c2a85c59ff50f9a022777f1d759374371b5`). Section 14 has the details.

## 0. In one screen

**It works on small text.** From "the cat sat on the mat ." and "the dog sat on the mat ." the module learns the chunk `sat on the mat .` in node_1a, the rule `[the] [VAR|1] [PTRN|76a6fb]` in node_1b and the values `cat`, `dog` in node_2b. A third sentence with `bird` is recognised as the same rule, and node_1b's own prediction does the binding: `missing [[], ["VAR|1"], []]`, `extras [[], ["bird"], []]`.

**KATO already supplies most of it.**

1. node_0 is `stm_mode=ROLLING` with `max_pattern_length=7`. No new code.
2. With one symbol per event, a prediction's `missing` and `extras` carry the full positional alignment. Rebuilt exactly on 502,184 of 502,184 predictions (in-process).
3. A chunk's name is the hash of its content, so "is this chunk known" and "is this value known for this VAR" are lookups by name, and frequency counts reuse.
4. node_2b answers "which values does VAR|2 take" and "which VARs take cat" as ordinary predictions on a one-symbol observation.
5. `future_potentials` at node_2b gives the value of one slot given another: `purrs` 0.991 after `[VAR|4] [cat] [VAR|5]`.
6. node_0's `recall_threshold` is the dial for how general a rule gets.

**The description needs seven things added or changed.** Each is shown with output below, and collected in section 11.

1. **Echoes.** Each window shares up to six tokens with the windows just learned. They lead every ensemble and have to be held out.
2. **Edges.** A substitution at the window's edge is not in `missing`. KATO puts the pattern's side in `past` or `future`.
3. **VAR identity.** A fresh integer per anomaly never repeats, so node_1b would never see a rule twice. Three ways to give a slot a stable id are run side by side.
4. **One window at a time models every structure at every shift.** 9 chunks, 5 rules and 5 VARs where the same text stitched along the stream gives 1, 1 and 1.
5. **"Everything else is noise" throws away new material.** A city name of two words is dropped and the rule that remains is `[show flights from] [to denver .]`.
6. **One VAR per aligned position cannot hold a value of another length,** and it reads any two gaps of equal length as position-for-position variables.
7. **KATO's default `recall_threshold` of 0.1 over-generalises here.** On one text: 5 rules with 16 VARs at 0.1, 3 rules with 5 VARs at 0.5.

**Sevak's answers of 24 Nov 2026, applied here.**

- node_2a observes the *names* of node_1b's patterns, in order, and learns sequences of rules.
- What gives a VAR its id: "Let's add all 3 to the experiments so we can identify which works best. It may also be a combination." All three are settings of the sketch (Example 5).
- Rule span: both, compared. One window at a time first, then stitched along the stream (Examples 1 and 2).
- "Variables will form their own patterns together" means all four: adjacent VARs as one unit (Example 3), values that go together (Example 4), VARs sharing values and recurring VAR sequences (Example 5).

**Open on Sevak's side.**

1. Where the code lives: a new repository, or a folder of the Language Lab's.
2. The first real data (section 12 proposes one set with annotated slots and one for scale).
3. Whether the application may say where a stretch ends in the first experiments. Stitched mode needs something to close a stretch, and the brief gives nothing for it.

## 1. Setup

### 1.1 The nodes

```
node_0   rolling window of tokens, one token per event      (KATO: stm_mode=ROLLING, max_pattern_length=7)
   |  prediction ensemble, one per token
module   reads each prediction's matches / missing / extras
   |-> node_1a   each contiguous match of two or more tokens         -> PTRN|<chunk>
   |-> node_1b   the abstracted sequence: chunk names, single
   |             tokens, VAR|n                                       -> PTRN|<rule>
   |       '-> node_2a   observes PTRN|<rule> names in order
   '-> node_2b   each VAR|n with a value; the values of one rule
                 instance together; VARs that stand side by side
```

KATO's prefix for a pattern name is `PTRN|`. The brief writes `PTN|`; the examples use KATO's.

### 1.2 The settings

Every choice the brief leaves open is a named setting of the sketch, so the experiments can run the alternatives side by side.

| Setting | Values | What it decides | In the examples |
|---|---|---|---|
| `window` | integer | node_0's rolling window | 7 |
| `recall_threshold` | KATO's own, on node_0 | how alike a learned window must be before it is read | 0.5 (KATO's default is 0.1; Example 4 shows why) |
| `span` | `window`, `stream` | one rule per ensemble, or stitched along the stream | Example 1 `window`, the rest `stream` |
| `markers` | tokens | where a stretch ends when stitched | `.` |
| `naming` | `rule`, `neighbours`, `values` | what gives a slot its VAR id | `rule`; Example 5 compares |
| `slots` | `position`, `gap` | one VAR per aligned position, or one per gap | `position`; Example 3 compares |
| `unexplained` | `drop`, `break` | a token no learned pattern accounts for is removed as noise, or ends the part | `drop` to Example 3(b), `break` after |
| `mixed` | `var`, `const` | a position some earlier places match and others substitute | `var` |
| `min_support` | integer | earlier places a substitution needs before it makes a variable | 1 |
| `edge_vars` | off, on | read an extra that lines up with `past` or `future` as a variable too | off |
| `rejoin` | on, off | join a chunk again when the noise inside it has been dropped | on |
| `node2a_window` | integer | node_2a's own rolling window over rule names | 2 (a placeholder: the brief gives none) |

### 1.3 Reading the output

```
labels    the/C  dog/V  sat/C ...      C constant, V variable, N noise (with the reason)
node_1a   PTRN|76a6fb = [sat on the mat .]   frequency 1
node_1b   PTRN|16f905 = [the] [VAR|1] [PTRN|76a6fb(sat on the mat .)]   frequency 1
node_2b   [VAR|1] [dog]   (new value; earlier: cat x1)
```

Names are cut to six hex digits. A chunk name is followed by its tokens in brackets for reading only: the stored symbol is the name. `earlier: cat x1` means `cat` stood at the aligned position in one earlier place of the stream.

How one learned pattern accounts for each observed position:

| Mark | Meaning | Where KATO says it |
|---|---|---|
| `=` | matched | `extras[i] == []` |
| `~x` | substituted: the pattern holds `x` at the aligned position | `extras[i]` against `missing[j]`, same count on both sides of the gap |
| `e:x` | edge: lines up with `x` before the first or after the last match | `extras[i]` against `past` or `future` |
| `+` | inserted: the pattern has the two neighbours side by side | `extras[i]`, nothing in `missing` |
| `u` | unequal gap: n extras against a different number of missing | both |
| `.` | out of the pattern's view | beyond its first or last event |

## 2. How the module reads one ensemble

Five steps. Example 1 shows each on real output.

**Step 1: hold out the echoes.** A window learned at step *u* covers the seven tokens that end at *u*. It shares no token with the window in the STM only when *u* <= *t* - 7. Later windows are the same tokens shifted, and they always match. The module holds them out. A pattern learned both recently and earlier stays in, with the earlier learns as its frequency. KATO returns a pattern's name and frequency with a prediction, not where it was learned, so the module keeps its own record of the step at which node_0 learned each window. That record is the one piece of state the module holds.

**Step 2: read each prediction position by position.** With one symbol per event, `extras[i] == []` says STM position *i* matched, `missing[j] == []` says position *j* of `present` matched, and the alignment rises on both sides, so the k-th of one pairs with the k-th of the other. What lies between two matched pairs is a gap, and the gap's two sides give the marks of section 1.3.

**Step 3: fold the readings into one label per position.** Evidence is counted in earlier places of the stream, each place once, however many shifted windows node_0 holds over it.

- **Variable** when at least `min_support` earlier places hold another symbol at the aligned position.
- **Constant** when not variable and at least one earlier place holds the same token, aligned.
- **Noise** otherwise, with its reason: `inserted`, `unequal` or `unexplained`.

A position that some places match and others substitute is a variable (`mixed=var`). That gives the most general rule the aligned patterns allow.

**Step 4: cut the constants into chunks.** A chunk is a run of constants that was seen whole before: one contiguous match covers it. For a run longer than the window, one contiguous match must cover every window-length piece of it. The longest such run is taken first, then the one seen in more places, then the leftmost, and what is left on either side is cut the same way. A chunk of two or more tokens is learned in node_1a and stands in the rule by name. A single token stands as itself, because KATO does not learn a pattern of fewer than two symbols.

**Step 5: build the rule and name its slots.** The rule is the sequence of chunk names, single tokens and VAR ids, with noise removed. node_1b learns it when it has two or more symbols and at least one constant. node_2b then learns three shapes of pattern:

| Shape | Example | Its frequency counts |
|---|---|---|
| a VAR with one value | `[VAR|2] [cat]` | how often the value stood in the slot |
| the values of one rule instance together | `[VAR|2] [cat] [VAR|3] [rug]` | how often the values came together |
| VARs side by side | `[VAR|6] [VAR|7] [VAR|8]` | how often the run occurred |

A value or a set of joint values that a learned pattern holds at the slot, and that node_2b does not have yet, is added once. Counts therefore start when a rule comes into being, plus one for each earlier value the ensemble shows.

## 3. Example 1: one slot, one window at a time

The brief to the letter: `span=window`, `slots=position`, `unexplained=drop`, `naming=rule`.

```
text: the cat sat on the mat . the dog sat on the mat . the bird sat on the mat .
```

**t=6.** The first full window. The ensemble is empty, and node_0 learns the window as `PTRN|a3719f`.

**t=13.** node_0 returns seven predictions. Six are echoes.

```
t=13  STM  the dog sat on the mat .
  a3719f  the cat sat on the mat .   frequency 1  similarity 0.857  learned at t=6   READ
  1eaaea  cat sat on the mat . the   frequency 1  similarity 0.714  learned at t=7   echo
  7c6bcd  sat on the mat . the dog   frequency 1  similarity 0.714  learned at t=8   echo
  fbf9a2  on the mat . the dog sat   frequency 1  similarity 0.571  learned at t=9   echo
  4f4db4  the mat . the dog sat on   frequency 1  similarity 0.571  learned at t=10  echo
  a09df5  mat . the dog sat on the   frequency 1  similarity 0.714  learned at t=11  echo
  92502d  . the dog sat on the mat   frequency 1  similarity 0.857  learned at t=12  echo
```

The one prediction that is read, as KATO returns it:

```
matches  ["the", "sat", "on", "the", "mat", "."]
missing  [[], ["cat"], [], [], [], [], []]
extras   [[], ["dog"], [], [], [], [], []]
past     []
present  [["the"], ["cat"], ["sat"], ["on"], ["the"], ["mat"], ["."]]
future   []
```

What the module does with it:

```
  a3719f  the cat sat on the mat .   @0  | =  ~cat  =  =  =  =  =
labels    the/C  dog/V  sat/C  on/C  the/C  mat/C  ./C
node_1a   PTRN|76a6fb = [sat on the mat .]   frequency 1   (contiguous match, seen whole in 1 earlier place)
probe     [the] [dog] [PTRN|76a6fb(sat on the mat .)]   -> no learned rule fits: new VAR ids
node_1b   PTRN|16f905 = [the] [VAR|1] [PTRN|76a6fb(sat on the mat .)]   frequency 1
node_2b   [VAR|1] [dog]   (new value; earlier: cat x1)
node_2b   [VAR|1] [cat]   (value a learned pattern has there)
```

`the` at position 0 is a contiguous match of one token, so it stays a token.

**t=14.** The same slot, now at the window's edge. `dog` is an extra and nothing stands against it in `missing`: the pattern's `cat` is in `past`.

```
t=14  STM  dog sat on the mat . the
  1eaaea  cat sat on the mat . the
    matches  ["sat", "on", "the", "mat", ".", "the"]
    missing  [[], [], [], [], [], []]
    extras   [["dog"], [], [], [], [], [], []]
    past     [["cat"]]
labels    dog/N:unexplained  sat/C  on/C  the/C  mat/C  ./C  the/C
node_1a   PTRN|11a6bb = [sat on the mat . the]   frequency 1
node_1b   nothing to learn: one symbol is not a pattern
```

**t=20.** The rule is recognised. The module shows node_1b the sequence with the observed value standing in the slot (the probe), and node_1b's own prediction binds value to variable:

```
t=20  STM  the bird sat on the mat .
probe     [the] [bird] [PTRN|76a6fb(sat on the mat .)]
  16f905  frequency 1  similarity 0.667
    matches  ["the", "PTRN|76a6fbd3fd4840cef7844f523750e20d3e996af3"]
    missing  [[], ["VAR|1"], []]
    extras   [[], ["bird"], []]
    present  [["the"], ["VAR|1"], ["PTRN|76a6fbd3fd4840cef7844f523750e20d3e996af3"]]
node_1b   PTRN|16f905 = [the] [VAR|1] [PTRN|76a6fb(sat on the mat .)]   frequency 2
node_2b   [VAR|1] [bird]   (new value; earlier: cat x1, dog x1)
```

A learned rule is taken as recognised when it has the same constants in the same places and VARs where the probe has values. No id is minted.

**Every step that taught a node above node_0:**

```
t=13  the dog sat on the mat .     [the] [VAR|1] [PTRN|76a6fb(sat on the mat .)]
t=14  dog sat on the mat . the     chunk only: [sat on the mat . the]
t=15  sat on the mat . the bird    chunk only: [sat on the mat . the]
t=16  on the mat . the bird sat    [PTRN|86e365(on the mat . the)] [VAR|2] [sat]
t=17  the mat . the bird sat on    [PTRN|19d06e(the mat . the)] [VAR|3] [PTRN|9b9746(sat on)]
t=18  mat . the bird sat on the    [PTRN|feedd8(mat . the)] [VAR|4] [PTRN|4e0120(sat on the)]
t=19  . the bird sat on the mat    [PTRN|490ed6(. the)] [VAR|5] [PTRN|c2fcdf(sat on the mat)]
t=20  the bird sat on the mat .    [the] [VAR|1] [PTRN|76a6fb(sat on the mat .)]   (recognised)
```

**What the nodes hold at the end:** node_0 15 windows, node_1a 9 chunks, node_1b 5 rules, 5 VARs, node_2a 5 pairs of rule names, node_2b 13 patterns. The text has one slot.

**What Example 1 shows.**

1. The base case works as the brief describes it, and KATO's `missing` and `extras` are the A of the sketch.
2. One window at a time, the same slot is modelled once per shift: VAR|1 to VAR|5 are one slot seen at five offsets, with five rules and nine chunks around it.
3. With `edge_vars` on, the two edge windows make rules too (`[VAR|2] [PTRN|11a6bb]` and `[PTRN|11a6bb] [VAR|3]`): 7 rules and 7 VARs.

## 4. Example 2: the same text stitched along the stream

`span=stream`: the module keeps stream positions, merges what the seven windows over each token say about it, and models a stretch when the window has moved past its last token. A stretch ends at a marker, here `.`.

```
stretch 0..6    the cat sat on the mat .
  labels    the/N:unexplained  cat/N:unexplained  ...  ./N:unexplained
  nothing to learn above node_0
stretch 7..13   the dog sat on the mat .
  labels    the/C  dog/V  sat/C  on/C  the/C  mat/C  ./C
  node_1a   PTRN|76a6fb = [sat on the mat .]   frequency 1
  node_1b   PTRN|16f905 = [the] [VAR|1] [PTRN|76a6fb(sat on the mat .)]   frequency 1
  node_2b   [VAR|1] [dog]   (new value; earlier: cat x1)
  node_2b   [VAR|1] [cat]   (value a learned pattern has there)
stretch 14..20  the bird sat on the mat .
  probe     [the] [bird] [PTRN|76a6fb(sat on the mat .)]   -> RECOGNISED
  node_1b   PTRN|16f905 = [the] [VAR|1] [PTRN|76a6fb(sat on the mat .)]   frequency 2
  node_2b   [VAR|1] [bird]   (new value; earlier: cat x1, dog x1)
```

The first sentence is the "I don't know" case one level up: no learned pattern lines up with any of it, so nothing above node_0 learns.

| Same text, same settings otherwise | per window | stitched |
|---|---|---|
| node_0 patterns | 15 | 15 |
| node_1a chunks | 9 | 1 |
| node_1b rules | 5 | 1 |
| rules seen again | 1 | 1 |
| VARs | 5 | 1 |
| node_2a patterns | 5 | 1 |
| node_2b patterns | 13 | 3 |

**A chunk longer than the window.** A constant stretch of eight tokens, window of seven:

```
text: the old cat sat on the mat by the door . the old dog sat on the mat by the door .
      the old bird sat on the mat by the door .

stretch 11..21  the old dog sat on the mat by the door .
  node_1a   PTRN|9c5d3c = [the old]   frequency 1
  node_1a   PTRN|1c5c3e = [sat on the mat by the door .]   frequency 1
  node_1b   PTRN|d81498 = [PTRN|9c5d3c(the old)] [VAR|1] [PTRN|1c5c3e(sat on the mat by the door .)]   frequency 1
stretch 22..32  the old bird sat on the mat by the door .
  node_1b   PTRN|d81498 = ...   frequency 2      (recognised)
```

Per window this text gives 14 chunks, 7 rules and 7 VARs, the longest chunk 7 tokens. Stitched: 2 chunks, 1 rule, 1 VAR, the longest chunk 8 tokens.

KATO already signals a repeat longer than the window: node_0 had learned the windows inside it before, so learning them again raised their frequency.

```
PTRN|46e7a8  f=3  sat on the mat by the door
PTRN|2bbc25  f=3  on the mat by the door .
```

**What Example 2 shows.**

1. Stitched, one structure is one rule, whatever the window offset was.
2. A stretch is modelled six tokens after its last token arrives, and its labels never change afterwards. Evidence comes only from text earlier in the stream (checked: section 14).
3. Stitching needs something to close a stretch. Here the application says so with a marker. The brief has no rule for it, and none is automatic yet (section 12, choice 3).
4. node_2a learns `[PTRN|16f905] [PTRN|16f905]`: the same rule twice in a row. Per window it learns five pairs of rules that are one token's shift apart.

## 5. Example 3: the sketch in the brief, then noise and values of other lengths

### 5.1 The sketch, run

The brief's sketch is `[N] [A] [match 1] [A] [A] [A] [match 2] [N] [A] [N] [N]`, giving `[VAR|1] [PTN|h1] [VAR|2] [VAR|3] [VAR|4] [PTN|h2] [VAR|5]`. Four sentences, stitched, to the letter otherwise:

```
text: please book a table for two quiet adults at seven tonight .
      kindly book a table for six hungry diners at seven today .
      please book a table for four tired guests at uh seven tonight .
      kindly book a table for two quiet adults at seven today .

stretch 12..23  kindly book a table for six hungry diners at seven today .
  labels    kindly/N:unexplained  book/C  a/C  table/C  for/C  six/V  hungry/V  diners/V  at/C  seven/C  today/V  ./C
  node_1a   PTRN|6454f3 = [book a table for]   frequency 1
  node_1a   PTRN|8a0c5a = [at seven]   frequency 1
  node_1b   PTRN|ad48e1 = [PTRN|6454f3] [VAR|1] [VAR|2] [VAR|3] [PTRN|8a0c5a] [VAR|4] [.]   frequency 1
  node_2b   [VAR|1] [six] [VAR|2] [hungry] [VAR|3] [diners] [VAR|4] [today]   (values together)
  node_2b   [VAR|1] [VAR|2] [VAR|3]   (VARs side by side)

stretch 24..36  please book a table for four tired guests at uh seven tonight .
  labels    please/V  book/C  a/C  table/C  for/C  four/V  tired/V  guests/V  at/C  uh/N:inserted  seven/C  tonight/V  ./C
  node_1a   PTRN|6454f3 = [book a table for]   frequency 2
  node_1a   PTRN|8a0c5a = [at seven]   frequency 2   (joined again after the noise between its parts was dropped)
  node_1b   PTRN|1c9f9a = [VAR|5] [PTRN|6454f3] [VAR|6] [VAR|7] [VAR|8] [PTRN|8a0c5a] [VAR|9] [.]   frequency 1
  node_2b   [VAR|5] [please]   (new value; earlier: kindly x1)
  node_2b   [VAR|6] [four]   (new value; earlier: six x1, two x1)
  ...
  node_2b   [VAR|6] [VAR|7] [VAR|8]   (VARs side by side)

stretch 37..48  kindly book a table for two quiet adults at seven today .
  probe     [kindly] [PTRN|6454f3] [two] [quiet] [adults] [PTRN|8a0c5a] [today] [.]   -> RECOGNISED
  node_1b   PTRN|1c9f9a = ...   frequency 2
```

The third sentence gives the sketch's shape: VAR, chunk, VAR VAR VAR, chunk, VAR. `uh` falls inside `at seven`, is dropped as an insertion, and the chunk is joined again because node_1a already holds `at seven` under that name.

Two cells of the sketch cannot come out of `missing` and `extras` as drawn:

- **An A outside the outermost matches** (the sketch's first and last A). KATO has the pattern's side in `past` or `future`, never in `missing`. It is a variable only with `edge_vars` on, or when another window has it between two matches, as `please` has here through `. kindly book`.
- **An N beside an A in one gap** (the sketch's `[match 2] [N] [A]`). Two extras against one missing is an unequal gap. Position by position, nothing says which of the two is the noise.

Under `naming=rule` the rule's slots were renamed when the rule gained its leading slot: VAR|1 to VAR|4 became VAR|6 to VAR|9, and the first rule is left behind with frequency 1.

### 5.2 Noise, and a value of another length

```
text: show flights from boston to denver .        show flights from dallas to denver .
      show me flights from boston to denver .     show flights from new york to denver .
      show flights from los angeles to denver .
```

The second sentence gives `PTRN|27641b = [PTRN|ac5190(show flights from)] [VAR|1] [PTRN|c97f0b(to denver .)]`. The third has `me` inside the first chunk. It is dropped, the chunk is joined again, and the rule is recognised. Then the three readings part ways:

**(b) To the letter** (`slots=position`, `unexplained=drop`):

```
stretch 22..29  show flights from new york to denver .
  labels    show/C  flights/C  from/C  new/N:unequal  york/N:unequal  to/C  denver/C  ./C
  node_1b   PTRN|35ed08 = [PTRN|ac5190(show flights from)] [PTRN|c97f0b(to denver .)]   frequency 1
stretch 30..37  show flights from los angeles to denver .
  labels    show/C  flights/C  from/C  los/V  angeles/V  to/C  denver/C  ./C
  node_1b   PTRN|4401ca = [PTRN|ac5190] [VAR|2] [VAR|3] [PTRN|c97f0b]   frequency 1
  node_2b   [VAR|2] [los] [VAR|3] [angeles]   (values together)
  node_2b   [VAR|2] [new] [VAR|3] [york]   (values together in a learned pattern)
  node_2b   [VAR|2] [VAR|3]   (VARs side by side)
```

`new york` stands against the one-word `boston` and `dallas`, so it is noise, and the rule that is learned has no city in it. `los angeles` stands against `new york`, two against two, and becomes two VARs side by side in a third rule.

**(c) Only an insertion is removed** (`unexplained=break`). A token nothing accounts for ends the part, and what stands on either side is modelled on its own. `show flights from` and `to denver .` are each one chunk, one symbol is not a pattern, and no rule is learned for the `new york` sentence.

**(d) One VAR per gap** (`slots=gap`). A slot is the whole gap between two constants, its value may be any length, and a value of two or more tokens is a chunk in node_1a:

```
stretch 22..29  show flights from new york to denver .
  labels    show/C  flights/C  from/C  new/V  york/V  to/C  denver/C  ./C
  node_1a   PTRN|86a351 = [new york]   frequency 1   (the value of a slot)
  probe     [PTRN|ac5190] [PTRN|86a351(new york)] [PTRN|c97f0b]   -> RECOGNISED
  node_1b   PTRN|27641b = [PTRN|ac5190(show flights from)] [VAR|1] [PTRN|c97f0b(to denver .)]   frequency 3
  node_2b   [VAR|1] [PTRN|86a351(new york)]   (new value; earlier: boston x2, dallas x1)
```

| | (b) letter | (c) break | (d) gap |
|---|---|---|---|
| node_1a chunks | 2 | 2 | 4 |
| node_1b rules | 3 | 2 | 1 |
| frequency of the flights rule | 2 | 2 | 4 |
| VARs | 3 | 3 | 1 |
| node_2b patterns | 9 | 9 | 4 |

**What Example 3 shows.**

1. Noise inside a chunk is handled as the brief wants, and the rule is still recognised.
2. "Removed as noise" cannot tell noise from news. `new york` was new, and to the letter it is thrown away.
3. Adjacent VARs as one unit comes out two ways. Position by position, `los` and `angeles` are two VARs whose joint values node_2b records (`new`+`york`, `los`+`angeles`: two combinations seen of four possible). Gap by gap, they are one slot whose value is a chunk.
4. Gap by gap, all five sentences are one rule with four values of one VAR.

## 6. Example 4: two slots, how general a rule gets, values that go together

From here on `unexplained=break`.

```
text: the cat sat on the mat . the dog sat on the mat . the cat sat on the rug . the dog sat on the rug .
      when the cat is happy it purrs . when the dog is happy it barks .
      when the cat is happy it purrs . when the dog is happy it barks .
```

The rule grows more general as evidence arrives:

```
the dog sat on the mat .    PTRN|16f905 = [the] [VAR|1] [PTRN|76a6fb(sat on the mat .)]                f=1
the cat sat on the rug .    PTRN|15eab5 = [the] [VAR|2] [PTRN|4e0120(sat on the)] [VAR|3] [.]          f=1
the dog sat on the rug .    PTRN|15eab5   recognised                                                   f=2
when the cat is happy ...   chunk [the cat] only
when the dog is happy ...   PTRN|2c85fc = [PTRN|3dc3ab(when the)] [VAR|4] [PTRN|f73d8d(is happy it)] [VAR|5] [.]   f=1
                            then recognised twice                                                      f=3
```

In the third sentence `cat` is matched by the first sentence and substituted by the second, so it is a variable (`mixed=var`), and the chunk `sat on the mat .` gives way to `sat on the`.

### 6.1 The dial

Same text, one setting changed. A window of seven and a threshold of 0.5 mean a learned window is read only when it shares at least four of its seven tokens with the STM, in order.

```
recall_threshold=0.1 (KATO default):  5 rules, 16 VARs
    f=1  [the] [VAR|1] [PTRN|76a6fb(sat on the mat .)]
    f=1  [the] [VAR|2] [PTRN|4e0120(sat on the)] [VAR|3] [.]
    f=1  [the] [VAR|4] [PTRN|4e0120(sat on the)] [VAR|5] [VAR|6]
    f=1  [VAR|7] [PTRN|4894cb(the cat)] [VAR|8] [VAR|9] [VAR|10] [VAR|11] [.]
    f=3  [PTRN|3dc3ab(when the)] [VAR|12] [VAR|13] [VAR|14] [VAR|15] [VAR|16] [.]
recall_threshold=0.3:  4 rules, 12 VARs
recall_threshold=0.5:  3 rules, 5 VARs       (the three rules above)
recall_threshold=0.7:  3 rules, 5 VARs       (the same three)
recall_threshold=0.9:  0 rules, 0 VARs
0.5, mixed=const:  4 rules, 4 VARs
    f=1  [PTRN|a4fb47(the cat sat on the)] [VAR|2] [.]
    f=1  [PTRN|171bc5(the dog sat on the)] [PTRN|6a9d11(rug .)]
0.5, min_support=2:  3 rules, 5 VARs, none seen again
```

At 0.1, "when the cat is happy it purrs ." is read against "the cat sat on the mat .": they share `the cat` and `.`, the gap between is four tokens on each side, and position by position that is `is~sat`, `happy~on`, `it~the`, `purrs~mat`. Four VARs, and by the brief's rule they are exactly "positional anomalies". At 0.9 only an exact repeat is read, so nothing varies. With `mixed=const` a token that matched anywhere stays constant and no rule is ever seen again.

### 6.2 Values that go together

The joint values node_2b holds for each rule with two slots:

```
[the] [VAR|2] [PTRN|4e0120(sat on the)] [VAR|3] [.]
    cat + mat x1    cat + rug x1    dog + mat x1    dog + rug x1
    4 of 4 possible combinations seen (2 values of VAR|2 x 2 values of VAR|3)
[PTRN|3dc3ab(when the)] [VAR|4] [PTRN|f73d8d(is happy it)] [VAR|5] [.]
    cat + purrs x2    dog + barks x2
    2 of 4 possible combinations seen (2 values of VAR|4 x 2 values of VAR|5)
```

Combinations seen over combinations possible is a count an auditor can check. The first rule's slots vary freely. The second rule's slots move together.

KATO answers the question itself. Observe the first VAR, its value and the second VAR at node_2b, and read what follows:

```
observe [VAR|2] [cat] [VAR|3] at node_2b: 11 predictions, 2 match all three symbols
    0c8681  frequency 1  similarity 0.857  future [["mat"]]
    8e7244  frequency 1  similarity 0.857  future [["rug"]]
    future_potentials: rug 0.5, mat 0.499
observe [VAR|4] [cat] [VAR|5] at node_2b: 10 predictions, 1 match all three symbols
    b43951  frequency 2  similarity 0.857  future [["purrs"]]
    future_potentials: purrs 0.991, barks 0.007
```

**What Example 4 shows.**

1. `recall_threshold` on node_0 is the generality dial, and KATO's default is too low for this use.
2. An equal-length gap is not evidence that its positions correspond. It takes a close analog (the threshold) or a gap-level slot to avoid `is~sat`.
3. Values that go together need no new machinery: one more pattern per rule instance in node_2b, read back with `future_potentials`.
4. A rule that generalises is a new rule. `PTRN|16f905` and its VAR|1 are left behind with frequency 1.

## 7. Example 5: three ways to give a slot its VAR id

```
text: the cat sat on the mat . the dog sat on the mat .
      we saw the cat near the old barn . we saw the dog near the old barn .
      the cat sat by a warm fire . the dog sat by a warm fire .
      the bird sat on the mat . we saw the bird near the old barn . the bird sat by a warm fire .
```

The rules are the same four under every naming. Only the ids differ:

```
                                      naming=rule   naming=neighbours   naming=values
[the] [VAR] [sat on the mat .]          VAR|1          VAR|1              VAR|1
[we saw the] [VAR] [near the old barn .]  VAR|2        VAR|2              VAR|1
[the] [VAR] [sat]                       VAR|3          VAR|1              VAR|1
[the] [VAR] [sat by a warm fire .]      VAR|4          VAR|1              VAR|1
VARs                                    4              2                  1
node_2b patterns                        11             6                  3
```

- **`rule`: node_1b recognises it.** The probe of Example 1. An id belongs to one slot of one rule. Four slots, four ids, each holding `cat`, `dog` and (three of them) `bird`.
- **`neighbours`: the tokens on either side name it.** VAR|1 is the slot between `the` and `sat`, in three rules. VAR|2 is the slot between `the` and `near`.
- **`values`: its values name it.** The module asks node_2b which VARs already hold the slot's values, and the most shared values wins. One VAR, `bird x3, cat x2, dog x3`.

The fifth sentence, "the cat sat by a warm fire .", is new after `sat`. Its known beginning becomes the rule `[the] [VAR] [sat]` on its own: the frame around the slot.

**VARs sharing values.** Under `naming=rule` the sharing is still there to be found, by asking node_2b:

```
observe [cat]  at node_2b -> VAR|1 (x1), VAR|2 (x1), VAR|3 (x1), VAR|4 (x1)
    one of them, as KATO returns it: past [["VAR|3"]] present [["cat"]] future [] similarity 0.667
observe [bird] at node_2b -> VAR|1 (x1), VAR|2 (x1), VAR|4 (x1)
```

**Recurring VAR sequences.** Two slots side by side, in two different rules:

```
text: the big dog sat on the mat . the small cat sat on the mat . the big cat sat on the mat .
      we saw the big dog near the old barn . we saw the small cat near the old barn .
      we saw the small dog near the old barn .

naming=rule: 4 VARs
    node_1b f=2  [the] [VAR|1] [VAR|2] [PTRN|76a6fb(sat on the mat .)]
    node_1b f=2  [PTRN|24d6a8(we saw the)] [VAR|3] [VAR|4] [PTRN|14fd2b(near the old barn .)]
    node_2b f=2  [VAR|1] [VAR|2]      node_2b f=2  [VAR|3] [VAR|4]
naming=values: 2 VARs
    node_1b f=2  [the] [VAR|1] [VAR|2] [PTRN|76a6fb(sat on the mat .)]
    node_1b f=2  [PTRN|24d6a8(we saw the)] [VAR|1] [VAR|2] [PTRN|14fd2b(near the old barn .)]
    node_2b f=4  [VAR|1] [VAR|2]
```

A run of VARs can recur across rules only when rules share ids. With `values` the pair `[VAR|1] [VAR|2]` (`big`/`small`, then `cat`/`dog`) is one node_2b pattern with frequency 4, across both rules.

**What Example 5 shows, and a combination to test.**

| | `rule` | `neighbours` | `values` |
|---|---|---|---|
| An id means | one slot of one rule | one frame, in any rule | one class of values |
| State outside KATO | a counter | a counter and a table of frames | a counter |
| Survives the rule generalising | no (Example 4) | only while both neighbours stay constant | yes |
| Can show a recurring VAR sequence | no | where frames repeat | yes |
| Risk | many ids for one thing | one id for unlike things in one frame | one shared word merges two classes; an id's meaning drifts as values join |

A combination worth testing first: keep rule-scoped ids as the permanent names, because they are exact and nothing is ever renamed, and store the other two as patterns *about* VARs. Sharing is already a node_2b query. A class would be one more pattern, such as `[CLS|1] [VAR|1]`, and so would a frame. Rules would keep their names while the classes above them change.

## 8. Example 6: using what was learned

The state at the end of Example 4, then more text.

**(a) A new sentence with a value never seen in the slot.**

```
stretch 60..66  the bird sat on the rug .
  probe     [the] [bird] [PTRN|4e0120(sat on the)] [rug] [.]   -> RECOGNISED
  node_1b   PTRN|15eab5 = [the] [VAR|2] [PTRN|4e0120(sat on the)] [VAR|3] [.]   frequency 3
  node_2b   [VAR|2] [bird]   (new value; earlier: cat x2, dog x2)
  node_2b   [VAR|3] [rug]   (known value; earlier: mat x2)
```

**(b) Which values a VAR accepts.** Observe the VAR alone at node_2b. A one-symbol observation returns every pattern that holds it:

```
observe [VAR|2] at node_2b: 8 predictions, 3 of them a VAR with one value
    0af7ce  frequency 2  future [["dog"]]
    2cd579  frequency 1  future [["cat"]]
    f9526c  frequency 1  future [["bird"]]
```

**(c) What a rule allows, against what was seen.**

```
the bird sat on the mat .            never seen: the rule allows it, no observation backs it
the bird sat on the rug .            seen together x1
the cat sat on the mat .             seen together x1
...
when the cat is happy it barks .     never seen: the rule allows it, no observation backs it
when the cat is happy it purrs .     seen together x2
when the dog is happy it barks .     seen together x2
when the dog is happy it purrs .     never seen: the rule allows it, no observation backs it
```

Ten sentences allowed, three never observed. A rule goes beyond what KATO observed, which the README says KATO does not do. Anything built on rules has to say which of its outputs were seen and which are recombined. The joint values in node_2b are what makes that label possible.

**(d) A sentence that shares nothing with what was learned.**

```
node_0, asked about 'birds fly south in winter .' on its own: 0 predictions (recall_threshold 0.5)
stretch 74..79  birds fly south in winter .
  labels    birds/N:unexplained  fly/N:unexplained  south/N:unexplained  in/N:unexplained  winter/N:unexplained  ./C
  nothing to learn above node_0
```

KATO's empty ensemble carries up: no rule is made from nothing.

**(e) Every name unravels.**

```
node_1b  PTRN|2c85fc = [PTRN|3dc3ab] [VAR|4] [PTRN|f73d8d] [VAR|5] [.]
    PTRN|3dc3ab -> node_1a -> when the
    PTRN|f73d8d -> node_1a -> is happy it
    with VAR|4=cat and VAR|5=purrs: when the cat is happy it purrs .
```

Checked for every rule instance in 16 runs (section 14).

## 9. Two side results

### 9.1 How node_2b stores a VAR's values

The brief's example is one list per VAR: `[[VAR|1],[a1],[a2],[a3]]`.

```
learn PTRN|76d530 = [VAR|1] [cat] [dog]
learn PTRN|9fd21a = [VAR|1] [cat] [dog] [bird]        a new value is a second pattern
the same values in another order: PTRN|4328df         and another order is a third
    observe [bird] -> 9fd21a  past [["VAR|1"], ["cat"], ["dog"]]
```

One pattern per VAR and value, as the examples use:

```
observe [VAR|1] -> db6f9e f=3 future [["cat"]]
                   5dce77 f=2 future [["dog"]]
                   9651e3 f=1 future [["bird"]]
    future_potentials: cat 0.448, dog 0.34, bird 0.212
observe [cat]   -> 2cd579 f=1 past [["VAR|2"]]
                   db6f9e f=3 past [["VAR|1"]]
is [VAR|1] [bird] known?  frequency of PTRN|9651e3 = 1   (one lookup by name, no search)
is [VAR|1] [fish] known?  frequency = 0
```

The list depends on the order values arrive in, grows by adding whole new patterns, and counts nothing. The pair counts how often each value stood in the slot and answers both directions. Note that `future_potentials` is KATO's probability from `potential`, not the share of the frequencies (3, 2, 1 would be 0.5, 0.33, 0.17). For counts, read `frequency`.

### 9.2 What the window cannot see

```
text: the cat says meow . the dog says woof . the cat says meow . the dog says woof .

window=7:  node_1a  [the cat says meow .] f=1   [the dog says woof .] f=1      node_1b: 0 rules
window=5:  node_1b  PTRN|0c8fce = [the] [VAR|1] [says] [VAR|2] [.]   f=3
           node_2b  [VAR|1] [dog] [VAR|2] [woof] f=2    [VAR|1] [cat] [VAR|2] [meow] f=2
```

Two instances of a structure closer together than one window cannot be compared: the earlier one is still an echo when the later one is in the STM. With five-token sentences and a window of seven, the module sees only the exact repeats. With a window of five it finds the rule and the joint values.

## 10. What KATO already does here, and what is missing

**Capabilities found (all used above).**

| Capability | Used for |
|---|---|
| `stm_mode=ROLLING` with `max_pattern_length`; observe predicts, then learns | node_0, one call per token |
| `GET /sessions/{id}/cognition-data` returns the predictions computed during the observe | the ensemble for the full window, before the window was learned |
| `missing`, `extras`, `past`, `present`, `future` per event | the positional alignment (one symbol per event) |
| A name is the hash of the content; learning again raises frequency | chunk reuse counts; "is it known" by name |
| A pattern name is an ordinary symbol in another node | chunks inside rules, rules inside node_2a |
| node_1b's own `missing` and `extras` | binding a value to a VAR |
| The one-symbol observation returns every pattern that holds the symbol | a VAR's values; the VARs of a value |
| `future_potentials` | one slot's value given another's |
| `recall_threshold` | how general a rule gets |
| The empty ensemble | no rule from nothing |

**Missing or awkward (candidates for CORE, or for the module to carry).**

1. **Where a predicted pattern was learned.** A prediction carries name and frequency. `metadata` can hold a stream position, and `GET /pattern/{id}` returns it, but a prediction does not. The module therefore keeps its own log. Options: return a pattern's metadata with a prediction, or let a session predict against the node as it stood N learns ago.
2. **The observe response has no predictions.** `GET /sessions/{id}/predictions` computes on the current STM, which after an auto-learn in ROLLING mode holds six events and already has the window just learned. `cognition-data` has the right ensemble. It works, in two calls per token.
3. **The alignment for events of several symbols** is computed and not returned (open decision 6 of the frames module). Not needed while events hold one symbol.
4. **A name inside a pattern is opaque to matching** (Language Lab finding 60). node_1b recognises a rule only when the text was chunked the same way. The `rejoin` step exists because of it.
5. **At most 10,000 predictions per request** (`max_predictions`). The module reads every candidate. At scale it cannot.
6. **Cost.** node_0 learns one window per token: 15 windows of 7 symbols for the 21 tokens of Example 1. The Language Lab measured rolling windows of 3 at 3.119 stored symbols per symbol of text, and a new pattern at about 83 ms through KATO.
7. **`GET /pattern/{id}` for a pattern that was not learned** returns HTTP 200 with `{"pattern": {"status": "error", ...}}`, not 404.

## 11. Where the description is weak

Told plainly, as the project instructions ask. Each has output above.

1. **Echoes are not in the description.** Without the hold-out every window is one long contiguous match with its neighbours (Example 1, t=13).
2. **`missing` and `extras` do not cover the window's edges** (Example 1, t=14).
3. **A fresh integer per anomaly makes every rule unique.** Something has to give a slot the same id again (Example 5).
4. **One window per rule learns each structure at every shift** (Example 2: 9, 5 and 5 against 1, 1 and 1).
5. **Unaligned anomalies are not all noise.** A new phrase and a filler word look the same the first time (Example 3). `unexplained=break` removes only an insertion. It is a refinement, not a cure: "we saw" before a known "the cat" is still read as an insertion the first time it is seen.
6. **Position-for-position variables** lose a value of another length and invent correspondences inside equal-length gaps (Examples 3 and 4).
7. **KATO's default recall threshold** (Example 4).
8. **Slots are decided bottom-up at every instance.** A known rule does not help to read a new sentence. Reading top-down, with node_1b proposing the rule and node_2b saying whether a token is a known value of the slot, is the natural next step and is not built.
9. **Rule-scoped ids do not survive a rule generalising** (Examples 3 and 4), and old rules are left behind.
10. **The list format for node_2b** (section 9.1).
11. **Analogs closer than a window are invisible** (section 9.2).
12. **Stitching needs a boundary the brief does not give.** Chunk boundaries are found automatically. Stretch boundaries are not.
13. **Determinism.** The same events in the same order give the same names and counts. A VAR counter and value-named classes depend on arrival order, which the decisions of 23 Nov allow for cuts. Two sessions teaching at once would race for the counter, so either one writer names VARs or the id is derived from content (for example a hash of the rule's constants and the slot's index).

## 12. Open choices, as experiments

Following the lab's rule that a question an experiment can answer goes on the experiment list.

| # | Choice | Options in the sketch | What would decide it |
|---|---|---|---|
| 1 | What gives a VAR its id | `rule`, `neighbours`, `values`, and the combination of section 7 | VARs per annotated slot type; rule instances recognised; ids renamed or merged |
| 2 | Span | per window, stitched | chunks, rules and VARs per sentence; held-out sentences recognised |
| 3 | What closes a stretch | the application's marker; an unexplained token; a length limit; a learned boundary | rules seen again; agreement with sentence ends |
| 4 | Window and `recall_threshold` | 5, 7, 10, 15 by 0.1 to 0.9 | VARs per rule; rules seen again; slots found |
| 5 | Slots | `position`, `gap` | values lost as noise; rules per construction |
| 6 | Unexplained tokens | `drop`, `break`, keep as literals | rules never seen again |
| 7 | When a position varies | `mixed`, `min_support` | over-general rules against rules never seen again |
| 8 | Echo hold-out | by window (as here), by token | analogs lost at short range |
| 9 | Chunk choice | longest first (as here), most frequent first (the lab's repetition cut) | stored symbols per symbol against the repetition cut |
| 10 | Reading top-down | bottom-up only (as here), node_1b first | sentences recognised despite noise |
| 11 | node_2b layout | three shapes in one node (as here), a node per shape | lookups per question |
| 12 | Edge variables | off, on | rules and VARs added; slots found earlier |

**A smallest first experiment (proposal).** Text whose slots are annotated, so that "did it find the variables" has an answer: the user turns of the Schema-Guided Dialogue set (CC BY-SA 4.0, already checked for the frames module). Measure whether VAR positions fall on annotated slot spans, across choices 1, 2, 4 and 5. In-process first, then a sample through KATO. For scale and cost: WikiText-2 through the lab's corpus reader, with the lab's measures (stored symbols per symbol, held-out text already known).

## 13. How this sits beside the other threads

- **Learned cuts** (`claude/kato-learned-cuts-study.md`, plan awaiting approval). That study dropped cutting from ensembles because it needs a node of rolling windows first. This experiment has that node, at its known cost, and finds cuts as the edges of contiguous matches. The two can be compared on the study's measures. Nothing here replaces that plan.
- **Frames module** (`claude/kato-frames-module-summary.md`). `VAR|n` is the frames module's `<$n>` where it is stored back into KATO (its open decision 7). `slots=gap` is its "align with gaps". Joint values are its relation, one row per member. What this brief calls an insertion and removes is the frames module's optional element `<@n>`. "Seen" against "allowed" in Example 6 is its attested against recombined.
- **Language Lab.** Its findings on names inside patterns (60), the 10,000 cap (61) and rolling-window cost bound what can run through KATO. The examples are tokenised by its word-and-punctuation rule.

**Earlier work on the same idea.** Citations checked on 24 Nov 2026. None was read through in this session.

- van Zaanen (2000), "ABL: Alignment-Based Learning", COLING 2000. https://aclanthology.org/C00-2139/ Aligns pairs of sentences and takes the parts that differ as interchangeable. The closest relative of reading `missing` against `extras`.
- Mintz (2003), "Frequent frames as a cue for grammatical categories in child directed speech", Cognition 90, 91-117. https://doi.org/10.1016/S0010-0277(03)00140-9 Words between the same two framing words are grouped together. This is `naming=neighbours`.
- Solan, Horn, Ruppin and Edelman (2005), "Unsupervised learning of natural languages", PNAS 102(33), 11629-11634. https://doi.org/10.1073/pnas.0409746102 ADIOS: recurring patterns and classes of interchangeable elements, built up hierarchically. The relative of chunks plus VARs that share values.

## 14. Checks and how to rerun

**Code read:** KATO `main` at `f32bac0`: `kato/representations/prediction.py`, `kato/searches/pattern_search.py`, `kato/informatics/extractor.py`, `prediction_metrics.py`, `knowledge_base.py`, `kato/workers/observation_processor.py`, `pattern_processor.py`, `kato/storage/redis_writer.py`, `kato/api/endpoints/sessions.py`, `kato_ops.py`.

**Checks (24 Nov 2026).**

1. **The alignment can be rebuilt from the returned fields.** 502,184 of 502,184 predictions, against the matcher's own positions: the toy text and generated streams of 4 and 12 symbols, windows of 3, 5, 7 and 10. In-process.
2. **In-process equals through KATO.** `examples.py` prints 906 lines. With every node in a running KATO service and every learn, prediction, frequency and pattern read over REST, it prints the same 906 lines (sha1 `818a4c2a85c59ff50f9a022777f1d759374371b5`). The service was started from the checkout at `f32bac0` with one uvicorn worker, against ClickHouse 26.10.4.207, Redis 7.4.12 and Qdrant v1.17.1 in Docker. 3 min 50 s against 2.6 s. KATO's own image was not built: pip inside the build could not verify TLS through the sandbox's proxy.
3. **Determinism.** The same report under `PYTHONHASHSEED` 0 and 7.
4. **Invariants on 16 runs** (in-process): the echo hold-out equals "frequency minus the times the pattern is among the last six learns"; every learned window that is read ends before the window in the STM begins; every `PTRN|` symbol in node_1b and node_2b is a pattern of node_1a; every rule instance, with its values put back and its chunk names unravelled, gives back the tokens of its part; every VAR in node_1b has a value in node_2b.

**Not shown.** No real text, no scale, no timing beyond the two totals, no measure of quality. One worker and one session at a time. Events of one symbol only.

**Scripts** (shared in chat as `chunks-rules-sketch.zip`, in no repository): `kato_node.py` (a node in-process on KATO's classes), `kato_api_node.py` (the same interface over REST), `alignment.py`, `modeler.py` (the module; every choice a field of `Settings`), `examples.py`, `check_alignment.py`, `check_examples.py`, `explore2.py`, `show.py`, `report.txt`, `README.md`.

```sh
export KATO_REPO=/path/to/kato            # a checkout of github.com/sevakavakians/kato
./run.sh examples.py                      # all examples, in-process
./run.sh examples.py --digest             # one sha1 over the report
KATO_API=http://127.0.0.1:8000 KATO_API_TAG=run1 ./run.sh examples.py    # through a running service
```
