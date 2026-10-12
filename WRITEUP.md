# Architecture under a fixed, weak model

**Constraint extraction is model-based.** The weak model reads every line of
every item and translates each one into a constraint, or into nothing. No part
of the answering pipeline pattern-matches the notes. Everything after
extraction — deciding the kind, enumerating the consistent assignments,
localising a contradiction — is symbolic and exact.

## 1. Characterising the model first

I spent the first hour measuring the model rather than prompting it, because
the two things I needed to know were what it *cannot* do and what it is
*already* good at.

**It cannot hold the problem.** Asked for the whole answer in one shot
(`--drop solver`, which is the ablation arm for "no formal layer") it declares
`unique` for every item, and scores 0.0 — the brief's figure, reproduced. It
does worse than guess: on `B2-001` it put two people on the 07:00 block, and
across six items it emitted three mutually incompatible JSON shapes for the
station field (`"station": null`, a top-level `stations` map, and a station
mapped to a *list* of three people). There is no representation of ambiguity or
contradiction anywhere in its output. That is not a prompt that needs fixing;
it is a model that cannot carry a permutation constraint, and it set the whole
design: the model would never be asked to count, compare or decide.

**It is good at one small thing.** Translating a *single line* into a formal
code, it is reliable — and specifically, it is near-perfect at recognising a
line that says nothing. Of 28 pure-padding lines in the first probe it marked
28 as `NONE`. The weak model's strength is local and lexical, so the
architecture gives it only local, lexical work.

**Its errors are not symmetric, and the asymmetry is measurable.** I wrote a
regex reference parser over the visible phrasing pool (`dev/refparse.py`,
100% coverage of all 1,172 body lines) purely to get ground truth per line, and
used it to measure precision per emitted code (`dev/calibrate.py`, 60 items):

| emitted code | precision | | emitted code | precision |
|---|---|---|---|---|
| `BETWEEN` | 97% | | `SBEFORE` | 89% |
| `STATION` | 94% | | `IMM` (adjacent) | 77% |
| `NOT_STATION` | 93% | | `NOT_BLOCK` | 74% |
| `EARLIER` | 92% | | `BLOCK` | 71% |

Overall 87%. The shape is intelligible: the two *absolute* forms are the least
reliable, because the model's signature error is to **resolve** a relative
statement into an absolute one. "Rohan is on the block directly after Meera"
came back as `BLOCK Rohan 11:00` seven times. That matters far more than the
87% suggests, because an invented absolute placement eliminates most of the
720 worlds while a wrong relative one eliminates few. This table is the input
to the one component that helps most, and it is the reason that component
exists at all.

**Three of the four distractor families are free to get wrong.** Using the
reference parser and the solver together, I checked whether each inert family
*would* change an answer if the model over-read it (`dev/check_entailment.py`,
`dev/check_null_family.py`):

- thwarted wishes ("lobbied for 11:00 without success") read as a negative:
  **64/64 entailed** by the real constraints — i.e. true in every consistent
  world anyway;
- unresolved questions ("nobody could remember whether") read as a negative:
  **31/31 entailed**;
- **past-tense station history ("last month Priya was on intake"): 0/25.**
  Always false of the current rota.

So there is exactly one dangerous over-reading, and it has a crisp linguistic
signature. Rule 2 of the prompt leads with it, and the ablation measures what
dropping it costs.

Finally I confirmed the target semantics before building anything: with the
reference parser feeding the solver and *only* the present-tense definite
statements treated as constraints, the oracle scores **macro 1.0000** on all 60
items (`dev/check_semantics.py`). Including the wish family drops it to 0.950;
including past-tense history drops it to 0.367. That told me the symbolic layer
was correct and that every remaining point was an extraction problem — which
is where all the subsequent effort went.

## 2. Why each component exists

The spine is: **one call translates the lines; the solver does the rest.** With
5 people, 5 blocks and 3 stations an item has 120 × 6 = 720 possible worlds, so
the enumerator is exhaustive by construction. `count == 1` is unique, `count ≥ 2`
is ambiguous and returns all of them, `count == 0` is inconsistent, and the
citation is a minimal unsatisfiable subset found by deletion — which is
*definitionally* the scorer's rule, not an approximation of it.

Two components come from reading the brief as a specification rather than as
prose.

**`calib` — the calibrated drop.** The brief says every conflicting set on this
set has at least three statements, and the key confirms it (smallest cores:
thirteen of size 3, four of size 4, three of size 5; **none of size 2**). So an
extraction whose smallest core has two statements is *provably not reporting a
conflict the notes contain* — the answer built on it is wrong whichever kind the
item really is, so there is nothing to lose by disbelieving one of the two. The
calibration table above says which: drop the one from the least reliable code
kind. On the visible set 8 of 20 such cases arose and 5 were truly ambiguous
items destroyed by one invented constraint. **This is the single largest win in
the system and it costs no model call** (+0.05 to +0.13 macro depending on the
run).

**`softneg` — soft negatives.** The mirror image, also free. A line read as
asserting nothing that nonetheless names exactly one person and exactly one
clock time is tried as a negative block claim, and kept only if it removes
worlds and leaves at least one. It is safe precisely because of the entailment
measurements above: no padding line in this task mentions a clock time, and the
two inert families that do are entailed as negatives anyway. +0.05 macro on a
fixed extraction.

**`mus` — minimal-core citation.** Not optional in any sense: with it the
inconsistent stratum scores 0.45, and citing every constraining line instead
scores **0.00**. Citing more is not safer; it is disqualifying.

**`repair` and `vote` — what the extra budget buys.** The world count is a
proof of extraction error that needs no key, so budget is spent only where the
count says something is wrong, and only on the lines responsible:

- `count > 4` — a constraint was missed, and it is in a line read as `NONE`.
  Re-read *only those lines*, typically twelve of twenty.
- `count == 0` — either a real contradiction or an invented constraint, and if
  invented it is in the core. Re-read *exactly the core*, typically three
  lines. If the model re-reads all three and stands by them, that is the
  strongest available evidence the contradiction is in the notes, and the
  system stops and cites it.
- otherwise — extract again and vote.

A repair is never a retry of the item. It is a re-read of the handful of lines
the solver has just proved are carrying the error.

**The reply format is a component in disguise.** The model's dominant failure
at full item length is not a wrong code — it is derailing into commentary
part-way down the list and never reaching the rest of it (reasoning is disabled
at the API level and it writes prose regardless). On one item it answered 2 of
20 lines after a 400-token monologue about what "held by" means. Dictating the
literal first characters of the reply and banning question marks took line
coverage from 68% to 89%; replacing the word `NONE` with `-` to cut output
tokens took macro from 0.300 to 0.317. Omitting inert lines entirely — the
shortest output of all — *lost* five points (0.233), because recall fell faster
than derailment did. Format was worth more than any wording change to the rules.

## 3. What I built and then removed

**Per-line vote merging, as the arbiter.** The first budget loop merged repeated
extractions line by line and re-solved the merge. The curve came out
**non-monotone — 1× 0.450, 3× 0.517, 10× 0.400** — and the confusion matrix said
exactly why: inconsistent fell from 0.60 at 3× to 0.30 at 10×. Per-line majority
*drops* a constraint that only two passes of five found, and when that is the
constraint a contradiction rests on, a correctly-detected inconsistent item
quietly becomes satisfiable. Extra budget was dissolving the system's best
answers. The fix was to turn each extraction into a *finished verdict* and vote
on verdicts: a verdict a majority of passes reached independently cannot be
dissolved that way. The line-by-line merge is still offered as one more
candidate — it beats any single pass when passes differ by noise — but it no
longer overrides.

**Restatement agreement.** The scorer rejects a cited set containing two
citations that normalise to the same string, and warns that a restatement
normalises to the same string as the line it restates. I built the component to
avoid that trap, then measured it: **no two body lines in the visible set
normalise identically** (`dev/check_restatements.py`). The "restatements" are
re-phrasings — "Put Meera between Tomas and Rohan" and "Whichever way round
Tomas and Rohan are, Meera is between them" are two statements, and a core may
legitimately cite either. Catching those needs semantic matching, and the
obvious symbolic proxy (same set of names mentioned) also groups "A is earlier
than B" with "A is next to B". Removed rather than guessed at.

**`recover`, kept but honestly near-dead.** It re-parses codes the strict
parser rejected, when the item is under-constrained. It fires on 3 items in 60
and moves the score by ~0. Most of what it was built for turned out to be fixed
better upstream: the strict parser was discarding 37 codes per run over a
trailing `?`, and salvaging those at parse time made the component redundant.
I report it at roughly zero rather than quietly deleting it.

**An honest non-choice.** `n=3` sampling would return three completions in *one*
HTTP request, which the graders' proxy would count as one call — self-consistency
at 1×, within the letter of the budget rule. I did not do it. The rule is about
how much model work an answer may use, and three samples is three samples.

## 4. Where it breaks

**Under-extraction on unique items is the largest single bucket.** At 1×, 8 of
20 unique items are declared ambiguous: the model missed one constraint, the
world count is 2–4, and nothing in the formal layer can tell "genuinely
ambiguous" from "one constraint short". This is the plateau, and it is not a
plateau of the solver — the oracle gets 20/20 — it is the extraction recall
ceiling showing through. It is also why 3× helps: the `count > 4` trigger
catches the *badly* under-extracted items, but an item sitting at exactly 2
worlds when it should be 1 looks perfectly legitimate and is never repaired.

**The relative-to-absolute collapse is the costliest error class.** `BLOCK` at
71% precision does more damage than anything else, because one invented
placement eliminates ~500 of 720 worlds. `calib` cleans this up only when it
produces a too-small core; when it produces a *plausible* core the system cites
a contradiction that is not there.

**Two numbers I am treating as soft.** `AMBIG_MAX = 4` and `MIN_CORE = 3` are
read straight off the brief, and the brief states the second as a property of
*this* set. If the held-out set contains a two-statement conflict, `calib` will
dissolve it, and that is the component most likely to transfer worst — which is
precisely why it is a separately-switchable arm in the ablation.

**Run-to-run variance is real.** At `temperature=1.0` the same configuration
moves ±0.05 macro between runs; the 1× figures here came in at 0.450 and 0.467
on two consecutive runs of identical code. Every number in [ABLATION.md](ABLATION.md)
is a mean over three runs with the spread reported, and no single-run difference
smaller than about 0.05 should be read as a real effect.

## 5. If the notes were written by people

This is the question the design is most exposed to, and I want to be precise
about which parts survive.

**What survives.** The formal layer is phrasing-independent: the world model,
the enumerator, the minimal-core search, `calib` and `softneg` all operate on
constraints, never on text. The few-shot example is deliberately written in
*paraphrases* that do not appear in `items.json` — "Dev starts the moment Erin
finishes, with nothing in between", not "Dev is on the block directly after
Erin" — so the extractor is being shown the semantic category rather than the
template, and the rules are stated as categories ("anything in the past", "a
request that was refused") rather than as surface forms.

**What degrades gracefully.** The constraint vocabulary is closed, and real
humans would write things it cannot express: "Priya and Rohan are never on
adjacent blocks", "someone has to cover intake before the delivery at eleven",
soft preferences, or a statement whose scope is genuinely unclear. Those become
`NONE`, the item looks under-constrained, and the system over-declares
ambiguous — which the brief correctly calls failing honestly. The count-based
repair trigger still fires, so the failure is visible rather than silent.

**What breaks.** Three things, in order of severity. First, real notes contain
statements that *conflict in degree* rather than flatly — "I think Priya was on
calibration, though Nadia may have swapped in" — and the whole architecture
rests on hedges carrying full force, which the brief guarantees and reality
does not. Second, `softneg`'s safety rests on a measured property of this
generator (no padding line mentions a clock time); a human writing "I'll
double-check the 09:00 handover with Meera" breaks it immediately, and it would
need to go. Third, `MIN_CORE = 3` is a property of how these items were
constructed; humans contradict themselves in pairs all the time.

The honest summary: the symbolic half transfers, the calibration half is tuned
to a generator, and the two free components that produce most of the gain are
the two most exposed. I would expect a real drop on human-written notes, led by
`calib`.

## 6. With a month

1. **Attack extraction recall, not the budget.** The plateau is per-line recall
   on unique items, and the oracle proves the ceiling is 1.00. The highest-value
   work is making one call extract more of the lines correctly — not making more
   calls. Concretely: a two-stage single call that first *classifies* each line
   into {block, station, order, inert} and only then emits the code, which
   directly targets the dimension confusions (`block ← imm` 7, `imm ← before` 6,
   `block ← between` 6).
2. **Replace the hand-set trust order with a fitted one.** `TRUST` is eight
   integers read off one table. With a month I would fit per-code *and
   per-context* reliability on generated data and make the drop decision a
   likelihood comparison between "the notes contradict" and "this constraint is
   misread", instead of the `MIN_CORE` threshold.
3. **Make ambiguity a first-class question for the model.** Nothing currently
   asks it to distinguish "2 worlds because the notes allow 2" from "2 worlds
   because I missed a line", and that is the biggest remaining bucket. A
   targeted question — "does any line fix which of Meera and Rohan is earlier?"
   — is answerable by a weak model and would be worth more per call than a
   re-read.
4. **Generate my own held-out set.** I have the semantics pinned to 1.0000, so I
   can generate items with a disjoint phrasing pool and measure transfer
   directly rather than arguing about it, which is the only way to tell
   phrasing-independence from phrasing-luck.
5. **A proper MUS enumerator.** `all_muses` sweeps deletion from 24 starting
   points; QuickXplain with proper recursion would give all cores cheaply and
   let the citation choose by calibrated confidence rather than by size.

## Reproducing the numbers

All figures come from the provided scorer against `visible_key.json`.
Per-budget curve and ablation: three runs per cell, mean ± population standard
deviation, in [ABLATION.md](ABLATION.md), regenerated by:

```bash
python3 ablate.py --items items.json --key visible_key.json \
    --budgets 1x,3x,10x --runs 3 --outdir runs/ablation
```

Characterisation figures come from `dev/`, one script per claim; those marked
"on a fixed extraction" are replays of one recorded run through a changed
symbolic layer (`dev/replay.py`), which removes sampling noise from the
comparison entirely. `dev/check_model_sensitivity.py` demonstrates the
dependence on the model's output: with every code blanked the system scores
**0.0000** and all 60 answers change; with polarities flipped, 0.0500.
