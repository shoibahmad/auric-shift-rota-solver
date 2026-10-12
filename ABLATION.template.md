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
