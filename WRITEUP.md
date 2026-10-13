# Architecture under a fixed, weak model

**Constraint extraction is model-based.** The model reads every line and turns
each into one constraint or into nothing. Nothing in the answering pipeline
pattern-matches the notes; everything after extraction — the kind, the
assignments, the localised contradiction — is symbolic and exact.

| budget | macro (n=9) | range | u / a / i | calls/item |
|---|---|---|---|---|
| **1×** | **0.469 ± 0.041** | 0.417–0.533 | 0.42 / 0.38 / 0.60 | 1 |
| **3×** | **0.504 ± 0.043** | 0.450–0.583 | 0.50 / 0.47 / 0.55 | 2–3 |
| **10×** | **0.504 ± 0.034** | 0.450–0.550 | 0.52 / 0.45 / 0.60 | 2–10 |
| no formal layer | **0.000 ± 0.000** | — | 0.00 / 0.00 / 0.00 | 1 |

Nine runs per budget, mean ± population SD; the last row is the brief's 0.0%
reproduced. One call buys 0.469, a third buys 0.035 more, **the seven after that
buy nothing** — 3× and 10× are equal to three decimals. §4 says why. Full tables
in [ABLATION.md](ABLATION.md); each claim names the `dev/` script behind it.

## 1. Characterising the model first

**It cannot hold the problem.** One-shot it declares `unique` for everything and
scores 0.0. It does worse than guess — it put two people on one block, and
across six items emitted three incompatible shapes for the station field.
Ambiguity and contradiction are absent from its output entirely. That decided
the architecture: the model would never count, compare or decide
(`probe_model.py`).

**It is good at one small thing:** translating a single line, especially
recognising one that says nothing — 28 of 28 padding lines. So it gets only
local, lexical work.

**Its errors are asymmetric.** A regex reference parser over the visible pool
(`refparse.py`, 100% of 1,137 lines) gave per-line ground truth; precision per
*emitted* code (`calibrate.py`) is 87% overall but spans `BETWEEN` 97% down to
`BLOCK` 71%. The two *absolute* forms are worst because the signature error is
**resolving** a relative statement into an absolute one — "on the block directly
after Meera" came back as `BLOCK Rohan 11:00` seven times. That costs more than
87% suggests: an invented placement kills most of an item's 720 worlds, a wrong
relative one kills few.

**Three of four distractor families are free to get wrong**
(`check_entailment.py`). Thwarted wishes read as negatives are **64/64
entailed** — already true in every consistent world; unresolved questions
**31/31**; but past-tense station history **0/25**, always false of the current
rota. One dangerous over-reading, with a crisp signature, so the prompt's rules
lead with it — worth 0.133.

**Then I verified the target semantics before building.** Reference parser plus
solver, counting only present-tense definite statements, scores **macro 1.0000**
on all 60 items (`check_semantics.py`). The symbolic layer is correct, so every
remaining point is an extraction problem.

## 2. Why each component exists

**The spine.** One call translates the lines; the solver enumerates all 720
worlds. One world is `unique`, two or more `ambiguous` (all returned), none
`inconsistent`, and the citation is a minimal unsatisfiable subset found by
deletion — *definitionally* the scorer's rule, not an approximation of it.

**`calib`, the calibrated drop** (−0.022, no model call). Every conflicting set
here has at least three statements and the key agrees — **none of size 2**. So
an extraction whose smallest core has two is provably not reporting a conflict
the notes contain; it is wrong whichever kind the item is, so there is nothing
to lose by disbelieving one of them, and the precision table says which.

**`softneg`, soft negatives** (−0.033, no model call). A line read as inert that
names exactly one person and one clock time is tried as a negative block claim,
kept only if it removes worlds and leaves one — safe *because* of the entailment
measurements above. The two free repairs are **additive, not overlapping**
(−0.079 together); I expected overlap and was wrong.

**`mus`** (−0.167). Citing every constraining line instead of a minimal core
scores **0.00** on all 20 inconsistent items. Citing more is disqualifying, not
safer.

**`repair`.** The world count is a proof of extraction error needing no key, so
budget goes only to the lines responsible: `count > 4` re-reads just the lines
read as inert; `count == 0` re-reads *exactly the core*, three lines of twenty.
Items emitting an impossible answer fall from **11 at 1× to 1 at 3×**.

**The reply format was a component in disguise.** The dominant failure at full
length is derailing into commentary and never reaching the rest of the list —
one item answered 2 of 20 lines after a 400-token monologue about my own prompt.
Dictating the reply's first characters and banning question marks took coverage
**68% → 89%**; shortening `NONE` to `-` took macro 0.300 → 0.317; omitting inert
lines entirely *lost* eight points. Format beat every wording change to the
rules.

## 3. What I built and then removed

**Two aggregation designs.** The first merged extractions line by line and made
the curve non-monotone — 1× 0.450, 3× 0.517, **10× 0.400** — because per-line
majority *drops* a constraint only two passes of five found, and when that is
the one a contradiction rests on, a correctly-detected inconsistent item
silently becomes satisfiable. The second voted on whole verdicts. Replaying one
three-pass log through every rule with the extraction held fixed
(`tune_aggregation.py`), **every way of combining three extractions lost to the
best single one** — 0.383 to 0.517, against individual passes of 0.533 / 0.400 /
0.550. The errors are systematic, not noise, so averaging reinforces them. What
works is *selection*: discard candidates that are provably wrong (count > 4) and
keep the first survivor — 0.567, saturating at three passes. Two further fixes
after 3× again came in below 1×: a contradiction wins only if it was the first
conclusion or a second candidate reaches the same core, and the core is re-read
twice. 3×: 0.450 → 0.517.

**Restatement agreement, removed.** The scorer rejects two citations normalising
to one string, so I built a component to avoid the trap — then measured that no
two body lines in the visible set normalise identically
(`check_restatements.py`). Catching true re-phrasings needs semantic matching,
and the obvious symbolic proxy groups "A is earlier than B" with "A is next to
B". Removed rather than guessed at.

**`recover` and `strict`, kept but near-dead** (−0.004; `-strict` measures a
fraction *above* full — both inside the noise). Most of what `recover` was for
proved fixable upstream: the parser was discarding 37 codes a run over a
trailing `?`. Reported at roughly zero rather than quietly deleted.

**An honest non-choice.** `n=3` sampling returns three completions in *one* HTTP
request, which the counting proxy would see as one call. I did not do it. Three
samples is three samples.

## 4. Where it breaks, and why the curve is flat

The plateau has a number. Five independent extractions of all 60 items, every
line-judgement bucketed (`check_error_structure.py`): **79.5% right in all five
passes, 4.0% wrong in all five in exactly the same way.** Only about 16% is
reachable by resampling at all. That 4.0% is dominated by *silent*
under-extraction — of 46 such lines, 30 state a real constraint and are read as
asserting nothing. An item scores only if its whole reading is right, so **only
28 of 60 items have no permanently-wrong line, 46.7%.** That is the ceiling
resampling can reach with this model and this prompt, and the system sits on it
at one call. The budget is not the binding constraint.

Three specific failures. **Under-extraction on unique items** is the largest
bucket — 9 of 20 declared ambiguous at 1×: one constraint missed, count 2–4, and
nothing separates "genuinely ambiguous" from "one constraint short", so no
trigger fires. **The relative-to-absolute collapse** does most damage per
occurrence; when it yields a *plausible* core the system cites a contradiction
that is not there. **`MIN_CORE = 3`** is read off the brief, which states it as
a property of *this* set; a two-statement conflict in the held-out set would be
dissolved by `calib`.

**The paid mechanisms are not clearly positive, and the ablation says so.**
`-vote` at 3× scores **0.539 against the full system's 0.506**, yet the same
removal costs 0.044 at 10×. I did not re-tune on it: the gap is 0.033 against a
0.028 SD in that very cell and reverses sign at the next budget. Both *free*
repairs cost more to remove than either paid one.

**Variance is large and not hidden.** Over 27 runs the per-budget SD is
0.034–0.043 and a single run lands anywhere in 0.417–0.583, so a re-run should
be expected in that range rather than on the mean. Nothing below ~0.05 is real.

## 5. If the notes were written by people

**Survives.** The formal layer never touches text: world model, enumerator,
minimal-core search and both free repairs operate on constraints. The few-shot
example is written in *paraphrases absent from `items.json`* — "Dev starts the
moment Erin finishes, with nothing in between", not the visible set's "Dev is on
the block directly after Erin" — so the extractor sees the semantic category,
not the template. Repair triggers are properties of a solution count, so they
fire on new wording unchanged.

**Degrades gracefully.** The vocabulary is closed, and people would write what it
cannot express — "never on adjacent blocks", soft preferences. Those go inert,
the item looks under-constrained, and the system over-declares ambiguous:
failing honestly and *visibly*, because the count trigger still fires.

**Breaks.** Real notes conflict *in degree* — "I think Priya was on calibration,
though Nadia may have swapped in" — and the architecture rests on hedges carrying
full force, which the brief guarantees and reality does not. `softneg` rests on a
measured property of this generator (no inert line mentions a clock time); "I'll
double-check the 09:00 handover with Meera" breaks it. And `MIN_CORE = 3`
reflects how these items were built — people contradict themselves in pairs. The
symbolic half transfers; the calibrated half is tuned to a generator, and the two
free components producing most of the gain are the two most exposed.

## 6. With a month

1. **Attack extraction recall, not the budget.** The binding constraint is the
   4% of lines wrong identically every time, 30 of 46 of them real constraints
   read as silence, with an oracle ceiling of 1.00 above them. Concretely: a
   two-stage single call that first *classifies* each line into {block, station,
   order, inert} and only then emits a code, targeting both the silent drops and
   the dimension confusions.
2. **Fit the trust order** per code and per context, making the drop a likelihood
   comparison between "the notes contradict" and "this constraint is misread"
   rather than a size threshold.
3. **Make ambiguity a question for the model** — nothing asks it to tell "2
   worlds because the notes allow 2" from "2 worlds because I missed a line".
4. **Generate my own held-out set** from a disjoint phrasing pool. The semantics
   are pinned at 1.0000, so this *measures* transfer instead of arguing about it.
5. **A real MUS enumerator** (QuickXplain), so the citation picks a core by
   calibrated confidence rather than by size.
