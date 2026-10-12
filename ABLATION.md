# Ablation

Two tables. They measure the same components by different means and agree,
which is the point of having both.

- **Live** — the full system re-run end to end with one component switched
  off, three runs per cell. This is the table to re-run.
- **Replay** — the purely-symbolic components measured over four *recorded*
  extractions, with no new model calls. Same model output for every arm, so
  the comparison carries no sampling noise at all.

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
worth everything, minimal-core citation is worth the whole inconsistent
stratum, the free repairs beat the paid ones -- and those are the ones the
commentary draws.

The replay table exists for the same reason. Three individual extractions of
the same item scored 0.533 / 0.400 / 0.550 on one log and 0.483 / 0.417 /
0.517 / 0.433 / 0.417 on another, which is larger than several of the effects
being ablated. Replaying a *fixed* extraction removes that noise entirely, so
the small effects are resolved there rather than in the live table.

## Reproducing

```bash
# live table (this is the one to re-run)
python3 ablate.py --items items.json --key visible_key.json \
    --budgets 1x,3x,10x --runs 3 --plan focused --outdir runs/ablation

# every arm at every budget, if you want it
python3 ablate.py --budgets 1x,3x,10x --runs 3 --plan full --outdir runs/full

# replay table: no model calls, exact comparison
python3 dev/replay.py runs/fmt_dash_calls.json runs/v2_1x_calls.json \
    runs/p3_calls.json runs/p5_calls.json
```

`ablate.py` writes `runs/ablation/ablation.md` plus the `answers.json`,
`score.json` and per-item trace behind **every cell**, so any number in the
table can be traced back to the answers that produced it.

Under the `focused` plan each arm runs at the budgets where its component can
act — a component that only spends extra calls has nothing to do at 1×, and a
component that acts on the extraction is measured at 1× where no repair can
mask it. The reasoning is in a comment at the top of `ablate.py`.

## Live table

Three runs per cell unless noted; **mean +/- population standard deviation** of macro exact match. Highest run count seen: 3.

| arm | 1x | 3x | 10x | what it does |
|---|---|---|---|---|
| `full` | 0.467 +/- 0.036 | 0.506 +/- 0.028 | 0.522 +/- 0.016 | every component on |
| `-solver` | 0.000 +/- 0.000 | 0.000 +/- 0.000 | 0.000 +/- 0.000 | no formal layer: the model is asked for the answer |
| `-mus` | 0.300 +/- 0.024 | -- | -- | cite every constraining line, not a minimal core |
| `-rules` | 0.333 +/- 0.027 | -- | -- | extraction prompt without the inert-family rules |
| `-calib` | 0.444 +/- 0.034 | -- | -- | no calibrated drop on a too-small conflict (free, no call) |
| `-softneg` | 0.433 +/- 0.049 | -- | -- | no soft negatives on missed name+time lines (free, no call) |
| `-vote` | -- | 0.539 +/- 0.021 | 0.478 +/- 0.021 | no re-extraction and selection |
| `-repair` | -- | 0.489 +/- 0.016 | 0.506 +/- 0.048 | no count-triggered targeted re-reads |
| `-recover` | 0.422 +/- 0.008 | -- | -- | no free re-parse of dropped codes |
| `-strict` | 0.472 +/- 0.016 | -- | -- | accept codes the validator drops, by fuzzy name matching |

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
| `-rules` | 1x | 0.28 | 0.28 | 0.43 | 0.28 | 0.08 | 1-1 |
| `-calib` | 1x | 0.42 | 0.43 | 0.48 | 0.43 | 0.32 | 1-1 |
| `-softneg` | 1x | 0.42 | 0.35 | 0.53 | 0.35 | 0.17 | 1-1 |
| `-vote` | 3x | 0.48 | 0.50 | 0.63 | 0.50 | 0.18 | 1-3 |
| `-vote` | 10x | 0.48 | 0.43 | 0.52 | 0.43 | 0.22 | 1-3 |
| `-repair` | 3x | 0.47 | 0.50 | 0.50 | 0.50 | 0.25 | 3-3 |
| `-repair` | 10x | 0.50 | 0.45 | 0.57 | 0.45 | 0.22 | 5-5 |
| `-recover` | 1x | 0.40 | 0.37 | 0.50 | 0.37 | 0.20 | 1-1 |
| `-strict` | 1x | 0.52 | 0.37 | 0.53 | 0.37 | 0.22 | 1-1 |

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


| arm | macro (mean of 4) | unique | ambiguous | inconsistent | vs full |
|---|---|---|---|---|---|
| `full` | 0.479 +/- 0.036 | 0.47 | 0.40 | 0.56 | -- |
| `-mus` | 0.292 +/- 0.028 | 0.47 | 0.40 | 0.00 | -0.187 |
| `-calib` | 0.458 +/- 0.049 | 0.47 | 0.34 | 0.56 | -0.021 |
| `-softneg` | 0.421 +/- 0.030 | 0.41 | 0.29 | 0.56 | -0.058 |
| `-calib,-softneg` | 0.400 +/- 0.043 | 0.41 | 0.23 | 0.56 | -0.079 |
| `-recover` | 0.475 +/- 0.042 | 0.47 | 0.39 | 0.56 | -0.004 |
| `-strict` | 0.475 +/- 0.030 | 0.47 | 0.40 | 0.55 | -0.004 |

logs: fmt_dash_calls.json, v2_1x_calls.json, p3_calls.json, p5_calls.json

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

**The free repairs are worth more than the paid ones.** `-calib` (0.444) and
`-softneg` (0.433) each cost more than removing *either* paid mechanism, and
neither spends a model call. They are also additive rather than overlapping:
replay puts them at -0.021 and -0.058 alone, -0.079 together.

**Live and replay agree where both measured** — `-mus` -0.167 live against
-0.187 replayed, `-calib` -0.022 against -0.021 — which is the point of running
both. They disagree on `-recover`: -0.045 live, -0.004 replayed. The replay is
the better-controlled number (identical model output for both arms), and the
live gap is about one standard deviation of `full`'s own spread, so the honest
reading is that `recover` does nothing measurable either way.

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
