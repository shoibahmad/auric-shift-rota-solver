<!-- SOURCE FILE. Edit this, not ABLATION.md.
     ABLATION.md is generated from this template by dev/build_ablation.py,
     which substitutes the two tables below from runs/ablation/*_score.json
     and runs/replay_table.md so no figure is ever hand-typed. -->

# Ablation

<sub>Generated from `ABLATION.template.md` by `dev/build_ablation.py` — edit
the template, not this file.</sub>

Two tables. They measure the same components by different means and agree,
which is the point of having both.

- **Live** — the full system re-run end to end with one component switched
  off, three runs per cell. This is the table to re-run.
- **Replay** — the purely-symbolic components measured over the three
  *recorded* extractions in `fixtures/`, with no new model calls. Same model
  output for every arm, so the comparison carries no sampling noise at all.

### What "reproduces" means here

Over **33 runs of the unmodified pipeline** (`dev/summarise_runs.py`), the
full system measures:

| budget | n | mean | SD | observed range |
|---|---|---|---|---|
| 1x | 15 | 0.481 | 0.040 | 0.417 - 0.533 |
| 3x | 9 | 0.504 | 0.043 | 0.450 - 0.583 |
| 10x | 9 | 0.504 | 0.034 | 0.450 - 0.550 |

1x carries n=15 because the `-vote` and `-repair` cells at one call are the
same code path as `full` -- see the null, below -- so they are extra samples of
the shipped system rather than a different one. That is also why the `full` 1x
cell reads 0.467 while the pooled estimate is 0.481: three runs is a small
sample of a distribution this wide.

**A single re-run should be expected to land in the observed range, not on the
mean.** That spread is a property of `temperature=1.0` on a 60-item set, not
of the system: the three-run cells below were sampled from exactly these
distributions, and re-running one cell once can easily move it 0.05. The
conclusions that survive this noise are the large ones -- the formal layer is
worth everything, and minimal-core citation is worth the whole inconsistent
stratum. The smaller arms do not clear it, which is why the commentary below
measures an explicit null before drawing anything from them.

The replay table exists for the same reason. Three individual extractions of
the same item scored 0.533 / 0.400 / 0.550 on one log and 0.483 / 0.417 /
0.517 / 0.433 / 0.417 on another, which is larger than several of the effects
being ablated. Replaying a *fixed* extraction removes that noise entirely, so
the small effects are resolved there rather than in the live table.

## Reproducing

```bash
# the live table below: every arm at every budget, three runs per cell
python3 ablate.py --items items.json --key visible_key.json \
    --budgets 1x,3x,10x --runs 3 --plan full --outdir runs/ablation

# cheaper: each arm only at the budgets where its component can act
python3 ablate.py --budgets 1x,3x,10x --runs 3 --plan focused \
    --outdir runs/focused

# replay table: no model calls, exact comparison
python3 dev/replay.py fixtures/extraction_1x.json \
    fixtures/extraction_3pass.json fixtures/extraction_5pass.json

# rebuild this document from the template and those two results
python3 dev/build_ablation.py --outdir runs/ablation \
    --replay runs/replay_table.md
```

`ablate.py` writes `runs/ablation/ablation.md` plus the `answers.json`,
`score.json` and per-item trace behind **every cell**, so any number in the
table can be traced back to the answers that produced it.

Every cell below is measured. The `focused` plan exists as a cheaper option —
it runs each arm only where its component can act, since one that merely spends
extra calls has nothing to do at 1× — but the shipped table is the full grid,
and the cells `focused` would have skipped turned out to be the most
informative ones (see the null, below).

## Live table

<!-- LIVE_TABLE -->

## Replay table — symbolic components, no sampling noise

<!-- REPLAY_TABLE -->

## Reading it

**The formal layer is the whole system.** `-solver` is the same weak model
answering the same question with no symbolic layer: **0.000 at every budget**,
with every item declared `unique`. That is the brief's figure reproduced, and it
is the only arm whose removal is catastrophic rather than costly.

**Two components carry most of the rest, and both act on the extraction, not
the budget.** `-mus` (0.300) loses the entire inconsistent stratum: citing
every constraining line instead of a minimal core scores *zero* on all 20
items, because "contradictory" is not the rule — "minimally contradictory" is.
`-rules` (0.333) is the inert-family guidance in the prompt, and its cost is
almost all past-tense station history read as current, which is the one
over-reading that is never free (`dev/check_entailment.py`: 0/25 entailed).

**The free repairs are worth more than the paid ones at 1x** — and only
there. `-calib` (0.444) and `-softneg` (0.433) each cost more at one call than
removing *either* paid mechanism does, without spending a call, and they are
additive rather than overlapping: replay puts them at -0.022 and -0.061 alone,
-0.083 together. Above 1x the sign reverses; see below. That reversal is why
this heading carries a qualifier the writeup's earlier drafts did not.

**Live and replay agree where both measured** — at 1x, `-mus` is -0.167 live
against -0.200 replayed and `-calib` -0.022 against -0.022 — which is the point
of running both. They disagree on `-recover`: -0.044 live, -0.006 replayed. The
replay is the better-controlled number (identical model output for both arms)
and the live gap is about one standard deviation of `full`'s own spread, so the
honest reading is that `recover` does nothing measurable either way.

**There is an empirical null in this table, and it should be read first.**
`-vote` and `-repair` at 1x are *the same code path* as `full`: neither
component can act when the single call has already been spent, so those cells
measure identical behaviour. They come out **+0.044 and +0.022 away from
`full`**. That is what zero effect looks like here, measured rather than
assumed, and it is the yardstick for every other number below. Anything inside
about 0.045 is indistinguishable from no effect at all.

By that yardstick: the formal layer (-0.467), minimal-core citation (-0.167 at
1x) and the inert-family rules (-0.133) are real and large. Everything else in
the table is at or near the null, including the three results that look like
the full system being beaten.

**`-softneg` and `-recover` score ABOVE the full system at 3x and 10x**
(+0.072 and +0.078 at 3x; +0.050 and +0.044 at 10x). Both are free repairs that
help at 1x (-0.033 and -0.044) and appear to hurt once a repair loop is also
running, which is a plausible interference: a speculative constraint added for
free can lock the selection onto a wrong-but-plausible verdict that the paid
re-read would otherwise have corrected. The 3x figures sit just outside the
null and the 10x figures sit on it, so I record this as a suggestive finding
rather than a result, and as the first thing I would chase with more time. It
does qualify the writeup's claim: the free repairs earn their place *at 1x*,
which is the budget weighted most heavily, not necessarily above it.

**`-vote` at 3x scores 0.539, above the full system's 0.506.** Switching off
re-extraction-and-selection at three calls *improves* the score, and at ten
calls it costs 0.044 instead. I have not re-tuned the trigger on this: the 3x
gap is 0.033 against a 0.028 standard deviation in the same cell, it reverses
sign at the next budget, and fitting a budget-dependent threshold to 60 items
with that much spread is how a submission stops generalising. What the pair of
numbers does support is the conclusion in the writeup — at three calls the paid
mechanisms are roughly interchangeable and neither is clearly positive, because
the errors they chase are systematic and resampling does not reach them
(`dev/check_error_structure.py`: 4% of lines are wrong identically every time,
and only 28 of 60 items have none of them).

**The confusion matrices show the failure has the honest direction.** At every
budget the `unique` row leaks into `ambiguous` (27, 23, 23 of 60) and almost
never the reverse — the system under-extracts and says so, rather than
inventing a single answer. `inconsistent` recognition improves with budget
(45 → 43 → 48 of 60) and `inc_label_only` stays at 0.15-0.20, meaning that when
the kind is called correctly the citation usually meets the minimality rule
too.
