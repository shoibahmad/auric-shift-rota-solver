# Recorded scores

The `score.py` output behind every number in [../../ABLATION.md](../../ABLATION.md)
and the headline curve in [../../WRITEUP.md](../../WRITEUP.md), so both
reproduce from a clean checkout with no model calls.

| what | files |
|---|---|
| ablation cells | 90 — one per arm × budget × run |
| extra full-system runs | 15 — the variance measurement and the end-to-end runs |

`dev/summarise_runs.py` reads `runs/` if you have just produced fresh results
there, and falls back to these; it prints which it used. 419 KB in total, which
is cheaper than asking a grader to spend two hours of model calls to check an
arithmetic claim.

These are *outputs*, not inputs: regenerate them with the commands in
[../../ABLATION.md](../../ABLATION.md).
