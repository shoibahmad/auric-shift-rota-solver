"""How much does one run of the same configuration move?

Three runs per cell gave a population SD of 0.016 at 10x, and a later
end-to-end run of the byte-identical pipeline came in 0.072 below that cell's
mean. An SD estimated from three samples is itself very noisy, and reporting
one that tight invites a re-run to look like a failure to reproduce. This
gathers more replicates of the full system so the published spread is an
honest one.

    python3 dev/measure_variance.py --runs 5 --budgets 1x,3x,10x
"""
import argparse
import json
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rota.main import run, parse_components                      # noqa: E402
from score import score                                          # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                                # noqa: BLE001
    pass

ap = argparse.ArgumentParser()
ap.add_argument("--runs", type=int, default=5)
ap.add_argument("--budgets", default="1x,3x,10x")
ap.add_argument("--workers", type=int, default=10)
ap.add_argument("--outdir", default="runs/variance")
a = ap.parse_args()

items = json.load(open("items.json", encoding="utf-8"))
key = json.load(open("visible_key.json", encoding="utf-8"))
os.makedirs(a.outdir, exist_ok=True)
comps = parse_components("all")

for b in [x.strip() for x in a.budgets.split(",") if x.strip()]:
    macros = []
    for r in range(a.runs):
        ans, _tr, client = run(items, b, comps, workers=a.workers,
                               progress=False)
        res = score(key, ans, items)
        macros.append(res["macro_exact_match"])
        path = os.path.join(a.outdir, f"{b}_r{r}.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"macro": res["macro_exact_match"],
                       "per_case": res["per_case_rate"],
                       "calls": client.total_calls()}, fh, indent=1)
        print(f"  {b} run {r}: macro={res['macro_exact_match']:.3f} "
              f"calls={client.total_calls()}", flush=True)
    print(f"{b}: n={len(macros)} mean={statistics.mean(macros):.3f} "
          f"sd={statistics.pstdev(macros):.3f} "
          f"min={min(macros):.3f} max={max(macros):.3f}\n", flush=True)
