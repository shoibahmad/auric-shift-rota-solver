# Sample output

`run_1x.json`, `run_3x.json`, `run_10x.json` are the answers the system
actually produced on the visible set, and `score_*.json` are the provided
scorer's output for each.

These are **run 0** of the three ablation runs at each budget, not the best of
the three. Picking the best would misrepresent a system whose run-to-run spread
is larger than most of its components' effects. The means over all three runs
are in [../ABLATION.md](../ABLATION.md); this run 0 came in at 0.433 / 0.533 /
0.500 against means of 0.467 / 0.506 / 0.522.

Regenerate:

```bash
./run items.json --budget 3x --out results/run_3x.json
python3 score.py visible_key.json results/run_3x.json
```
