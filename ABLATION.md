# Ablation

Two tables. They measure the same components by different means and agree,
which is the point of having both.

- **Live** — the full system re-run end to end with one component switched
  off, three runs per cell. This is the table to re-run.
- **Replay** — the purely-symbolic components measured over four *recorded*
  extractions, with no new model calls. Same model output for every arm, so
  the comparison carries no sampling noise at all.

The replay table exists because of a measurement, not a preference:
**run-to-run spread at `temperature=1.0` is ±0.04 to 0.10 macro on 60 items**,
which is larger than several of the effects being ablated. Three individual
extractions of the same item scored 0.533 / 0.400 / 0.550 on one log and
0.483 / 0.417 / 0.517 / 0.433 / 0.417 on another. Any single-run difference
below about 0.05 in the live table should be read as noise; the replay table
is where the small effects are actually resolved.

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
| `-rules` | 0.333 +/- 0.027 | -- | -- | extraction prompt without the inert-family rules |
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
| `-rules` | 1x | 0.28 | 0.28 | 0.43 | 0.28 | 0.08 | 1-1 |
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

<!-- COMMENTARY -->
