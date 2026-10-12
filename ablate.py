"""Reproduce the ablation table.

    python3 ablate.py --items items.json --key visible_key.json \
        --budgets 1x,3x,10x --runs 1 --outdir runs/ablation

For each budget and each arm it runs the full system, scores it with the
provided `score.py`, and writes `ablation.md` plus the raw `answers.json` and
`score.json` for every cell so any number in the table can be traced back to
the answers that produced it.

An arm is the full system with one component switched off. Every arm still
makes at least one model call per item and never more than the budget: the
`solver` arm replaces the symbolic layer with a direct question to the model
rather than removing the call.
"""
import argparse
import json
import os
import statistics
import sys
import time

from rota.main import run, parse_components
from score import score

ARMS = [
    ("full",      "all",       "every component on"),
    ("-solver",   "-solver",   "no formal layer: ask the model for the answer"),
    ("-rules",    "-rules",    "extraction prompt without the inert-family rules"),
    ("-strict",   "-strict",   "accept codes the validator would drop"),
    ("-recover",  "-recover",  "no free re-parse of dropped codes"),
    ("-vote",     "-vote",     "no self-consistency over extractions"),
    ("-repair",   "-repair",   "no count-triggered targeted re-reads"),
    ("-mus",      "-mus",      "cite every constraining line, not a minimal core"),
    ("-calib",    "-calib",    "no calibrated drop on a too-small conflict (free)"),
    ("-softneg",  "-softneg",  "no soft negatives on missed name+time lines (free)"),
]

# Components that cannot act at 1x: one call leaves nothing to spend, so the
# arm is identical to `full` by construction and is not re-run.
ONLY_MULTI = {"-vote", "-repair"}

# Which budgets each arm is run at.
#
# `focused` is what ABLATION.md reports, and it is not a shortcut -- it puts
# the runs where they change a conclusion. Run-to-run spread at temperature
# 1.0 is +/-0.05 to 0.10 macro on 60 items, which is larger than several of
# the effects being measured, so three runs of the cells that matter is better
# evidence than one run of everything. Each arm is run at the budgets where
# its component can actually act: a component that only spends extra calls has
# nothing to do at 1x, and a component that acts on the extraction is measured
# at 1x where no repair can mask it. `dev/replay.py` additionally measures
# every purely-symbolic arm over four recorded extractions with no sampling
# noise at all.
#
# `--plan full` runs every arm at every budget, for anyone who wants it.
FOCUSED = {
    "full":     ("1x", "3x", "10x"),
    "-solver":  ("1x", "3x", "10x"),
    "-mus":     ("1x",),
    "-calib":   ("1x",),
    "-softneg": ("1x",),
    "-rules":   ("1x",),
    "-strict":  ("1x",),
    "-recover": ("1x",),
    "-vote":    ("3x", "10x"),
    "-repair":  ("3x", "10x"),
}

HEAD = ("| arm | " + " | ".join("{b} macro".format(b=b) for b in ("1x", "3x", "10x"))
        + " | what it does |")


def cell(items, key, budget, comps, outdir, tag, runs, workers):
    macros, details = [], []
    for r in range(runs):
        ans, traces, client = run(items, budget, comps, workers=workers,
                                  progress=True)
        res = score(key, ans, items)
        res.pop("per_item", None)
        macros.append(res["macro_exact_match"])
        details.append(res)
        base = os.path.join(outdir, f"{tag}_{budget}_r{r}")
        with open(base + "_answers.json", "w", encoding="utf-8") as fh:
            json.dump(ans, fh, indent=1, ensure_ascii=False)
        with open(base + "_score.json", "w", encoding="utf-8") as fh:
            json.dump({"calls": client.calls, "result": res}, fh, indent=1)
        with open(base + "_trace.json", "w", encoding="utf-8") as fh:
            json.dump(traces, fh, indent=1)
        sys.stderr.write(f"  [{tag} {budget} run {r}] macro="
                         f"{res['macro_exact_match']:.3f} "
                         f"per_case={res['per_case_rate']} "
                         f"calls={client.total_calls()}\n")
    return macros, details


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--items", default="items.json")
    ap.add_argument("--key", default="visible_key.json")
    ap.add_argument("--budgets", default="1x,3x,10x")
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--outdir", default="runs/ablation")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--arms", default="", help="comma list of arm names")
    ap.add_argument("--plan", default="focused",
                    help="focused (default: each arm at the budgets where its "
                         "component can act) | full (every arm x every budget)")
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()

    items = json.load(open(a.items, encoding="utf-8"))
    if a.limit:
        items = items[:a.limit]
    key = json.load(open(a.key, encoding="utf-8"))
    key = {k: v for k, v in key.items() if k in {i["id"] for i in items}}
    budgets = [b.strip() for b in a.budgets.split(",") if b.strip()]
    arms = ARMS
    if a.arms:
        want = {x.strip() for x in a.arms.split(",")}
        arms = [x for x in ARMS if x[0] in want]
    os.makedirs(a.outdir, exist_ok=True)

    table = {}
    t0 = time.time()
    for name, spec, blurb in arms:
        comps = parse_components(spec)
        for b in budgets:
            if name in ONLY_MULTI and b == "1x":
                table[(name, b)] = ("=full", None)
                continue
            if a.plan == "focused" and b not in FOCUSED.get(name, budgets):
                table[(name, b)] = ("skipped", None)
                continue
            macros, details = cell(items, key, b, comps, a.outdir,
                                   name.replace("-", "no_"), a.runs, a.workers)
            table[(name, b)] = (macros, details)
    sys.stderr.write(f"\nablation done in {time.time() - t0:.0f}s\n")

    lines = ["# Ablation",
             "",
             f"items: `{a.items}` ({len(items)})  |  runs per cell: {a.runs}"
             f"  |  plan: `{a.plan}`  |  headline: macro exact match",
             "",
             "A cell reading `--` was not run at that budget under the "
             "`focused` plan; see the note in `ablate.py`. `= full` means the "
             "arm is identical to the full system there by construction.",
             "",
             "| arm | " + " | ".join(f"{b}" for b in budgets) + " | what it does |",
             "|---|" + "---|" * len(budgets) + "---|"]
    for name, spec, blurb in arms:
        cells = []
        for b in budgets:
            m, _d = table[(name, b)]
            if m == "=full":
                cells.append("_= full_")
            elif m == "skipped":
                cells.append("--")
            elif a.runs > 1:
                cells.append(f"{statistics.mean(m):.3f} ± "
                             f"{statistics.pstdev(m):.3f}")
            else:
                cells.append(f"{m[0]:.3f}")
        lines.append(f"| `{name}` | " + " | ".join(cells) + f" | {blurb} |")

    lines += ["", "## Per-case rates", "",
              "| arm | budget | unique | ambiguous | inconsistent | "
              "amb_partial | inc_label_only |", "|---|---|---|---|---|---|---|"]
    for name, spec, blurb in arms:
        for b in budgets:
            m, d = table[(name, b)]
            if d is None:
                continue
            r = d[0]
            pc = r["per_case_rate"]
            lines.append(
                f"| `{name}` | {b} | {pc['unique']} | {pc['ambiguous']} | "
                f"{pc['inconsistent']} | {r['ambiguous_partial']} | "
                f"{r['inconsistent_label_only']} |")

    lines += ["", "## Confusion, full system", ""]
    for b in budgets:
        m, d = table[("full", b)]
        if d is None:
            continue
        lines += [f"**{b}** (rows: true case, columns: declared)", "",
                  "| true \\ declared | unique | ambiguous | inconsistent | "
                  "unparsed |", "|---|---|---|---|---|"]
        for t, row in d[0]["confusion"].items():
            lines.append(f"| {t} | {row['unique']} | {row['ambiguous']} | "
                         f"{row['inconsistent']} | {row['unparsed']} |")
        lines.append("")

    out = os.path.join(a.outdir, "ablation.md")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    sys.stderr.write(f"wrote {out}\n")


if __name__ == "__main__":
    main()
