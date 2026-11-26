# One rule for a whole sentence: what entropy can and cannot do about it

26 Nov 2026. For a reader who was not involved. `summary-2026-11-26.md` says what the experiment is and how it is scored; this note takes up four questions asked after it.

1. Spell can serve as a KATO module in some situations. Mark it as something to build.
2. Is Drain compatible with how KATO works?
3. Is ADIOS?
4. On dialogue sentences the method makes one rule per whole sentence, and that does not work. Can entropy restrain it? Has someone solved this already? What are the options?

## 1. In brief

| Question | Answer | How sure |
|---|---|---|
| Spell as a module | Recorded as decided, in `methods-register.md`, with what building it still needs. | |
| Drain | **Compatible.** It is Spell's loop with another rule for joining. That rule runs on KATO's own matcher once a symbol says where its token stands. It belongs in the Spell module as a setting, for lines of fixed format. It is of no use for sentences. | Measured: 0.865 on the log benchmark on KATO. The published figure is 0.866. |
| ADIOS | **Its parts fit KATO. Its procedure does not.** The parts are the three things the hierarchy already has: patterns, classes of values, and sequences rewritten with both. The procedure needs the whole corpus, goes over it many times, cannot undo a step, and depends on the order of the sentences. | From its paper. Not run. |
| Entropy, as a floor on what a sentence may join | **No.** KATO already returns the measure (its weight of evidence). Used as a floor, it finds fewer of the marked values, 11.6% against 15.6%, and the worn-down rules stay. | Measured. |
| Entropy, as the way to cut a sentence into pieces | **Yes.** 46% of the marked values come out as exactly one piece, against 19% for cuts placed at random and 16% for one rule per sentence. KATO's own next-event distribution carries the signal as well as counts do. | Measured. The threshold was picked using the marked values. |
| Has someone dealt with the degeneracy? | **Yes, in 1994, with description length.** Bayesian model merging starts from exactly one rule per sentence and lets the length of the whole description decide every step. It is shown on small formal languages; on natural language its authors report mixed results. Later work on dialogue systems and on grammar learning agrees on the shape of the answer: rules for parts of sentences, and a variable that holds one known unit. | Read from the papers. Not run. |

**The one finding to keep.** Entropy does not help by judging whether a sentence fits a rule. It helps by saying where a unit ends, and, summed over everything stored, by saying whether a rule or a variable pays for itself.

## 2. The problem, in the data

The method under test keeps one rule per group of sentences. A new sentence joins the rule it shares most words with, in order, when that is at least half of the sentence. The rule keeps what the two have in common and gets a variable, written `*` here, wherever they differ.

On log lines this works (0.81 on a published benchmark). On 3,873 dialogue sentences it finds 16% of the 1,388 marked values exactly. Two things go wrong.

**Fault 1: no rule yet.** 48% of the marked values are in a sentence that shares half its words with no rule when it arrives. A sentence such as `i want to eat in new york at 7 pm` (made up for this note) is several parts put together. Other sentences share `in new york` or `at 7 pm` with it. Few share half of all of it.

**Fault 2: rules wear down.** Every sentence that joins a rule can only take fixed words away from it. These are five of the seven most-used rules at the end of the run on KATO, described and not quoted, because the results hold no text from the data:

| Sentences under the rule | What is still fixed in it | Variables |
|---|---|---|
| 98 | two words of thanks and the full stop | 2 |
| 58 | one word of reply and the full stop | 1 |
| 49 | one word of reply and the full stop | 1 |
| 35 | one word of reply, a comma and the full stop | 1 |
| 33 | the full stop, and nothing else | 1 |

64 rules have at most two fixed words and hold 518 of the 3,873 sentences. A rule of the shape `* .` says only that a sentence ends in a full stop. At the end of the run, 45% of the marked values sit inside a variable that is longer than the value.

Both faults come from the same two choices: the rule is as long as the sentence, and a variable may hold any stretch of words. Changing the threshold trades one fault for the other and never passes 16.4%.

## 3. What others have done

Each method below was read from its original paper, except where section 10 says that only an abstract or an earlier version was read. "Decision" is what the method uses the measure for.

| Who | Decision | Measure | Shown on | As data arrives? |
|---|---|---|---|---|
| Harris (1955); Jin and Tanaka-Ishii (2006) | Where a unit ends | The entropy of what follows a stretch: it falls inside a unit and rises at its end | Chinese characters into words: precision 0.88, recall 0.79 | The counts came from 200 MB of text |
| Cohen, Adams and Heeringa (2007), "Voting Experts" | Where a unit ends | High entropy at the edge, high frequency inside, decided by vote | Letters into words: F 0.76 on English | No: the whole text first |
| Du and Li (2019), Spell's own refinement | Is a placeholder a real variable? | How many different tokens it has held: under 8, and no digit, and the template is taken apart again | Logs: accuracy up on three data sets (0.82 to 0.97 on one), down on a fourth | Run now and then, not per line |
| LEMUR (2024); ECLIPSE (2024) | Constant or variable at one position | The entropy of the tokens seen at that position, against a threshold | Logs | Not stated clearly |
| Barzilay and Lee (2003) | Is a place where sentences differ a slot, or just other wording? | A slot, when no more than 30% of the sentences go the same way there | News sentences on one topic | No |
| Mintz (2003) | Which words are one class | The two words around them ("frame"): words that stand in the same frequent frame are one class | Speech to children: 98% of the pairings right, 7% of the possible pairings found | No: the 45 most frequent frames |
| Meng and Siu (2002); Pargellis and others (2001, 2004) | What is a chunk, and which chunks are one class | Chunks by mutual information. Classes by how alike the words around them are (Kullback-Leibler divergence). Rewrite the sentences, repeat | Pargellis and others: three dialogue corpora of 1,451 to 2,500 sentences, 8% to 27% of the class members wrong. Meng and Siu: flight queries | No: repeated passes |
| Solan, Horn, Ruppin and Edelman (2005), ADIOS | Where a pattern starts and ends; which units fill one place | A drop in the share of sentences that continue the same way, with a significance test; the same words before and after | Flight queries (ATIS-2): 40% of unseen sentences covered, about 70% of generated ones judged acceptable | No, and the result depends on the order |
| Stolcke and Omohundro (1994), Bayesian model merging | Every merge of two units into a class, and every chunk | The posterior of the grammar: the length of the grammar's description, and how well it fits | Small formal languages: every target grammar recovered. Natural language: "mixed results" in "preliminary experiments", in their words | It has a form in which taking in new samples and merging alternate |
| Tatti and Vreeken (2012) | Which patterns to keep | The total description length; a gap inside a pattern costs bits | Text: `support vector machine` and the like | No |

Three things in this table bear on the question.

1. **The exact degeneracy has a published answer.** Model merging begins with one rule per sample sentence, which is where this work stands. Left alone that grammar is as long as the data. Merged without limit it becomes one rule that fits everything, the rule with only a full stop above. The description length is what stops it at both ends: a merge is made only if grammar and data together get shorter.
2. **In every method that learns from language, a variable holds one known unit.** A word, or a chunk found earlier. Never an arbitrary stretch. In the log parsers a variable is one token (Drain) or anything between two constants (Spell), which is harmless when a parameter is a number or a name, and is the source of the one-word rules here.
3. **The measures are of three kinds, and they do different jobs.** Entropy of what comes next, for where a unit ends. Agreement of the surroundings, for which units are one class. Description length, for whether to keep any of it.

## 4. What KATO already returns

At the commit used here (v7.1.0 plus 34 commits, `f32bac0`), a KATO prediction carries fields that are these measures. The module that makes rules has used only the last of them so far.

| KATO field | What it is | The published measure it corresponds to |
|---|---|---|
| `future_potentials`, `ends_here` | The probability of each next event, and of no next event, given what was just observed | The distribution whose entropy Harris, Jin and Tanaka-Ishii and Voting Experts use. ADIOS's test is a drop in the same quantity. |
| `bayesian_likelihood` | Good's weight of evidence: how many bits better than chance a pattern explains the observation. Each match adds bits, more for a rare symbol; each missing or extra symbol costs 4.32 bits. | The saving in description length from coding the observation with that pattern. Summed over the data, this is what model merging and Tatti and Vreeken count. |
| `confluence` | How many bits more often a pattern was learned than chance would put its symbols together | The association measure used to make chunks (mutual information). |
| `missing`, `extras` | What the pattern has that the observation lacks, and the reverse | The surroundings test: two things that stand between the same matched neighbours. The module reads variables from these already. |

One thing is missing. `bayesian_likelihood` counts a token that stands at a variable as an extra, that is, as noise. That is right for a pattern without variables. For a rule with a variable it is wrong, and section 5.1 shows what it costs.

## 5. What was measured

All on the dialogue probe: 3,873 user sentences, 1,388 marked values of six kinds (a time, a city, a kind of food, a date, a restaurant's name, a film's title). Unless a line says otherwise, a sentence is cut and judged with what was learned from the sentences before it, as KATO would have it. `experiments/entropy_probe.py`; numbers in `experiments/results/entropy_probe_2026-11-26.json`, which is two runs put together: the default parts, and section 5.5 (`--only kato`, 44 minutes).

### 5.1 KATO's weight of evidence as a floor on joining a rule

**The idea.** Let a sentence join a rule only if the rule explains it better than chance: `bayesian_likelihood` above 0 bits. A sentence should then not join a rule that is only a full stop.

| | Values found exactly, as the sentence arrived | At the end of the run | Rules at the end | Rules with at most two fixed words, and the sentences under them |
|---|---|---|---|---|
| Spell's loop on KATO, as before | 216 (15.6%) | 228 (16.4%) | 941 | 64 rules, 518 sentences |
| The same, joining only above 0 bits | 161 (11.6%) | 169 (12.2%) | 1,102 | 70 rules, 464 sentences |

**Verdict: worse on both counts.** A quarter fewer values are found, and the worn-down rules are still there.

**Why.**

1. **It holds back the wrong sentences.** Of the 2,899 joins in the first run, 687 were at or below 0 bits. Those 687 joins held 101 of the 216 values that were found. A sentence that carries a value has words standing at a variable, KATO charges 4.32 bits for each of them, and a time of four words costs more than the matching words earn.
2. **Wear is not one bad join.** A rule gets from a whole sentence to one word and a full stop in steps, and each step is a sentence joining a rule that still explains it well. A test on one match cannot see that. A test on what the edit does to everything stored can, and that is what description length is.

### 5.2 Is the entropy higher at the edges of a value?

For every place between two words: the entropy of what has followed the word before it, and of what has preceded the word after it. AUC is the chance that an edge of a value scores higher than a place it is compared with: 0.5 is a coin, 1.0 is perfect.

| | Mean, at the edge | Mean, inside a value | Mean, elsewhere | AUC against inside a value | AUC against elsewhere |
|---|---|---|---|---|---|
| What follows the word before a value's start | 3.91 bits | 2.10 | 2.72 | 0.81 | 0.75 |
| What precedes the word after a value's end | 5.30 bits | 1.98 | 2.96 | 0.89 | 0.81 |

**Verdict: the signal is there, and it is strong for a statistic this simple.** After `in`, many different words have followed, so a new unit is about to start. After the first word of a two-word city, few have. By kind, against the inside of a value: city 0.96 and 0.99, restaurant's name 0.93 and 0.99, time 0.86 and 0.89, food 0.81 and 0.80, date 0.72 and 0.94, title 0.72 and 0.96.

### 5.3 Cutting by that entropy

Two of the three rules of Jin and Tanaka-Ishii, as the paper states them (`experiments/branching.py`). **B_increase** cuts where the entropy rises as the stretch read grows; it was the paper's best. **B_ordinary** cuts where the entropy is above a threshold. A value counts when both its ends are cut and nothing inside it is. "By chance" is what cuts placed at random would give at the same rate of cutting.

| Rule | Places cut | Values that are exactly one piece | By chance at that rate |
|---|---|---|---|
| B_increase, threshold 0 | 39% | 118 (8.5%) | 10.9% |
| B_ordinary, 3.0 bits | 74% | 613 (44.2%) | 23.0% |
| **B_ordinary, 3.5 bits** | 62% | **644 (46.4%)** | 19.1% |
| B_ordinary, 4.0 bits | 48% | 485 (34.9%) | 14.1% |
| B_ordinary, 4.5 bits | 31% | 326 (23.5%) | 8.2% |

**Verdict: the threshold rule works, and the rule the paper found best does not.**

1. **B_ordinary at 3.5 bits cuts out 46% of the values exactly**, 2.4 times what chance gives, and almost three times the 16% of one rule per sentence.
2. **B_increase is at chance.** It was built for characters and 200 MB of text. On 30,000 words, the entropies of longer stretches rest on a handful of sightings.
3. **The threshold was picked with the marked values in view.** As a check it was picked on the first half of the sentences and applied to the second: 3.5 bits again, 49.1% against 20.3% by chance.
4. **It differs a lot by kind.** City 81%, restaurant's name 71%, food 32%, time 31%, title 28%, date 19%. A time said in six or seven words, a clock time and then the part of the day, has high-entropy places inside it. It is a small rule of its own, not one unit.
5. **How good is 46%?** I found no published score for a method of this kind on these sentences. The nearest marker: a 2022 study of the same task that uses neural language models reports that its span-finding step recovers 54% to 68% of hand-labelled spans in 200 utterances (Yu and others 2022, table 7). The sample and the way a match is counted differ, so it marks the region and is not a comparison.

### 5.4 Rules for parts of sentences

Cutting is not yet a rule. Two ways of making rules from the pieces, both scored by the probe's own measure: the share of marked values that are exactly one variable when the sentence arrives. The second column is the price: how many variables were marked in all. The probe marks six kinds of value only, so a variable that holds three verbs of the same meaning counts against a method here although it may be a good variable.

| | Values found exactly | Variables marked | Second half of the sentences only |
|---|---|---|---|
| Spell's loop on words: one rule per sentence, as before | 224 (16.1%) | 4,011 | 17.8% |
| Spell's loop on the pieces instead of the words | 260 (18.7%) | 3,770 | 18.1% |
| Two words around a piece, seen 2 times with 1 other piece | 582 (41.9%) | 11,792 | 45.6% |
| ... seen 5 times with 3 other pieces | 524 (37.8%) | 8,050 | 42.4% |
| ... seen 10 times with 5 other pieces | 450 (32.4%) | 6,605 | 36.8% |
| ... seen 20 times with 8 other pieces | 344 (24.8%) | 5,214 | 28.1% |
| Two words around one word (Mintz's frame as published) | 281 (20.2%) | 14,719 | 20.1% |

"Two words around a piece" is the smallest rule with a variable there is: `in * .` The piece is a variable when those two words have stood around other pieces before.

**Verdict.**

1. **Cutting alone does not help** while the rule is still one per sentence: 18.7% against 16.1%, and no gain on the second half.
2. **The smallest rule for a part of a sentence finds one and a half to two and a half times as many values**, 25% to 42%, because it does not need the rest of the sentence to match.
3. **It is not selective.** It marks up to three times as many variables, and about 5% to 7% of them are marked values at each of the four settings. Being seen often does not make two words the frame of a value. Something must still decide which variables are worth having and which are the same variable. That is the class step of the methods in section 3, and their third measure.
4. **This is a measurement, not a method.** It puts two published ideas side by side to see how far a rule for a part of a sentence reaches. It is not proposed as the design.

### 5.5 Does KATO's own distribution carry the signal?

A KATO node learned each sentence whole, after being asked about it. At every place between two words it was shown the words before and its `future_potentials` and `ends_here` were read. The entropy of that distribution, at the start of a value against the inside of one:

| What the entropy is taken from | Mean at a value's start | Mean inside a value | AUC against inside | AUC against elsewhere |
|---|---|---|---|---|
| Counts of what followed the one word before | 3.91 bits | 2.10 | 0.81 | 0.75 |
| KATO, shown the one word before | 3.84 bits | 2.07 | 0.81 | 0.75 |
| KATO, shown the two words before | 3.18 bits | 1.66 | 0.82 | 0.74 |
| KATO, shown the whole sentence so far | 2.94 bits | 2.13 | 0.67 | 0.69 |

**Verdict: yes.** A node that holds whole sentences, asked with the last one or two words, gives the same signal as a table of counts. No extra store is needed for the forward direction. The backward direction, which section 5.2 shows to be the stronger one, has no field of its own; a second node fed the sentences backwards would give it. That was not run.

This bears on the separate study of learned cuts, which set cutting by prediction aside because it seemed to need a node of rolling windows first. Where the sequences already have ends, as sentences and lines do, it does not: a node of whole sequences is enough. For a stream with no ends at all the question stays open.

### 5.6 What stood at the placeholders

Spell's own refinement and the log parsers that use entropy decide from what one placeholder has held. On these sentences there is too little to decide from.

| Placeholders of Spell's rules at the end of the run | How many | Median number of different things held | Spell's rule would take apart |
|---|---|---|---|
| At least half of what they held is exactly a marked value | 89 | 2 | 62 (70%) |
| The others | 1,283 | 2 | 1,026 (80%) |

**Verdict: not usable here as it is.** A rule on these sentences has a handful of sentences under it, so a placeholder has held two or three things, and nothing separates a real variable from a worn place. Spell's rule would take most of the real variables apart with the rest. What a variable has held has to be pooled across rules, which again is the class step.

## 6. Options

| | Option | What changes | Evidence here | Prior art | Cost and risk |
|---|---|---|---|---|---|
| A | A floor on the evidence of a join | One setting | Worse: 11.6% | Good's weight of evidence | None. Rejected as it is. |
| B | Make KATO's evidence aware of variables | The evidence for a rule scores a value by how expected it is at that variable, not as noise | Not built. Section 5.1 says why the present measure fails. | The coding of gaps in Tatti and Vreeken; the likelihood in model merging | A change in KATO or a calculation in the module. Useful only with pooled variables. |
| C | Cut each sentence by entropy, then make rules | The unit of a variable becomes a piece | 46% of values cut out exactly. With one rule per sentence still, 18.7%. | Harris; Jin and Tanaka-Ishii | Small. Needs a threshold. Not enough alone. |
| D | Rules for parts of sentences, variables as classes of pieces | The unit of a rule becomes a part of a sentence. This is the design as first drawn, with cuts in place of fixed windows. | 25% to 42% with the crudest such rule; not selective. | Mintz; Meng and Siu; Pargellis and others; ADIOS | Medium. The class step must be chosen and built. |
| E | Description length as the judge of every edit | One measure decides whether to merge, to chunk, and to keep | Not run. It is the published remedy for this degeneracy. | Stolcke and Omohundro; Langley and Stromsten | Largest. The search can be slow; its authors report mixed results on natural language. |

**What I recommend.**

1. **For data in which one sequence is one message: build Spell as the module**, with Drain's rule as a setting. That is decided, and section 7 adds the evidence for the setting.
2. **For language-like data: stop adjusting the whole-sentence rule.** A threshold does not fix it and a floor on the evidence makes it worse. Change the unit (C and D), and take the judge from description length (E).
3. **Before building: get a reference number from a published method of that kind.** There is an open implementation of ADIOS (`madios`, C++, under the zlib licence). Run on the probe with the settings its description gives, it would say what such a method finds on these sentences, as `drain3` did for Drain. It is third-party code, so I have not fetched it.
4. **Then build model merging's two steps on KATO** and hold them to the formal languages of its paper, where the published result is that every grammar is recovered. Its starting point is where this work stands, its two steps are edits KATO already makes, its judge is in the bits KATO already returns, and it has a form in which taking in new sentences and merging alternate. ADIOS would be the comparison, not the design.

Points 3 and 4 are proposals. Nothing of them is started.

## 7. Drain, in detail

**What Drain is.** Like Spell it keeps one template per message type and gives it a placeholder where a new line differs. It differs in which type a line may join:

1. only a type whose lines have the line's number of tokens;
2. only a type whose template starts with the line's leading tokens;
3. of those, the one that has the line's own token at the most positions, if that is enough of them.

Drain finds the candidates of rules 1 and 2 with a small tree. The tree is an index. KATO has its own.

**The one real difference.** Rule 3 compares by position: token 3 of the line against token 3 of the template. KATO compares by order: it finds the most symbols the two have in the same order, wherever they stand. `a b c d` and `b c d e` share three of four for KATO and nothing for Drain.

**How it runs on KATO all the same.** Put the position into the symbol. Token `send` at position 0 becomes the symbol `0|=send`; a placeholder at position 2 is `2|*`. Two sequences then share a symbol only where they have the same token at the same position, and what KATO returns as `matches` is Drain's count. Storing, replacing and retiring a template are as for Spell.

**Measured**, on the log benchmark (`experiments/log_benchmark.py`, the runs "rules" and "rules on KATO"):

| | Average over the 16 systems |
|---|---|
| Drain, published | 0.866 |
| Drain's three rules on KATO | 0.865 |
| The same three rules without KATO | 0.865 |
| The `drain3` package | 0.860 |
| Spell on KATO, for comparison | 0.811 |
| Spell, published | 0.793 |

1. **On KATO, every one of the 32,000 lines is grouped exactly as the three rules group it without KATO.**
2. **Each of the 16 systems equals the published figure** once rounded as the paper rounds; none is more than 0.0005 away.
3. **The `drain3` package differs on one system**, Android: 0.831 where the paper has 0.911 and the three rules give 0.911. On the other 15 it groups every line as the rules do. I did not look into why.
4. On KATO: 30,209 learns and as many predictions, 2,163 patterns stored, 549 of them retired, 20 seconds in-process against 0.4 without KATO.

**Verdict.** Compatible, and not too different. It is a setting of the Spell module: three more conditions on which rule a line may join, and symbols that carry their position. It scores higher than Spell where lines of one type have the same length and the same layout, which is most logs. Where they do not, it is worse: on the dialogue sentences Drain finds 11% of the values, the lowest of everything tried, because `new york` and `boston` make lines of different length.

One thing to know before it is built: a symbol that carries its position makes two patterns unlike each other as soon as one token is inserted. That is Drain's own assumption, and it is the opposite of what KATO's matcher is good at.

## 8. ADIOS, in detail

**What ADIOS does.** It loads all sentences as paths through a graph of words. It looks for a stretch where many paths run together and then spread out, tests whether that is more than chance, and makes the stretch a pattern. Among the paths that share the words before and after a place, it collects what stands at that place into a class. It then replaces each pattern by one new unit in every sentence and starts again, so patterns come to hold patterns.

| Part of ADIOS | The same thing in KATO | Fits? |
|---|---|---|
| The share of paths that continue the same way | A next-event probability: `future_potentials`, or pattern frequencies | Yes. Section 5.5 shows KATO's distribution carries this signal. |
| The same share, read backward | No field. A node fed the sequences backwards. | Yes, at the cost of a second node. |
| A pattern: a stretch that passes the test | A learned pattern, named by its content | Yes |
| A class: what stands at one place between the same neighbours | A variable and its values, read from `missing` and `extras` | Yes. This is what the module does. |
| An existing class is used again when enough of its members are seen (0.65) | One of the three ways to give a variable its identity | Yes |
| Replace a pattern by one unit everywhere | The node above holds the sequence with the pattern's name in its place | Yes |
| Load the whole corpus, then pass over it until nothing new is found | KATO learns as data arrives | **No** |
| A replacement is never undone | KATO can retire a pattern and bring it back | KATO does better here |
| The result depends on the order of the sentences. The best published result on the large grammar pools 150 learners, each given another order. | The same input in the same order gives the same output. One learner. | Deterministic, yes. But the published quality rests partly on pooling that one learner does not have. |

**Verdict.** The parts are compatible, more so than those of Spell or Drain, because ADIOS and the hierarchy are built from the same three things. The procedure is not. I would not port ADIOS whole. Its two tests can be asked as data arrives, and KATO's retire is the undo that ADIOS lacks.

**Two cautions about holding KATO's version to the published one.**

1. The open implementation, `madios`, says in its own description that its output can differ from the original program's, because the original used approximations that were never documented. So there is no program to match line for line, as there was for Spell.
2. I have not checked whether the data ADIOS was scored on can be obtained.

## 9. Corrections and limits

1. **One count in the summary of 26 Nov was off by one.** Sentences that joined the very first template were scored as having no rule. Spell, written in Python, finds 224 of the 1,388 values, not 223, and marks 4,011 variables, not 4,003. The percentages (16.1% and 5.6%) are unchanged. Nothing measured on KATO changes. The summary and the notes of 24 Nov carry the correction, and there is a test for it.
2. **Thresholds were picked using the marked values.** Where that matters, the second half of the sentences is reported with a threshold picked on the first.
3. **The probe counts six kinds of value.** "Variables marked" is therefore a price, not an error count.
4. **Most of this ran in-process**, on KATO's own matching and scoring code at `f32bac0`. Checked through a live KATO service at the same commit: the 34 tests marked for it; Drain's rule on two of the 16 log systems, Apache and HDFS, which gave the same groups and the same patterns, stored and retired; and KATO's next-event entropy on the first 150 sentences, which gave the same numbers. One difference turned up: a service takes `max_predictions` up to 10,000 only, and the in-process stand-in took any number. It now refuses a larger one. Nothing in KATO was changed.
5. **Not run**: ADIOS, model merging, Voting Experts, a node fed backwards, and Spell's split and merge as a whole.

## 10. Sources

Original papers, each consulted for this note at the link given, unless marked.

- Harris (1955). "From phoneme to morpheme." Language 31(2):190-222. Not read for this note; cited as in the study of learned cuts.
- Jin and Tanaka-Ishii (2006). "Unsupervised Segmentation of Chinese Text by Use of Branching Entropy." https://aclanthology.org/P06-2056/
- Cohen, Adams and Heeringa (2007). "Voting Experts: an unsupervised algorithm for segmenting sequences." https://doi.org/10.3233/IDA-2007-11603
- Du and Li (2016). "Spell: Streaming Parsing of System Event Logs." https://doi.org/10.1109/ICDM.2016.0103
- Du and Li (2019). "Spell: Online Streaming Parsing of Large Unstructured System Logs." https://doi.org/10.1109/TKDE.2018.2875442
- He, Zhu, Zheng and Lyu (2017). "Drain: An Online Log Parsing Approach with Fixed Depth Tree." https://doi.org/10.1109/ICWS.2017.13 ; the later version read for this note: https://arxiv.org/abs/1806.04356
- Zhu and others (2019). "Tools and Benchmarks for Automated Log Parsing." https://arxiv.org/abs/1811.03509
- Zhang, Guo, Le, Yang, Liu and Li (2024). "LEMUR: Log Parsing with Entropy Sampling and Chain-of-Thought Merging." https://arxiv.org/abs/2402.18205
- Zhang and others (2024). "ECLIPSE: Semantic Entropy-LCS for Cross-Lingual Industrial Log Parsing." https://arxiv.org/abs/2405.13548
- Barzilay and Lee (2003). "Learning to Paraphrase: An Unsupervised Approach Using Multiple-Sequence Alignment." https://arxiv.org/abs/cs/0304006
- Mintz (2003). "Frequent frames as a cue for grammatical categories in child directed speech." https://doi.org/10.1016/S0010-0277(03)00140-9
- Meng and Siu (2002). "Semiautomatic Acquisition of Semantic Structures for Understanding Domain-Specific Natural Language Queries." IEEE Transactions on Knowledge and Data Engineering 14(1):172-181. Abstract only.
- Pargellis, Fosler-Lussier, Potamianos and Lee (2001). "A comparison of four metrics for auto-inducing semantic classes." https://slp-ntua.github.io/potam/preprints/conf/01_ASRU_andy_underst_II.pdf ; the journal version, Pargellis and others (2004), "Auto-induced semantic classes", Speech Communication 43(3):183-203, was not read.
- Solan, Horn, Ruppin and Edelman (2005). "Unsupervised learning of natural languages." https://doi.org/10.1073/pnas.0409746102
- `madios`, an open implementation of ADIOS, zlib licence. https://github.com/liesenf/madios , a fork of `shaobohou/madios`. Its description only; the code was not fetched.
- Stolcke and Omohundro (1994). "Inducing Probabilistic Grammars by Bayesian Model Merging." https://arxiv.org/abs/cmp-lg/9409010
- Langley and Stromsten (2000). "Learning Context-Free Grammars with a Simplicity Bias." https://doi.org/10.1007/3-540-45164-1_23 . Abstract only.
- Tatti and Vreeken (2012). "The Long and the Short of It: Summarising Event Sequences with Serial Episodes." https://arxiv.org/abs/1902.02834
- Yu and others (2022). "Unsupervised Slot Schema Induction for Task-oriented Dialog." https://arxiv.org/abs/2205.04515
- Good (1985). "Weight of evidence: a brief survey." Bayesian Statistics 2, 249-270. For the name; KATO's own definition is in `kato/informatics/prediction_metrics.py`.
- The dialogue data: https://github.com/google-research-datasets/dstc8-schema-guided-dialogue
