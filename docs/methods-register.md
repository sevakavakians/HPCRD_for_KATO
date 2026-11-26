# Methods for KATO: what to build, and what has been looked at

A running list, started 26 Nov 2026. One row per published method that was considered for making KATO segment sequences, chunk them and make rules from them by itself. It is kept so that a decision is not lost and a method is not looked at twice.

**How to read the status.**

| Status | Meaning |
|---|---|
| **Build** | Sevak decided it is to be built for KATO. |
| **Candidate** | Looks worth building. Not decided. |
| **Tried: not as is** | Measured here, and it did not help in the form tried. |
| **Not run** | Read from its paper only. |

"Fits KATO" asks four things: does it give the same output for the same input in the same order, can it work as data arrives, can it be built from what KATO already does (match, learn, retire, predict), and can every decision it makes be shown.

The two tests named in the table are described in `summary-2026-11-26.md`: the **log benchmark** (16 systems, 2,000 log lines each, sorted by hand; the score is the share of lines grouped exactly as by hand) and the **dialogue probe** (3,873 user sentences with 1,388 marked values; the score is the share of values that are exactly one variable when the sentence arrives).

## The list

| # | Method | What it does | Fits KATO? | Measured here | Status |
|---|---|---|---|---|---|
| 1 | **Spell** (Du and Li 2016) | Keeps one template per group of sequences. A new sequence joins the template it shares the longest common subsequence with, and the template gets a placeholder wherever they differ. | Yes, as it is. KATO's matcher gives the common subsequence; learn and retire replace the template. | Log benchmark 0.811 (the published figure is 0.793): every one of the 32,000 lines grouped as the paper's algorithm groups it, apart from lines of one token. Dialogue probe 16%. | **Build**, as a KATO module, for data in which one sequence is one message (log lines, records, fixed messages). Decided 26 Nov 2026. |
| 2 | **Drain** (He, Zhu, Zheng and Lyu 2017) | The same loop with another rule for joining: the same number of tokens, the same leading tokens, and the same token at enough positions. | Yes, as a setting of the Spell module. The rule runs on KATO's own matcher once a symbol says where its token stands. | Log benchmark 0.865 on KATO (published 0.866; equal on each of the 16 systems after rounding). Dialogue probe 11%. | **Candidate**: a setting of the Spell module for lines of fixed format. Not a module of its own. |
| 3 | **Cutting by branching entropy** (Harris 1955; Jin and Tanaka-Ishii 2006) | Cuts a sequence where what follows, or what precedes, is uncertain. | Yes. KATO's `future_potentials` is that distribution; its entropy separates the start of a marked value from the inside of one as well as counts do (0.81 against 0.81, where 0.5 is a coin). | The threshold rule makes 46% of the marked values exactly one piece, against 19% by chance. The rule the paper found best is at chance here. | **Candidate**: the cutter. It needs one threshold. |
| 4 | **A floor on KATO's weight of evidence** (`bayesian_likelihood`; I. J. Good's weight of evidence) | A sentence may join a rule only if the rule explains it better than chance. | It is a field of every KATO prediction. | Dialogue probe 15.6% falls to 11.6%, and the worn-down rules stay. | **Tried: not as is.** It counts a variable's value as noise. |
| 5 | **ADIOS** (Solan, Horn, Ruppin and Edelman 2005) | Finds patterns in parts of sentences by a statistical test, groups the units that fill the same place into a class, and repeats on the result. | Its parts, yes. Its procedure, no: it needs the whole corpus, passes over it many times, cannot undo, and depends on the order of the sentences. | Not run. | **Candidate**: its two tests, run as data arrives. Not the whole procedure. |
| 6 | **Bayesian model merging** (Stolcke and Omohundro 1994); description-length grammar induction (Langley and Stromsten 2000) | Starts from one rule per sentence. Merges units into classes and chunks sequences into units for as long as the description of grammar and data gets shorter. | Its two steps are KATO's edit (learn the new, retire the old). Its judge is in bits, as KATO's evidence is. It has a form in which taking in new samples and merging alternate. | Not run. | **Candidate**, and my proposal for the next method to build. |
| 7 | **Classes by shared context, chunks by association** (Mintz 2003; Meng and Siu 2002; Pargellis and others 2004) | Two units are one class when they stand between the same neighbours. Words that keep company are one chunk. Repeat. | Yes: this is what the module reads from KATO's `missing` and `extras`. | The smallest such rule, two words around a piece, finds 25% to 42% of the marked values, depending on how often the two words must have been seen (16% for one rule per sentence). It marks 1.3 to 3 times as many variables. | **Candidate**. The signal is measured; no method is built. |
| 8 | **Statistics of one placeholder** (Spell's split, Du and Li 2019; position entropy, LEMUR 2024; Barzilay and Lee 2003) | Decides from what a placeholder has held whether it is a real variable. | Yes. | On the dialogue sentences the median placeholder had held 2 different things. That is too little to decide anything from. | **Tried: not as is** on small data. Belongs in the Spell module for logs. |
| 9 | **Description length for sets of patterns** (Tatti and Vreeken 2012; Lam and others 2014) | Keeps a pattern only if the data gets shorter to describe with it. | Yes, in principle. | Not run. | **Not run**. Same idea as 6, without variables. |
| 10 | **Alignment-based learning** (van Zaanen 2000) | Aligns pairs of sentences; what differs is a constituent. | Yes. | Not run. | **Not run**. Looked at on 24 Nov. |
| 11 | **Voting Experts** (Cohen, Adams and Heeringa 2007) | Cuts where entropy is high at the edge and frequency is high inside, by vote. | Needs the whole corpus first. | Not run. | **Not run**. In the separate study of learned cuts. |

## What building row 1 needs settled

1. **Which settings the module exposes.** The threshold `tau`, and Drain's three rules as a second way of joining (row 2).
2. **Spell's own refinements.** The journal version (Du and Li 2019, section 3.5) splits a template whose placeholder took few different tokens and merges templates that differ in one place. Neither is built. On three of that paper's four data sets they raise accuracy, and on one they lower it.
3. **Three behaviours of KATO's API around retired patterns**, written up in the KATO repository as `docs/maintenance/retired-pattern-api-issues.md`.
4. **A line of one token.** KATO does not learn a pattern of one symbol, so the module keeps such a line as a type of its own.

## Where the evidence is

| Rows | Note in `docs/` | Numbers in `experiments/results/` |
|---|---|---|
| 1 | `round-4-log-benchmark-and-outer-loop-2026-11-24.md` | `log_benchmark_2026-11-26.json` |
| 2 to 9 | `entropy-and-rule-units-2026-11-26.md` | `log_benchmark_2026-11-26.json`, `entropy_probe_2026-11-26.json` |
| 5, 10 | `round-3-published-methods-2026-11-24.md` | |
