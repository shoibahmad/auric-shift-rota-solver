"""Measure the symbolic components exactly, by replay instead of re-running.

Five of the ten ablation arms change only code that runs *after* the model has
spoken: `mus`, `calib`, `softneg`, `recover`, `strict`. For those, a live
re-run is strictly worse evidence than a replay -- it pays for new calls and
then adds sampling noise on top, and at temperature 1.0 that noise (+/-0.05
macro, and 0.15 between individual passes) is larger than several of the
effects being measured.

This replays recorded extractions through the real pipeline functions with one
component switched off, so every arm sees literally the same model output. The
live table in ABLATION.md is what the graders re-run; this one is what the
component claims in the writeup rest on.

    python3 dev/replay.py runs/v3_1x_calls.json fixtures/extraction_1x.json ...
"""
import json
import sys
import os
import statistics

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rota.extract import parse_header, body_lines, parse_codes      # noqa: E402
from rota.solver import Problem                                     # noqa: E402
from rota import pipeline as P                                      # noqa: E402
from score import score                                             # noqa: E402

# Model output can contain any character; the Windows console codepage
# cannot. Printing a raw reply must not crash a measurement script.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass
# The fifth arm drops both free repairs at once, to check whether their solo
# deltas can be added. They can: -0.021 and -0.058 separately, -0.079
# together, so the two act on disjoint sets of items despite both being
# triggered by an implausible world count. Measured, not assumed -- the
# expectation going in was that they would overlap.
SYMBOLIC_ARMS = ["full", "-mus", "-calib", "-softneg",
                 "-calib,-softneg", "-recover", "-strict"]


def replay(items, log, comps):
    """Answers for every item, from the first recorded reply per item."""
    first = {}
    for rec in log:
        first.setdefault(rec["item"], rec)
    out = {}
    for it in items:
        iid = it["id"]
        people, blocks, stations, holders = parse_header(it["text"])
        prob = Problem(people, blocks, stations, holders)
        lines = body_lines(it["text"])
        rec = first.get(iid)
        if rec is None:
            out[iid] = {"case": "unique", "assignment": {}}
            continue
        cons, raw = parse_codes(rec["reply"], len(lines), prob)
        if not comps["strict"]:
            cons = dict(cons)
            cons.update(P._lenient(raw, cons, prob))
        if comps["recover"] and len(prob.solve(list(cons.values()))) > P.AMBIG_MAX:
            cons = P._recover(raw, cons, prob, lines)
        case, _sig, worlds, core, _c = P.verdict(prob, cons, lines, comps)
        if case == "unique":
            out[iid] = {"case": "unique", "assignment": prob.render(worlds[0])}
        elif case == "ambiguous":
            out[iid] = {"case": "ambiguous",
                        "assignments": [prob.render(w)
                                        for w in worlds[:P.RENDER_CAP]]}
        else:
            out[iid] = {"case": "inconsistent",
                        "conflicts": [lines[i] for i in (core or [])]}
    return out


def comps_for(arm):
    c = dict(P.DEFAULT_COMPONENTS)
    if arm != "full":
        for name in arm.split(","):
            c[name.strip().lstrip("-")] = False
    return c


if __name__ == "__main__":
    logs = sys.argv[1:] or ["runs/v3_1x_calls.json"]
    items = json.load(open("items.json", encoding="utf-8"))
    key = json.load(open("visible_key.json", encoding="utf-8"))

    print(f"replaying {len(logs)} recorded 1x extraction(s) through the "
          f"symbolic layer\n")
    print(f"| arm | macro (mean of {len(logs)}) | unique | ambiguous | "
          f"inconsistent | vs full |")
    print("|---|---|---|---|---|---|")
    base = None
    for arm in SYMBOLIC_ARMS:
        comps = comps_for(arm)
        macros, pcs = [], []
        for path in logs:
            log = json.load(open(path, encoding="utf-8"))
            r = score(key, replay(items, log, comps), items)
            macros.append(r["macro_exact_match"])
            pcs.append(r["per_case_rate"])
        m = statistics.mean(macros)
        sd = statistics.pstdev(macros) if len(macros) > 1 else 0.0
        avg = {k: statistics.mean(p[k] for p in pcs) for k in
               ("unique", "ambiguous", "inconsistent")}
        if base is None:
            base = m
            delta = "--"
        else:
            delta = f"{m - base:+.3f}"
        spread = f" +/- {sd:.3f}" if len(macros) > 1 else ""
        print(f"| `{arm}` | {m:.3f}{spread} | {avg['unique']:.2f} | "
              f"{avg['ambiguous']:.2f} | {avg['inconsistent']:.2f} | {delta} |")
    print(f"\nlogs: {', '.join(os.path.basename(p) for p in logs)}")
