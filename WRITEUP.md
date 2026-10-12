# Architecture under a fixed, weak model

**Constraint extraction is model-based.** The weak model reads every line and
translates each into one constraint or into nothing; nothing in the answering
pipeline pattern-matches the notes. Everything after extraction — the kind, the
consistent assignments, the localised contradiction — is symbolic and exact.

| budget | macro | per-kind (u / a / i) | calls/item |
|---|---|---|---|
| **1×** | **0.467 ± 0.036** | 0.42 / 0.38 / 0.60 | 1 – 1 |
| **3×** | **0.506 ± 0.028** | 0.50 / 0.47 / 0.55 | 2 – 3 |
| **10×** | **0.522 ± 0.016** | 0.52 / 0.45 / 0.60 | 3 – 10 |
| no formal layer (`-solver`) | **0.000 ± 0.000** | 0.00 / 0.00 / 0.00 | 1 – 1 |

Three runs each, mean ± population SD, provided scorer. The last row is the
brief's 0.0% reproduced: same model, same call, no symbolic layer. Tables and
per-kind confusion matrices in [ABLATION.md](ABLATION.md); each measurement
below names the `dev/` script that produces it.

## 1. Characterising the model first

**It cannot hold the problem.** One-shot it declares `unique` for every item and
scores 0.0. It does worse than guess: on `B2-001` it put two people on the 07:00
block, and across six items emitted three incompatible shapes for the station
field (`null`, a top-level `stations` map, a station mapped to a *list* of three
people). Ambiguity and contradiction are absent from its output entirely. That
decided the architecture — the model would never count, compare or decide
(`probe_model.py`).

**It is good at one small thing:** translating a single line, and especially at
spotting a line that says nothing (28 of 28 padding lines marked inert). The
strength is local and lexical, so it gets only local, lexical work.

**Its errors are asymmetric and measurable.** A regex reference parser over the
visible pool (`refparse.py`, 100% of 1,137 lines) gave per-line ground truth;
precision per *emitted* code (`calibrate.py`):

| `BETWEEN` 97% | `STATION` 94% | `NOT_STATION` 93% | `EARLIER` 92% |
|---|---|---|---|
| `SBEFORE` 89% | `IMM` 77% | `NOT_BLOCK` 74% | `BLOCK` 71% |

The two *absolute* forms are worst because the signature error is **resolving** a
relative statement into an absolute one — "Rohan is on the block directly after
Meera" came back as `BLOCK Rohan 11:00` seven times. That costs more than the
87% overall suggests: an invented placement kills most of an item's 720 worlds,
a wrong relative one kills few.

**Three of four distractor families are free to get wrong.** Checking whether
over-reading each would change any answer (`check_entailment.py`,
`check_null_family.py`): thwarted wishes read as negatives are **64/64
entailed** — already true in every consistent world; unresolved questions
**31/31**; but past-tense station history **0/25**, always false of the current
rota. One dangerous over-reading, with a crisp signature, so rule 2 of the
prompt leads with it.

**Then I verified the target semantics before building.** Reference parser plus
solver, counting only present-tense definite statements, scores **macro 1.0000**
on all 60 items (`check_semantics.py`) — 0.950 if wishes are included, 0.367 if
past-tense history is. The symbolic layer is correct, so every remaining point
is an extraction problem.

## 2. Why each component exists

**The spine.** One call translates the lines; the solver enumerates all
120 × 6 = 720 worlds. One world is `unique`, two or more `ambiguous` (all
returned), none `inconsistent`, and the citation is a minimal unsatisfiable
subset found by deletion — *definitionally* the scorer's rule, not an
approximation of it.

**`calib`, the calibrated drop (−0.022 live, −0.021 replayed; no model call).** The brief says every
conflicting set here has ≥3 statements and the key agrees (smallest cores: 13 of
size 3, 4 of size 4, 3 of size 5, **none of size 2**). So an extraction whose
smallest core has two statements is provably not reporting a conflict the notes
contain — wrong whichever kind the item is — so there is nothing to lose by
disbelieving one of the two, and the precision table says which.

**`softneg`, soft negatives (−0.033 live, −0.058 replayed; no model call).** A line read as inert that
names exactly one person and one clock time is tried as a negative block claim,
kept only if it removes worlds and leaves one. Safe *because* of the entailment
measurements above. The two free repairs are **additive, not overlapping**
(−0.079 together); I expected overlap and was wrong.

**`mus` (−0.167 live, −0.187 replayed).** Citing every constraining line
instead of a minimal core scores **0.00** on all 20 inconsistent items. Citing more is not safer,
it is disqualifying.

**`repair`.** The world count is a proof of extraction error needing no key, so
budget is spent only where it says something is wrong and only on the lines
responsible: `count > 4` re-reads just the lines read as inert, `count == 0`
re-reads *exactly the core* — three lines of twenty. A paid repair is never a
retry of the item. It does what it is for, even though the macro gain is
modest: the number of items that emit an impossible answer — more than four
assignments — falls from **11 at 1× to 1 at 3× and 10×** (`verify.py`).

**The reply format was a component in disguise.** The dominant failure at full
item length is derailing into commentary and never reaching the rest of the list
— one item answered 2 of 20 lines after a 400-token monologue about what "held
by" means (reasoning is disabled at the API level; it writes prose anyway).
Dictating the reply's literal first characters and banning question marks took
coverage 68% → 89%; shortening `NONE` to `-` took macro 0.300 → 0.317; omitting
inert lines entirely *lost* eight points, recall falling faster than derailment.
Format beat every wording change to the rules.

## 3. What I built and then removed

**Two aggregation designs.** The first merged extractions line by line, and the
curve went non-monotone — 1× 0.450, 3× 0.517, **10× 0.400** — because per-line
majority *drops* a constraint only two passes of five found, and when that is
the constraint a contradiction rests on, a correctly-detected inconsistent item
silently becomes satisfiable (inconsistent fell 0.60 → 0.30). The second voted
on whole verdicts. Replaying one three-pass log through every rule with the
extraction held fixed (`tune_aggregation.py`), **every way of combining three
extractions lost to the best single one**: merge 0.483, verdict-majority 0.517,
union 0.517, intersection 0.383, against individual passes of 0.533 / 0.400 /
0.550. The errors are systematic, not independent noise, so averaging reinforces
them. What works is *selection* — discard the candidates that are provably wrong
(count > 4) and keep the first survivor: 0.567 there, and 0.533 at both k=3 and
k=5 on an independent five-pass log against a 0.453 single-pass average, so the
gain saturates at three passes.

Two further corrections, from watching 3× come in below 1× again. A
contradiction now wins only if it was the first conclusion or a second candidate
reaches the same core — an under-constrained pass re-sampled into an
unsatisfiable one looked like progress, trading four true inconsistent items for
four wrong `unique` ones. And the core is re-read twice, the original reading
surviving unless the re-reads agree against it. 3×: 0.450 → 0.517.

**Restatement agreement, removed.** The scorer rejects two citations that
normalise identically, so I built a component to avoid the trap, then measured
it: **no two body lines in the visible set normalise identically**
(`check_restatements.py`). The "restatements" are re-phrasings, and a core may
cite either; catching them needs semantic matching, and the obvious symbolic
proxy (same names mentioned) also groups "A is earlier than B" with "A is next
to B". Removed rather than guessed at.

**`recover` and `strict`, kept but near-dead.** Replay puts both at −0.004, and
the live 1× table has `-strict` a fraction *above* full — both are inside the
noise, i.e. no measurable effect either way. Most of what `recover` was for
proved fixable upstream: the strict parser was discarding 37 codes a run over a
trailing `?`. I report them at roughly zero rather than quietly deleting them,
and keep `strict` on anyway, because refusing to repair a hallucinated name is
a property I want on a held-out set where the model may invent more of them.

**An honest non-choice.** `n=3` sampling returns three completions in one HTTP
request, which the counting proxy would see as one call — self-consistency at
1×, within the letter of the rule. I did not do it. Three samples is three
samples.

## 4. Where it breaks, and why the curve is flat

The plateau has a number. Five independent extractions of all 60 items, every
line-judgement bucketed (`check_error_structure.py`, 1,137 judgements):
**79.5% right in all five passes, and 4.0% wrong in all five in exactly the same
way**; only 14.7% mixed and 1.8% inconsistently-wrong are reachable by
resampling at all.

That 4.0% is a wall, dominated by *silent* under-extraction: of 46 such lines,
30 are read as asserting nothing when they state a real constraint (12
betweenness, 7 negative-block, 6 negative-station, 5 adjacency). An item scores
only if its whole reading is right, so **only 28 of 60 items have no
permanently-wrong line — 46.7%.** That is the ceiling resampling can reach with
this model and this prompt, and the system is already sitting on it at 1×. The
budget is not the binding constraint.

Three specific failures. **Under-extraction on unique items** is the largest
bucket, 7–8 of 20 declared ambiguous: one constraint missed, count 2–4, and
nothing in the formal layer separates "genuinely ambiguous" from "one constraint
short", so no trigger fires. **The relative-to-absolute collapse** does the most
damage per occurrence; when it yields a *plausible* core the system cites a
contradiction that is not there. **`AMBIG_MAX = 4` and `MIN_CORE = 3`** are read
off the brief, which states the second as a property of *this* set; a
two-statement conflict in the held-out set would be dissolved by `calib`.

**The paid mechanisms are not clearly positive, and the ablation says so.**
`-vote` at 3× scores **0.539 against the full system's 0.506** — switching off
re-extraction-and-selection *improves* three-call performance — while at ten
calls the same removal costs 0.044. `-repair` costs 0.017 at 3× and 0.016 at
10×. I have not re-tuned the trigger on this: the 3× gap is 0.033 against a
0.028 standard deviation in that very cell, it reverses sign at the next
budget, and fitting a budget-dependent threshold to 60 items with that much
spread is how a system stops generalising. The two numbers do support the
conclusion above — at three calls the paid mechanisms are roughly
interchangeable and neither is clearly worth its budget, because the errors
they chase are the systematic ones that resampling cannot reach. By contrast
the two *free* repairs cost 0.022 and 0.033 to remove, more than either paid
mechanism, for no calls at all.

**Variance is large and not hidden.** The same configuration moves ±0.04 to 0.10
macro between runs, and individual passes of one item range 0.400–0.550. Every
ablation number is a three-run mean with spread, and the symbolic arms are
*additionally* measured by replay over four fixed extractions, so those
comparisons carry no sampling noise. No single-run difference below ~0.05 is a
real effect — which is also why the `-vote` result above is reported rather than
acted on.

## 5. If the notes were written by people

**Survives.** The formal layer never touches text: world model, enumerator,
minimal-core search, `calib` and `softneg` all operate on constraints. The
few-shot example is written in *paraphrases absent from `items.json`* — "Dev
starts the moment Erin finishes, with nothing in between", not "Dev is on the
block directly after Erin" — so the extractor sees the semantic category, not
the template; the rules are stated as categories ("anything in the past", "a
request that was refused"). The repair triggers are properties of a solution
count, so they fire on new wording unchanged.

**Degrades gracefully.** The vocabulary is closed, and people would write what
it cannot express — "never on adjacent blocks", soft preferences. Those go
inert, the item looks under-constrained, and the system over-declares ambiguous:
failing honestly, and visibly, because the count trigger still fires.

**Breaks.** Real notes conflict *in degree* — "I think Priya was on calibration,
though Nadia may have swapped in" — and the whole architecture rests on hedges
carrying full force, which the brief guarantees and reality does not.
`softneg`'s safety rests on a measured property of this generator, that no inert
line mentions a clock time; "I'll double-check the 09:00 handover with Meera"
breaks it immediately and it would have to go. And `MIN_CORE = 3` is a property
of how these items were built, where people contradict themselves in pairs. The
symbolic half transfers, the calibrated half is tuned to a generator, and the
two free components producing most of the gain are the two most exposed — I
would expect a real drop, led by `calib`.

## 6. With a month

1. **Attack extraction recall, not the budget.** The binding constraint is the
   4% of lines wrong identically every time, 30 of 46 of them constraints read
   as silence, with an oracle ceiling of 1.00 above them. Concretely: a
   two-stage single call that first *classifies* each line into {block, station,
   order, inert} and only then emits a code, targeting both the silent drops and
   the dimension confusions (`block ← imm` 7, `imm ← before` 6, `block ←
   between` 6).
2. **Fit the trust order** per code *and per context*, making the drop a
   likelihood comparison between "the notes contradict" and "this constraint is
   misread" rather than the `MIN_CORE` threshold.
3. **Make ambiguity a question for the model.** Nothing asks it to tell "2 worlds
   because the notes allow 2" from "2 worlds because I missed a line" — the
   largest remaining bucket, and "does any line fix which of Meera and Rohan is
   earlier?" is answerable by a weak model.
4. **Generate my own held-out set.** The semantics are pinned at 1.0000, so I can
   generate from a disjoint phrasing pool and *measure* transfer rather than
   argue about it — the only test that separates phrasing-independence from
   phrasing-luck, and a direct check on the three breakages above.
5. **A real MUS enumerator** (QuickXplain), so the citation can choose a core by
   calibrated confidence rather than by size.
