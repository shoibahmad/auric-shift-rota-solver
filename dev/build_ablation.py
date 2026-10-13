"""Assemble ABLATION.md from the ablation run and the replay run.

Substitutes the two generated tables into the placeholders in ABLATION.md so
the published document is never hand-typed out of a log.

    python3 dev/build_ablation.py --outdir runs/ablation \
        --replay runs/replay_table.md
"""
import argparse
import collections
import glob
import io
import json
import os
import re
import statistics

ARM_ORDER = ["full", "no_solver", "no_mus", "no_rules", "no_calib",
             "no_softneg", "no_vote", "no_repair", "no_recover", "no_strict"]
PRETTY = {"full": "full", "no_solver": "-solver", "no_mus": "-mus",
          "no_rules": "-rules", "no_calib": "-calib",
          "no_softneg": "-softneg", "no_vote": "-vote",
          "no_repair": "-repair", "no_recover": "-recover",
          "no_strict": "-strict"}
BLURB = {
    "full": "every component on",
    "no_solver": "no formal layer: the model is asked for the answer",
    "no_mus": "cite every constraining line, not a minimal core",
    "no_rules": "extraction prompt without the inert-family rules",
    "no_calib": "no calibrated drop on a too-small conflict (free, no call)",
    "no_softneg": "no soft negatives on missed name+time lines (free, no call)",
    "no_vote": "no re-extraction and selection",
    "no_repair": "no count-triggered targeted re-reads",
    "no_recover": "no free re-parse of dropped codes",
    "no_strict": "accept codes the validator drops, by fuzzy name matching",
}
BUDGETS = ["1x", "3x", "10x"]


def load(outdir):
    cells = collections.defaultdict(list)
    for p in sorted(glob.glob(os.path.join(outdir, "*_score.json"))):
        m = re.match(r"(.+?)_(1x|3x|10x)_r(\d+)_score\.json$",
                     os.path.basename(p))
        if not m:
            continue
        d = json.load(io.open(p, encoding="utf-8"))
        cells[(m.group(1), m.group(2))].append(d)
    return cells


def fmt(vals):
    if not vals:
        return "--"
    if len(vals) == 1:
        return f"{vals[0]:.3f}"
    return f"{statistics.mean(vals):.3f} +/- {statistics.pstdev(vals):.3f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default="runs/ablation")
    ap.add_argument("--replay", default="runs/replay_table.md")
    ap.add_argument("--template", default="ABLATION.template.md")
    ap.add_argument("--target", default="ABLATION.md")
    a = ap.parse_args()

    cells = load(a.outdir)
    arms = [x for x in ARM_ORDER if any(k[0] == x for k in cells)]
    runs = max((len(v) for v in cells.values()), default=0)

    out = [f"Three runs per cell unless noted; **mean +/- population standard "
           f"deviation** of macro exact match. Highest run count seen: {runs}.",
           "",
           "| arm | 1x | 3x | 10x | what it does |",
           "|---|---|---|---|---|"]
    for arm in arms:
        row = []
        for b in BUDGETS:
            v = [d["result"]["macro_exact_match"] for d in cells.get((arm, b), [])]
            row.append(fmt(v) if v else "--")
        out.append(f"| `{PRETTY[arm]}` | " + " | ".join(row)
                   + f" | {BLURB.get(arm, '')} |")

    out += ["", "### Per-kind rates and the two diagnostics", "",
            "| arm | budget | unique | ambiguous | inconsistent | "
            "amb_partial | inc_label_only | calls/item |",
            "|---|---|---|---|---|---|---|---|"]
    for arm in arms:
        for b in BUDGETS:
            ds = cells.get((arm, b), [])
            if not ds:
                continue
            mean = lambda f: statistics.mean(f(d) for d in ds)      # noqa: E731
            pc = lambda k: mean(lambda d: d["result"]["per_case_rate"][k] or 0)
            calls = [v for d in ds for v in d["calls"].values()]
            out.append(
                f"| `{PRETTY[arm]}` | {b} | {pc('unique'):.2f} | "
                f"{pc('ambiguous'):.2f} | {pc('inconsistent'):.2f} | "
                f"{mean(lambda d: d['result']['ambiguous_partial'] or 0):.2f} | "
                f"{mean(lambda d: d['result']['inconsistent_label_only'] or 0):.2f} | "
                f"{min(calls)}-{max(calls)} |")

    out += ["", "### Confusion matrix, full system", "",
            "Rows are the true kind, columns what was declared. Summed over "
            "the three runs, so each row totals 60.", ""]
    for b in BUDGETS:
        ds = cells.get(("full", b), [])
        if not ds:
            continue
        agg = collections.defaultdict(collections.Counter)
        for d in ds:
            for t, row in d["result"]["confusion"].items():
                agg[t].update(row)
        out += [f"**{b}**", "",
                "| true \\ declared | unique | ambiguous | inconsistent | unparsed |",
                "|---|---|---|---|---|"]
        for t in ("unique", "ambiguous", "inconsistent"):
            r = agg[t]
            out.append(f"| {t} | {r['unique']} | {r['ambiguous']} | "
                       f"{r['inconsistent']} | {r['unparsed']} |")
        out.append("")

    live = "\n".join(out)
    replay = ""
    if os.path.exists(a.replay):
        replay = io.open(a.replay, encoding="utf-8").read().strip()
        replay = "\n".join(l for l in replay.splitlines()
                           if not l.startswith("replaying "))

    # always built from the tracked template, never from the last output, so
    # running this twice cannot double-substitute or lose the placeholders
    doc = io.open(a.template, encoding="utf-8").read()
    # the template's "edit this file, not the generated one" banner is for
    # whoever opens the template; it must not survive into the output, where
    # it would be telling the reader the opposite of what it means
    doc = re.sub(r"\A<!--\s*SOURCE FILE.*?-->\s*", "", doc, flags=re.S)
    doc = doc.replace("<!-- LIVE_TABLE -->", live)
    doc = doc.replace("<!-- REPLAY_TABLE -->", replay)
    io.open(a.target, "w", encoding="utf-8", newline="\n").write(doc)
    print(f"wrote {a.target}: {len(arms)} arms, "
          f"{sum(len(v) for v in cells.values())} cells")


if __name__ == "__main__":
    main()
