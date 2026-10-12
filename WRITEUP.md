# Architecture under a fixed, weak model

**Constraint extraction is model-based.** The weak model reads every line of
every item and translates each into one constraint, or into nothing. No part of
the answering pipeline pattern-matches the notes. Everything after extraction —
deciding the kind, enumerating the consistent assignments, localising a
contradiction — is symbolic and exact.

| budget | macro exact match | per-kind (u / a / i) | calls per item |
|---|---|---|---|
| **1×** | **0.467 ± 0.036** | 0.42 / 0.38 / 0.60 | 1 – 1 |
| **3×** | **0.506 ± 0.028** | 0.50 / 0.47 / 0.55 | 2 – 3 |
| **10×** | **0.522 ± 0.016** | 0.52 / 0.45 / 0.60 | 3 – 10 |
| no formal layer (`-solver`) | **0.000 ± 0.000** | 0.00 / 0.00 / 0.00 | 1 – 1 |

Three runs per row, mean ± population SD, scored with the provided `score.py`
against `visible_key.json`. The bottom row is the brief's 0.0% baseline,
reproduced: the same model, the same call, no symbolic layer. Full ablation and
the per-kind confusion matrices: [ABLATION.md](ABLATION.md). Every
characterisation figure below comes from one script in `dev/`, named inline.

The curve's shape is the honest part of this submission: **most of the result
is already there at one call per item**, and the remaining budget buys about
five points. §4 explains why, with the measurement that bounds it.

## 1. Characterising the model first

I spent the first stretch measuring the model rather than prompting it, because
the two things worth knowing were what it cannot do and what it is already good
at.

**It cannot hold the problem.** Asked for the whole answer in one shot — the
`-solver` ablation arm — it declares `unique` for every item and scores **0.0**,
reproducing the brief's figure. It does worse than guess: on `B2-001` it put two
people on the 07:00 block, and across six items it emitted three mutually
incompatible shapes for the station field (`"station": null`, a top-level
`stations` map, and a station mapped to a *list* of three people). Ambiguity and
contradiction are absent from its output entirely. That is not a prompt that
needs fixing, and it decided the architecture: the model would never be asked to
count, compare or decide.

**It is good at one small thing.** Translating a *single line* into a formal
code it is reliable, and it is near-perfect at recognising a line that says
nothing: 28 of 28 pure-padding lines marked inert in the first probe
(`dev/probe_model.py`). The strength is local and lexical, so the architecture
gives it only local, lexical work.

**Its errors are asymmetric, and the asymmetry is measurable.** I wrote a regex
reference parser over the visible phrasing pool (`dev/refparse.py`, 100%
coverage of all 1,137 body lines) solely to get per-line ground truth, and used
it to measure precision per *emitted* code — given that the model wrote this
code, how often the line says that (`dev/calibrate.py`, 60 items):

| | | | | |
|---|---|---|---|---|
| `BETWEEN` 97% | `STATION` 94% | `NOT_STATION` 93% | `EARLIER` 92% | |
| `SBEFORE` 89% | `IMM` 77% | `NOT_BLOCK` 74% | `BLOCK` 71% | overall **87%** |

The shape is intelligible rather than arbitrary. The two *absolute* forms are
least reliable because the model's signature error is to **resolve** a relative
statement into an absolute one — "Rohan is on the block directly after Meera"
came back as `BLOCK Rohan 11:00` seven times. That matters more than 87%
suggests, because an invented absolute placement eliminates most of an item's
720 worlds while a wrong relative one eliminates few. This table is the input
to the component that helps most, and the reason it exists.

**Three of the four distractor families are free to get wrong.** Running the
reference parser and the solver together, I checked whether over-reading each
inert family would actually change an answer
(`dev/check_entailment.py`, `dev/check_null_family.py`):

- thwarted wishes ("lobbied for 11:00 without success") read as negatives:
  **64/64 entailed** — already true in every consistent world;
- unresolved questions ("nobody could remember whether"): **31/31 entailed**;
- **past-tense station history ("last month Priya was on intake"): 0/25.**
  Always false of the current rota.

So there is exactly one dangerous over-reading and it has a crisp linguistic
signature. Rule 2 of the prompt leads with it.

**Then I confirmed the target semantics before building anything.** With the
reference parser feeding the solver and only present-tense definite statements
treated as constraints, the oracle scores **macro 1.0000** on all 60 items
(`dev/check_semantics.py`). Adding the wish family drops it to 0.950; adding
past-tense history drops it to 0.367. That proved the symbolic layer correct and
told me every remaining point was an extraction problem — which is where the
rest of the effort went.

## 2. Why each component exists

The spine: **one call translates the lines, the solver does the rest.** With
5 people, 5 blocks and 3 stations an item has 120 × 6 = 720 possible worlds, so
the enumerator is exhaustive by construction. One world is `unique`, two or more
is `ambiguous` and all are returned, none is `inconsistent`, and the citation is
a minimal unsatisfiable subset found by deletion — which is *definitionally* the
scorer's rule rather than an approximation of it.

Two components come from reading the brief as a specification.

**`calib` — the calibrated drop.** The brief says every conflicting set here has
at least three statements, and the key confirms it: smallest cores are thirteen
of size 3, four of size 4, three of size 5, and **none of size 2**. So an
extraction whose smallest core has two statements is *provably not reporting a
conflict the notes contain* — the answer built on it is wrong whichever kind the
item really is, so there is nothing to lose by disbelieving one of the two. The
precision table says which to drop. Eight such cases arose on one run and five
were truly ambiguous items destroyed by a single invented constraint. Worth
**−0.021** when removed, and it costs **no model call**.

**`softneg` — soft negatives.** The mirror image, also free. A line read as
asserting nothing that nonetheless names exactly one person and exactly one
clock time is tried as a negative block claim, kept only if it removes worlds
and leaves at least one. It is safe *because* of the entailment measurements
above: no padding line in this task mentions a clock time, and the two inert
families that do are entailed as negatives anyway. Worth **−0.058**, also for
no call. The two free repairs turn out to be **additive**, not overlapping:
−0.079 when both are removed, against −0.021 and −0.058 alone. I had expected
them to overlap, since both are triggered by an implausible world count; they
act on disjoint sets of items.

**`mus` — minimal-core citation.** Not optional in any sense. With it the
inconsistent stratum scores 0.56; citing every constraining line instead scores
**0.00** — the whole stratum, **−0.187** of macro. Citing more is not safer, it
is disqualifying.

**The reply format turned out to be a component in disguise.** The model's
dominant failure at full item length is not a wrong code — it is derailing into
commentary part-way down the list and never reaching the rest (reasoning is
disabled at the API level and it writes prose regardless). One item got 2 of 20
lines answered after a 400-token monologue about what "held by" means. Dictating
the literal first characters of the reply and forbidding question marks took line
coverage from 68% to 89% (`dev/probe_format.py`, `dev/probe_format2.py`), and
replacing the word `NONE` with `-` to shorten the output took macro from 0.300 to
0.317. Omitting inert lines altogether — the shortest output — *lost* eight
points (0.233), because recall fell faster than derailment did. Format was worth
more than any wording change to the rules.

**`repair` — what extra budget buys.** The world count is a proof of extraction
error that needs no key, so budget is spent only where the count says something
is wrong and only on the lines responsible. `count > 4`: a constraint was missed
and it is in a line read as inert, so re-read *only those lines*. `count == 0`:
either a real contradiction or an invented constraint, and if invented it is in
the core, so re-read *exactly the core* — three lines of twenty. A paid repair is
never a retry of the item.

## 3. What I built and then removed

**Per-line vote merging.** The first budget loop merged repeated extractions line
by line and re-solved the merge. The curve came out non-monotone — 1× 0.450,
3× 0.517, **10× 0.400** — and the confusion matrix said why: inconsistent fell
from 0.60 at 3× to 0.30 at 10×. Per-line majority *drops* a constraint only two
passes of five found, and when that is the constraint a contradiction rests on, a
correctly-detected inconsistent item quietly becomes satisfiable. Extra budget
was dissolving the system's best answers.

**Then verdict-majority voting, which was also wrong.** Replaying one recorded
three-pass log through every aggregation rule, with the extraction held fixed so
the comparison carries no sampling noise (`dev/tune_aggregation.py`):

| rule | macro | | rule | macro |
|---|---|---|---|---|
| the three individual passes | 0.533 / 0.400 / 0.550 | | constraint union | 0.517 |
| per-line majority merge | 0.483 | | agree-only intersection | 0.383 |
| verdict majority | 0.517 | | **pick by world-count rank** | **0.567** |

**Every way of combining three extractions scored below the best single one.**
The model's errors are systematic, not independent noise, so averaging
reinforces them; merging additionally discards the constraint one lucky pass
found alone, which is exactly the one worth keeping when under-extraction
dominates. What works is *selection*: throw away the candidates that are
provably wrong — a world count above four cannot be right whatever the item is —
and keep the first survivor. Confirmed on an independent five-pass log, where it
scores 0.533 at both k=3 and k=5 against a 0.453 single-pass average, so the
gain saturates at three passes.

**One further correction, from watching 3× come in below 1× again.** Two
mechanisms were too eager. The rank treated "no worlds" as plausibly as "one to
four", so an under-constrained first pass re-sampled into an unsatisfiable one
looked like progress — four genuinely-inconsistent items were being traded for
four wrong `unique` answers. A contradiction now wins only if it was the first
conclusion or a second candidate reaches the same core independently. And the
core re-read treated a single disagreement as authoritative, when at
`temperature=1.0` the model disagrees with itself constantly; the core is now
re-read twice and the original reading survives unless the re-reads agree
against it. Those two changes took 3× from 0.450 to 0.517.

**Restatement agreement.** The scorer rejects a cited set containing two
citations that normalise to the same string, and warns that a restatement
normalises to the same string as the line it restates. I built the component to
avoid the trap, then measured it: **no two body lines in the visible set
normalise identically** (`dev/check_restatements.py`). The "restatements" are
re-phrasings — "Put Meera between Tomas and Rohan" and "Whichever way round
Tomas and Rohan are, Meera is between them" are two statements, and a core may
legitimately cite either. Catching those needs semantic matching, and the
obvious symbolic proxy (same set of names mentioned) also groups "A is earlier
than B" with "A is next to B". Removed rather than guessed at.

**`recover` and `strict`, kept but honestly near-dead.** Both move the replay
score by **0.004**, which is a tenth of the run-to-run noise. Most of what
`recover` was built for turned out to be fixable upstream: the strict parser was
discarding 37 codes per run over a trailing `?`, and salvaging those at parse
time made the component redundant. I report them at roughly zero rather than
quietly deleting them.

**An honest non-choice.** `n=3` sampling returns three completions in one HTTP
request, which the graders' counting proxy would see as one call —
self-consistency at 1×, within the letter of the budget rule. I did not do it.
The rule is about how much model work an answer may use, and three samples is
three samples.

## 4. Where it breaks, and why the curve is flat

The plateau has a number. Taking five independent extractions of all 60 items
and sorting every line-judgement by whether the passes got it right
(`dev/check_error_structure.py`, 1,137 judgements):

| | |
|---|---|
| right in all five passes | **79.5%** |
| wrong in all five, **the same way every time** | **4.0%** |
| wrong in all five, different ways | 1.8% |
| mixed — some passes right | 14.7% |

Only the bottom two rows are reachable by resampling at all. The 4.0% is a wall,
and it is dominated by *silent* under-extraction: of 46 such lines, 30 were read
as asserting nothing when they state a real constraint — twelve betweenness, seven
negative-block, six negative-station, five adjacency.

An item scores only if its whole reading is right, so one permanently-wrong line
loses it however many calls are spent. **Only 28 of 60 items have no
permanently-wrong line — 46.7%.** That is the ceiling any amount of resampling
can reach with this model and this prompt, and the system is already sitting on
it at 1×. This is the answer to why 10× does not beat 3×: the budget is not the
binding constraint, and no repair loop can fix an error the model reproduces
exactly on every attempt.

Three more specific failure modes:

**Under-extraction on unique items is the largest single bucket.** Typically 7–8
of 20 unique items are declared ambiguous: one constraint missed, world count
2–4, and nothing in the formal layer can distinguish "genuinely ambiguous" from
"one constraint short". The `count > 4` trigger catches the badly
under-extracted items; an item sitting at exactly 2 worlds when it should be 1
looks perfectly legitimate and is never repaired.

**The relative-to-absolute collapse is the costliest error class.** `BLOCK` at
71% precision does more damage than anything else, because one invented
placement eliminates ~500 of 720 worlds. `calib` cleans this up only when it
produces a too-small core; when it produces a *plausible* core, the system cites
a contradiction that is not there.

**Two constants I treat as soft.** `AMBIG_MAX = 4` and `MIN_CORE = 3` are read
off the brief, and the brief states the second as a property of *this* set. If
the held-out set contains a two-statement conflict, `calib` will dissolve it.
That is the component most likely to transfer worst, which is why it is a
separately-switchable arm.

**Variance is large and I have not hidden it.** The same configuration moves
±0.04 to 0.10 macro between runs on 60 items; individual extraction passes of
the same item score anywhere from 0.400 to 0.550. Every number in
[ABLATION.md](ABLATION.md) is a mean over three runs with the spread reported,
and the symbolic components are additionally measured by replay over four fixed
extractions so that those comparisons carry no sampling noise at all. No
single-run difference below about 0.05 should be read as a real effect.

## 5. If the notes were written by people

**What survives.** The formal layer is phrasing-independent: the world model, the
enumerator, the minimal-core search, `calib` and `softneg` all operate on
constraints and never on text. The few-shot example is deliberately written in
*paraphrases* absent from `items.json` — "Dev starts the moment Erin finishes,
with nothing in between", not "Dev is on the block directly after Erin" — so the
extractor is shown the semantic category rather than the template, and the rules
are stated as categories ("anything in the past", "a request that was refused")
rather than as surface forms. The repair triggers are properties of a solution
count, so they fire on new wording unchanged.

**What degrades gracefully.** The constraint vocabulary is closed, and real
people would write things it cannot express: "Priya and Rohan are never on
adjacent blocks", "someone has to cover intake before the eleven o'clock
delivery", soft preferences, statements whose scope is genuinely unclear. Those
become inert, the item looks under-constrained, and the system over-declares
ambiguous — which the brief rightly calls failing honestly. The count-based
trigger still fires, so the failure is visible rather than silent.

**What breaks.** Three things, in order of severity. First, real notes contain
statements that conflict *in degree* rather than flatly — "I think Priya was on
calibration, though Nadia may have swapped in" — and the entire architecture
rests on hedges carrying full force, which the brief guarantees and reality does
not. Second, `softneg`'s safety rests on a measured property of this generator —
that no inert line mentions a clock time — and a human writing "I'll double-check
the 09:00 handover with Meera" breaks it immediately; it would have to go.
Third, `MIN_CORE = 3` is a property of how these items were constructed, and
people contradict themselves in pairs all the time.

The honest summary: the symbolic half transfers, the calibration half is tuned
to a generator, and the two free components producing most of the gain are the
two most exposed. I would expect a real drop on human-written notes, led by
`calib`.

## 6. With a month

1. **Attack extraction recall, not the budget.** The ceiling measurement says
   the binding constraint is 4% of lines the model gets identically wrong every
   time — and 30 of those 46 are constraints read as silence. The oracle proves
   the ceiling above them is 1.00. Concretely: a two-stage single call that first
   *classifies* each line into {block, station, order, inert} and only then emits
   a code, which targets both the silent drops and the dimension confusions
   (`block ← imm` 7, `imm ← before` 6, `block ← between` 6).
2. **Fit the trust order instead of reading it off a table.** `TRUST` is eight
   integers. With a month I would fit per-code *and per-context* reliability on
   generated data and make the drop decision a likelihood comparison between
   "the notes contradict" and "this constraint is misread", rather than the
   `MIN_CORE` threshold.
3. **Make ambiguity a first-class question for the model.** Nothing currently
   asks it to distinguish "2 worlds because the notes allow 2" from "2 worlds
   because I missed a line", and that is the largest remaining bucket. A targeted
   question — "does any line fix which of Meera and Rohan is earlier?" — is
   answerable by a weak model and worth more per call than a re-read.
4. **Generate my own held-out set.** The semantics are pinned at 1.0000, so I can
   generate items from a disjoint phrasing pool and *measure* transfer instead of
   arguing about it. It is the only way to tell phrasing-independence from
   phrasing-luck, and it would directly test the three breakages in §5.
5. **A proper MUS enumerator.** `all_muses` sweeps deletion from 24 starting
   points; QuickXplain with proper recursion would give all cores cheaply and let
   the citation choose by calibrated confidence rather than by size.

## Checks before sending

`verify.py` checks the four things that are auto-fails rather than low scores —
the output parses for every item, every citation occurs verbatim in its item and
quotes exactly one line, every assignment names the whole rota, and the budget
held in both directions. `dev/check_model_sensitivity.py` demonstrates that the
answers depend on the model: replaying one run with every code blanked scores
**0.0000** and changes all 60 answers, and with polarities flipped, 0.0500.
