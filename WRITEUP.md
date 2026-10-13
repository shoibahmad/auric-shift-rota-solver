# Architecture under a fixed, weak model

**Constraint extraction is model-based.** The model turns each line of notes into
one constraint or into nothing. Nothing in the answering pipeline pattern-matches
the notes; everything after extraction is symbolic and exact.

| budget | macro (n=9) | range | u / a / i |
|---|---|---|---|
| **1×** | **0.469 ± 0.041** | 0.417–0.533 | 0.42 / 0.38 / 0.60 |
| **3×** | **0.504 ± 0.043** | 0.450–0.583 | 0.50 / 0.47 / 0.55 |
| **10×** | **0.504 ± 0.034** | 0.450–0.550 | 0.52 / 0.45 / 0.60 |
| no formal layer | **0.000** | — | 0.00 / 0.00 / 0.00 |

Nine runs per budget; the last row is the brief's 0.0% reproduced. **3× and 10×
are equal to three decimals.** Each figure is reproduced by one `dev/` script;
tables in [ABLATION.md](ABLATION.md).

## 1. Characterising the model first

**It cannot hold the problem.** One-shot it declares `unique` for everything and
scores 0.0; it put two people on one block and emitted three incompatible JSON
shapes for the station field. It has no representation of ambiguity or
contradiction at all, so it is never asked to count, compare or decide. **It is
good at one thing:** translating a single line, especially spotting one that says
nothing — 28 of 28 padding lines.

**Its errors are asymmetric.** A regex reference parser (100% of 1,137 visible
lines) gave per-line ground truth: precision per *emitted* code is 87% overall but
spans `BETWEEN` 97% down to `BLOCK` 71%. The signature error is **resolving a
relative statement into an absolute one**, and an invented placement kills most of
an item's 720 worlds where a wrong relative one kills few. Three of four distractor
families are free to over-read: thwarted wishes read as negatives are **64/64
entailed**, unresolved questions 31/31, but past-tense station history **0/25**,
always false. One dangerous over-reading, so the rules lead with it — worth 0.133.

**I verified the target semantics before building.** That parser plus the solver,
counting only present-tense definite statements, scores **macro 1.0000** on all 60
items — so every remaining point is an extraction problem.

## 2. Why each component exists

**The spine.** One call translates the lines; the solver enumerates all 720
worlds. One world is `unique`, two or more `ambiguous` (all returned), none
`inconsistent`. The citation is a minimal unsatisfiable subset found by deletion —
*definitionally* the scorer's rule, not an approximation of it. Citing every
constraining line instead scores **0.00** on all 20 inconsistent items (`mus`,
−0.167); citing more is disqualifying.

**Two free repairs, worth more than either paid one.** `calib` (−0.022): every
real conflicting set has ≥3 statements — **none of size 2** — so a two-statement
core is provably not a conflict the notes contain and is wrong whichever kind the
item is. Nothing is lost by disbelieving one, and the precision table says which.
`softneg` (−0.033) is the mirror: a line read as inert naming one person and
one clock time is tried as a negative block claim, kept only if it removes worlds
and leaves one. They are **additive** (−0.079); I expected overlap and was wrong.

**`repair`.** The world count proves extraction error with no key: `>4` re-reads
only the lines read as inert, `0` re-reads *exactly the core*. Impossible answers
fall from **11 at 1× to 1 at 3×**. **Reply format** was a component in disguise —
the model derails into commentary mid-list, and dictating the reply's first
characters took coverage **68% → 89%**.

## 3. What I built and then removed

**Two aggregation designs.** Per-line vote merging made the curve non-monotone
(10× fell to 0.400) by dropping constraints only a minority of passes found,
dissolving correctly-detected contradictions; verdict-majority voting replaced it
and was also wrong. Replaying one three-pass log with the extraction held fixed,
**every way of combining three extractions lost to the best single one**
(0.383–0.517 vs passes of 0.533 / 0.400 / 0.550) — the errors are systematic, so
averaging reinforces them. What works is *selection*: discard provably-wrong
candidates, keep the first survivor (0.567, saturating at three).

**Restatement agreement, removed** after measuring that the scorer trap it
guarded cannot fire. **`recover`/`strict`, near-dead** (−0.004), reported at zero
rather than deleted.

## 4. Where it breaks, and why the curve is flat

Five extractions of all 60 items, every line-judgement bucketed:
**79.5% right in all five, 4.0% wrong in all five identically** — only ~16% is
reachable by resampling, and that 4.0% is mostly *silent* under-extraction (30 of
46 are real constraints read as nothing). An item needs its whole reading right, so
**only 28 of 60 items have no permanently-wrong line (46.7%)** — the ceiling
resampling can reach, and the system already sits on it at one call.

**Under-extraction on unique items** is the largest bucket (9 of 20 declared
ambiguous at 1×): nothing separates "genuinely ambiguous" from "one constraint
short", so no trigger fires. **`MIN_CORE = 3`** is read off the brief as a property
of *this* set; a two-statement conflict held out would be dissolved by `calib`.
Neither paid mechanism is clearly positive, and with SD 0.034–0.043 over 27 runs
nothing below ~0.05 is real.

## 5. If the notes were written by people

**Survives.** The formal layer never touches text. The few-shot example uses
*paraphrases absent from `items.json`* — "starts the moment Erin finishes", not the
visible set's "directly after" — so the extractor sees the semantic category, not
the template, and repair triggers are properties of a solution count. **Degrades
gracefully:** the vocabulary is closed, so what it cannot express goes inert and
the item over-declares ambiguous — failing honestly and *visibly*.

**Breaks.** Real notes conflict *in degree*, and the architecture rests on hedges
carrying full force, which the brief guarantees and reality does not. `softneg`
rests on a measured property of this generator — no inert line mentions a clock
time — that one realistic sentence would break, and people contradict themselves in
pairs, killing `MIN_CORE = 3`. The symbolic half transfers; the two free components
producing most of the gain are the two most exposed.

## 6. With a month

**Attack extraction recall, not the budget** — that 4% is the binding constraint
and the oracle ceiling above it is 1.00; a two-stage call classifying each line
before emitting a code targets the silent drops and the dimension confusions.
**Fit the trust order** per code and context, making the drop a likelihood
comparison rather than a size threshold. **Make ambiguity a question for the
model**, which nothing currently asks. And **generate my own held-out
set** from a disjoint phrasing pool, to *measure* transfer.
