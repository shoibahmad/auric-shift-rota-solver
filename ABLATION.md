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

Over **27 runs of the unmodified pipeline** (`dev/summarise_runs.py`), the
full system measures:

| budget | n | mean | SD | observed range |
|---|---|---|---|---|
| 1x | 9 | 0.469 | 0.041 | 0.417 - 0.533 |
| 3x | 9 | 0.504 | 0.043 | 0.450 - 0.583 |
| 10x | 9 | 0.504 | 0.034 | 0.450 - 0.550 |

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

Three runs per cell unless noted; **mean +/- population standard deviation** of macro exact match. Highest run count seen: 3.

| arm | 1x | 3x | 10x | what it does |
|---|---|---|---|---|
| `full` | 0.467 +/- 0.036 | 0.506 +/- 0.028 | 0.522 +/- 0.016 | every component on |
| `-solver` | 0.000 +/- 0.000 | 0.000 +/- 0.000 | 0.000 +/- 0.000 | no formal layer: the model is asked for the answer |
| `-mus` | 0.300 +/- 0.024 | 0.394 +/- 0.055 | 0.372 +/- 0.028 | cite every constraining line, not a minimal core |
| `-rules` | 0.333 +/- 0.027 | 0.378 +/- 0.028 | 0.394 +/- 0.028 | extraction prompt without the inert-family rules |
| `-calib` | 0.444 +/- 0.034 | 0.533 +/- 0.049 | 0.489 +/- 0.044 | no calibrated drop on a too-small conflict (free, no call) |
| `-softneg` | 0.433 +/- 0.049 | 0.578 +/- 0.016 | 0.572 +/- 0.021 | no soft negatives on missed name+time lines (free, no call) |
| `-vote` | 0.511 +/- 0.016 | 0.539 +/- 0.021 | 0.478 +/- 0.021 | no re-extraction and selection |
| `-repair` | 0.489 +/- 0.034 | 0.489 +/- 0.016 | 0.506 +/- 0.048 | no count-triggered targeted re-reads |
| `-recover` | 0.422 +/- 0.008 | 0.583 +/- 0.014 | 0.567 +/- 0.036 | no free re-parse of dropped codes |
| `-strict` | 0.472 +/- 0.016 | 0.494 +/- 0.028 | 0.506 +/- 0.016 | accept codes the validator drops, by fuzzy name matching |

### Per-kind rates and the two diagnostics

| arm | budget | unique | ambiguous | inconsistent | amb_partial | inc_label_only | calls/item |
|---|---|---|---|---|---|---|---|
| `full` | 1x | 0.42 | 0.38 | 0.60 | 0.38 | 0.15 | 1-1 |
| `full` | 3x | 0.50 | 0.47 | 0.55 | 0.47 | 0.17 | 2-3 |
| `full` | 10x | 0.52 | 0.45 | 0.60 | 0.47 | 0.20 | 2-10 |
| `-solver` | 1x | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 1-1 |
| `-solver` | 3x | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 3-3 |
| `-solver` | 10x | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 5-5 |
| `-mus` | 1x | 0.50 | 0.40 | 0.00 | 0.40 | 0.68 | 1-1 |
| `-mus` | 3x | 0.55 | 0.63 | 0.00 | 0.63 | 0.68 | 2-3 |
| `-mus` | 10x | 0.52 | 0.60 | 0.00 | 0.60 | 0.78 | 2-10 |
| `-rules` | 1x | 0.28 | 0.28 | 0.43 | 0.28 | 0.08 | 1-1 |
| `-rules` | 3x | 0.35 | 0.40 | 0.38 | 0.40 | 0.17 | 2-3 |
| `-rules` | 10x | 0.42 | 0.35 | 0.42 | 0.37 | 0.13 | 2-10 |
| `-calib` | 1x | 0.42 | 0.43 | 0.48 | 0.43 | 0.32 | 1-1 |
| `-calib` | 3x | 0.57 | 0.43 | 0.60 | 0.43 | 0.18 | 2-3 |
| `-calib` | 10x | 0.50 | 0.40 | 0.57 | 0.40 | 0.13 | 2-10 |
| `-softneg` | 1x | 0.42 | 0.35 | 0.53 | 0.35 | 0.17 | 1-1 |
| `-softneg` | 3x | 0.58 | 0.50 | 0.65 | 0.50 | 0.12 | 2-3 |
| `-softneg` | 10x | 0.55 | 0.57 | 0.60 | 0.57 | 0.10 | 2-10 |
| `-vote` | 1x | 0.48 | 0.48 | 0.57 | 0.48 | 0.12 | 1-1 |
| `-vote` | 3x | 0.48 | 0.50 | 0.63 | 0.50 | 0.18 | 1-3 |
| `-vote` | 10x | 0.48 | 0.43 | 0.52 | 0.43 | 0.22 | 1-3 |
| `-repair` | 1x | 0.43 | 0.43 | 0.60 | 0.43 | 0.17 | 1-1 |
| `-repair` | 3x | 0.47 | 0.50 | 0.50 | 0.50 | 0.25 | 3-3 |
| `-repair` | 10x | 0.50 | 0.45 | 0.57 | 0.45 | 0.22 | 5-5 |
| `-recover` | 1x | 0.40 | 0.37 | 0.50 | 0.37 | 0.20 | 1-1 |
| `-recover` | 3x | 0.53 | 0.58 | 0.63 | 0.58 | 0.17 | 2-3 |
| `-recover` | 10x | 0.47 | 0.58 | 0.65 | 0.58 | 0.17 | 2-10 |
| `-strict` | 1x | 0.52 | 0.37 | 0.53 | 0.37 | 0.22 | 1-1 |
| `-strict` | 3x | 0.53 | 0.42 | 0.53 | 0.42 | 0.17 | 2-3 |
| `-strict` | 10x | 0.47 | 0.50 | 0.55 | 0.50 | 0.25 | 2-10 |

### Confusion matrix, full system

Rows are the true kind, columns what was declared. Summed over the three runs, so each row totals 60.

**1x**

| true \ declared | unique | ambiguous | inconsistent | unparsed |
|---|---|---|---|---|
| unique | 25 | 27 | 8 | 0 |
| ambiguous | 1 | 45 | 14 | 0 |
| inconsistent | 1 | 14 | 45 | 0 |

**3x**

| true \ declared | unique | ambiguous | inconsistent | unparsed |
|---|---|---|---|---|
| unique | 31 | 23 | 6 | 0 |
| ambiguous | 1 | 46 | 13 | 0 |
| inconsistent | 4 | 13 | 43 | 0 |

**10x**

| true \ declared | unique | ambiguous | inconsistent | unparsed |
|---|---|---|---|---|
| unique | 31 | 23 | 6 | 0 |
| ambiguous | 2 | 44 | 14 | 0 |
| inconsistent | 4 | 8 | 48 | 0 |


## Replay table — symbolic components, no sampling noise


| arm | macro (mean of 3) | unique | ambiguous | inconsistent | vs full |
|---|---|---|---|---|---|
| `full` | 0.483 +/- 0.041 | 0.47 | 0.38 | 0.60 | -- |
| `-mus` | 0.283 +/- 0.027 | 0.47 | 0.38 | 0.00 | -0.200 |
| `-calib` | 0.461 +/- 0.057 | 0.47 | 0.32 | 0.60 | -0.022 |
| `-softneg` | 0.422 +/- 0.034 | 0.40 | 0.27 | 0.60 | -0.061 |
| `-calib,-softneg` | 0.400 +/- 0.049 | 0.40 | 0.20 | 0.60 | -0.083 |
| `-recover` | 0.478 +/- 0.048 | 0.47 | 0.37 | 0.60 | -0.006 |
| `-strict` | 0.478 +/- 0.034 | 0.47 | 0.38 | 0.58 | -0.006 |

logs: extraction_1x.json, extraction_3pass.json, extraction_5pass.json

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
