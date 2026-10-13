# Architecture under a fixed, weak model

**Constraint extraction is model-based.** The model turns each line of notes
into one constraint or into nothing. Nothing in the answering pipeline
pattern-matches the notes; everything after extraction is symbolic and exact.

| budget | macro (n=9) | range | u / a / i | calls/item |
|---|---|---|---|---|
| **1×** | **0.469 ± 0.041** | 0.417–0.533 | 0.42 / 0.38 / 0.60 | 1 |
| **3×** | **0.504 ± 0.043** | 0.450–0.583 | 0.50 / 0.47 / 0.55 | 2–3 |
| **10×** | **0.504 ± 0.034** | 0.450–0.550 | 0.52 / 0.45 / 0.60 | 2–10 |
| no formal layer | **0.000** | — | 0.00 / 0.00 / 0.00 | 1 |

Nine runs per budget. The last row is the brief's 0.0% reproduced. **3× and 10×
are equal to three decimals** — the seven calls after the third buy nothing. §4
says why. Details and the full ablation: [ABLATION.md](ABLATION.md); each claim
names the `dev/` script behind it.

## 1. Characterising the model first

**It cannot hold the problem.** One-shot it declares `unique` for everything and
scores 0.0; it put two people on one block and emitted three incompatible JSON
shapes for the station field. Ambiguity and contradiction are absent entirely,
so the model would never count, compare or decide. **It is good at one thing:**
translating a single line, especially recognising one that says nothing — 28 of
28 padding lines.

**Its errors are asymmetric.** A regex reference parser (`refparse.py`, 100% of
1,137 visible lines) gave per-line ground truth. Precision per *emitted* code is
87% overall but spans `BETWEEN` 97% down to `BLOCK` 71%: the signature error is
**resolving a relative statement into an absolute one**, and an invented
placement kills most of an item's 720 worlds where a wrong relative one kills
few.

**Three of four distractor families are free to over-read.** Thwarted wishes
read as negatives are **64/64 entailed** — already true in every consistent
world; unresolved questions 31/31; but past-tense station history **0/25**,
always false. One dangerous over-reading, so the prompt's rules lead with it —
worth 0.133.

**I verified the target semantics before building.** Reference parser plus
solver, counting only present-tense definite statements, scores **macro 1.0000**
on all 60 items. The symbolic layer is correct, so every remaining point is an
extraction problem.

## 2. Why each component exists

**The spine.** One call translates the lines; the solver enumerates all 720
worlds. One world is `unique`, two or more `ambiguous` (all returned), none
`inconsistent`. The citation is a minimal unsatisfiable subset found by deletion
— *definitionally* the scorer's rule, not an approximation of it.

**`calib`** (−0.022, no model call). Every real conflicting set has ≥3
statements — **none of size 2**. So an extraction whose smallest core has two is
provably not reporting a conflict the notes contain, and is wrong whichever kind
the item is; there is nothing to lose by disbelieving one, and the precision
table says which.

**`softneg`** (−0.033, no model call) is the mirror: a line read as inert naming
one person and one clock time is tried as a negative block claim, kept only if
it removes worlds and leaves one. The two are **additive** (−0.079 together); I
expected overlap and was wrong.

**`mus`** (−0.167). Citing every constraining line rather than a minimal core
scores **0.00** on all 20 inconsistent items. Citing more is disqualifying.

**`repair`.** The world count proves extraction error with no key: `>4` re-reads
only the lines read as inert, `0` re-reads *exactly the core*. Impossible answers
fall from **11 at 1× to 1 at 3×**. **Reply format** was a component in disguise:
the dominant failure is derailing into commentary mid-list, and dictating the
reply's first characters took coverage **68% → 89%** — more than any wording
change to the rules.

## 3. What I built and then removed

**Two aggregation designs.** Per-line vote merging made the curve non-monotone
(10× fell to 0.400) by dropping constraints only a minority of passes found,
dissolving correctly-detected contradictions; verdict-majority voting replaced it
and was also wrong. Replaying one three-pass log through every rule with the
extraction fixed, **every way of combining three extractions lost to the best
single one** (0.383–0.517 vs passes of 0.533 / 0.400 / 0.550) — the errors are
systematic, so averaging reinforces them. What works is *selection*: discard
provably-wrong candidates, keep the first survivor (0.567, saturating at three).

**Restatement agreement, removed** — built to dodge the scorer's
duplicate-citation trap, then measured that no two visible body lines normalise
identically, so it cannot fire. **`recover`/`strict`, near-dead** (−0.004,
inside the noise), reported at zero rather than quietly deleted. **An honest
non-choice:** `n=3` sampling would give self-consistency at 1× within the letter
of the budget rule. Three samples is three samples.

## 4. Where it breaks, and why the curve is flat

Five independent extractions of all 60 items, every line-judgement bucketed:
**79.5% right in all five, 4.0% wrong in all five identically.** Only ~16% is
reachable by resampling. That 4.0% is mostly *silent* under-extraction — 30 of
46 are real constraints read as nothing. An item needs its whole reading right,
so **only 28 of 60 items have no permanently-wrong line (46.7%)** — the ceiling
resampling can reach, and the system sits on it at one call. The budget is not
the binding constraint.

**Under-extraction on unique items** is the largest bucket (9 of 20 declared
ambiguous at 1×): nothing separates "genuinely ambiguous" from "one constraint
short", so no trigger fires. **`MIN_CORE = 3`** is read off the brief as a
property of *this* set; a two-statement conflict in the held-out set would be
dissolved by `calib`. **The paid mechanisms are not clearly positive:** `-vote`
at 3× scores 0.539 against the full system's 0.506, yet costs 0.044 at 10× — I
report it rather than re-tune on a 0.033 gap against a 0.028 SD that reverses
sign. **Variance is large:** over 27 runs, SD 0.034–0.043 and single runs
anywhere in 0.417–0.583, so nothing below ~0.05 is real.

## 5. If the notes were written by people

**Survives.** The formal layer never touches text. The few-shot example uses
*paraphrases absent from `items.json`* — "Dev starts the moment Erin finishes,
with nothing in between", not the visible set's "directly after" — so the
extractor sees the semantic category, not the template; rules are stated as
categories; repair triggers are properties of a solution count.

**Degrades gracefully.** The vocabulary is closed, so what it cannot express
("never on adjacent blocks", soft preferences) goes inert and the item
over-declares ambiguous — failing honestly and *visibly*.

**Breaks.** Real notes conflict *in degree*, and the architecture rests on hedges
carrying full force, which the brief guarantees and reality does not. `softneg`
rests on a measured property of this generator (no inert line mentions a clock
time) that one realistic sentence would break. And people contradict themselves
in pairs, killing `MIN_CORE = 3`. The symbolic half transfers; the calibrated
half is tuned to a generator, and the two free components producing most of the
gain are the two most exposed.

## 6. With a month

1. **Attack extraction recall, not the budget** — the binding constraint is that
   4%, with an oracle ceiling of 1.00 above it. A two-stage single call that
   classifies each line {block, station, order, inert} before emitting a code,
   targeting the silent drops and the dimension confusions.
2. **Fit the trust order** per code and context, making the drop a likelihood
   comparison rather than a size threshold.
3. **Make ambiguity a question for the model** — nothing asks it to tell "2
   worlds because the notes allow 2" from "2 worlds because I missed a line".
4. **Generate my own held-out set** from a disjoint phrasing pool, to *measure*
   transfer instead of arguing about it.
5. **A real MUS enumerator** (QuickXplain), picking a core by confidence.
