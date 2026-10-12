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

<!-- LIVE_TABLE -->

## Replay table — symbolic components, no sampling noise

<!-- REPLAY_TABLE -->

## Reading it

<!-- COMMENTARY -->
