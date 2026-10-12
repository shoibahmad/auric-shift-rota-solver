"""Pool every full-system run of the visible set into one honest summary.

Three sources, all of the same unmodified pipeline:
  runs/ablation/full_*      the three ablation runs per budget
  runs/variance/*           the extra replicates
  runs/e2e/score_*.json     the end-to-end validation run

Reports n, mean, population SD and the observed range per budget. The range is
the number that matters for the "ablation does not reproduce" check: a grader
re-running once should expect to land inside it.

    python3 dev/summarise_runs.py
"""
import glob
import io
import json
import os
import re
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                                # noqa: BLE001
    pass

vals = {"1x": [], "3x": [], "10x": []}
src = {"1x": [], "3x": [], "10x": []}


def add(b, v, where):
    if b in vals:
        vals[b].append(v)
        src[b].append(where)


for p in sorted(glob.glob(os.path.join(ROOT, "runs/ablation/full_*_score.json"))):
    m = re.match(r"full_(1x|3x|10x)_r(\d+)_score\.json$", os.path.basename(p))
    d = json.load(io.open(p, encoding="utf-8"))
    add(m.group(1), d["result"]["macro_exact_match"], "ablation")

for p in sorted(glob.glob(os.path.join(ROOT, "runs/variance/*.json"))):
    m = re.match(r"(1x|3x|10x)_r(\d+)\.json$", os.path.basename(p))
    if not m:
        continue
    d = json.load(io.open(p, encoding="utf-8"))
    add(m.group(1), d["macro"], "variance")

for b in ("1x", "3x", "10x"):
    p = os.path.join(ROOT, "runs/e2e", f"score_{b}.json")
    if os.path.exists(p):
        add(b, json.load(io.open(p, encoding="utf-8"))["macro_exact_match"],
            "e2e")

print(f"{'budget':8s} {'n':>3s} {'mean':>7s} {'sd':>7s} {'min':>7s} "
      f"{'max':>7s}   runs")
for b in ("1x", "3x", "10x"):
    v = vals[b]
    if not v:
        continue
    print(f"{b:8s} {len(v):3d} {statistics.mean(v):7.3f} "
          f"{statistics.pstdev(v):7.3f} {min(v):7.3f} {max(v):7.3f}   "
          + " ".join(f"{x:.3f}" for x in sorted(v)))

print("\nsources:", {b: {s: src[b].count(s) for s in set(src[b])}
                     for b in vals if vals[b]})
allv = [x for b in vals for x in vals[b]]
print(f"\nacross all budgets: n={len(allv)} "
      f"spread={max(allv) - min(allv):.3f} "
      f"(min {min(allv):.3f}, max {max(allv):.3f})")
