"""Entrypoint. `./run <items.json> --budget <1x|3x|10x> --out <answers.json>`"""
import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from .client import ModelClient
from .pipeline import DEFAULT_COMPONENTS, solve_item, to_answer

BUDGETS = {"1x": 1, "3x": 3, "10x": 10}


def parse_components(spec):
    """--components  all | none | solver,mus,...  | -vote,-repair"""
    comps = dict(DEFAULT_COMPONENTS)
    if not spec or spec == "all":
        return comps
    parts = [p.strip() for p in spec.split(",") if p.strip()]
    if parts and all(p.startswith("-") for p in parts):
        for p in parts:
            name = p[1:]
            if name not in comps:
                raise SystemExit(f"unknown component: {name}")
            comps[name] = False
        return comps
    if parts == ["none"]:
        return {k: False for k in comps}
    comps = {k: False for k in comps}
    for p in parts:
        if p not in comps:
            raise SystemExit(f"unknown component: {p}")
        comps[p] = True
    return comps


def run(items, budget, comps, workers=8, log=None, progress=True, fmt=None):
    client = ModelClient(budget=BUDGETS[budget] if budget in BUDGETS
                         else int(budget), log=log)
    answers, traces = {}, {}
    done = [0]
    t0 = time.time()

    def one(item):
        try:
            s = solve_item(item, client, budget, comps, want_trace=True,
                           fmt=fmt)
            a = to_answer(item, s)
            tr = {"case": s.case, "calls": s.calls, "trace": s.trace,
                  "n_worlds": len(s.worlds) if isinstance(s.worlds, list) else None,
                  "n_cons": len(s.cons)}
        except Exception as exc:                            # noqa: BLE001
            # A crash on one item must not cost the other 59. An empty unique
            # claim is a wrong answer, which is what a crash deserves.
            a = {"case": "unique", "assignment": {}}
            tr = {"case": "error", "error": repr(exc), "calls": 0}
        done[0] += 1
        if progress:
            sys.stderr.write(f"\r  {done[0]}/{len(items)} items"
                             f"  {time.time() - t0:6.1f}s")
            sys.stderr.flush()
        return item["id"], a, tr

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for iid, a, tr in ex.map(one, items):
            answers[iid] = a
            traces[iid] = tr
    if progress:
        sys.stderr.write("\n")
    return answers, traces, client


def main(argv=None):
    ap = argparse.ArgumentParser(prog="run", description=__doc__)
    ap.add_argument("items")
    ap.add_argument("--budget", default="1x", help="1x | 3x | 10x")
    ap.add_argument("--out", default="answers.json")
    ap.add_argument("--components", default="all",
                    help="all | none | comma list | -name,-name to drop")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--fmt", default=None, help="dense | dash | sparse")
    ap.add_argument("--trace", default=None, help="write a per-item trace here")
    ap.add_argument("--calls-log", default=None,
                    help="write every prompt and reply here (debugging)")
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args(argv)

    if a.budget not in BUDGETS:
        raise SystemExit("--budget must be 1x, 3x or 10x")

    items = json.load(open(a.items, encoding="utf-8"))
    if isinstance(items, dict):
        items = items.get("items", [])
    if a.limit:
        items = items[:a.limit]
    comps = parse_components(a.components)

    log = [] if a.calls_log else None
    answers, traces, client = run(items, a.budget, comps, a.workers, log=log,
                                  fmt=a.fmt)

    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(answers, fh, indent=1, ensure_ascii=False)

    over = {k: v for k, v in client.calls.items() if v > client.budget}
    zero = [i["id"] for i in items if client.used(i["id"]) == 0]
    sys.stderr.write(
        f"  budget {a.budget}: {client.total_calls()} calls over "
        f"{len(items)} items (max {max(client.calls.values(), default=0)}/item,"
        f" min {min(client.calls.values(), default=0)}/item)\n")
    if over or zero:
        sys.stderr.write(f"  !! budget violations: over={over} zero={zero}\n")

    if a.trace:
        with open(a.trace, "w", encoding="utf-8") as fh:
            json.dump({"budget": a.budget, "components": comps,
                       "calls": client.calls, "items": traces}, fh, indent=1)
    if a.calls_log:
        with open(a.calls_log, "w", encoding="utf-8") as fh:
            json.dump(log, fh, indent=1)
    sys.stderr.write(f"  wrote {a.out}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
