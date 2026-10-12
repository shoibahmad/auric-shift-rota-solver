"""DEV ONLY. Re-run the symbolic layer over a saved calls log.

The model's replies are the expensive part and the symbolic layer is free, so
every symbolic component was tuned by replaying one recorded 1x run rather
than by re-querying the endpoint. The extraction is held fixed; only the code
after it changes. That makes the comparison exact as well as cheap -- two
symbolic variants see literally the same model output, with none of the
sampling noise a fresh run at temperature 1.0 would add.

    python3 dev/replay.py runs/fmt_dash_calls.json
"""
import json
import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rota.extract import parse_header, body_lines, parse_codes      # noqa: E402
from rota.solver import Problem, pick_core                          # noqa: E402
from rota import pipeline as P                                      # noqa: E402
from score import score                                             # noqa: E402


def replay(items, log, use_recover, use_calib, use_mus, use_softneg):
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
        worlds = prob.solve(list(cons.values()))

        if use_recover and len(worlds) > P.AMBIG_MAX:
            cons = P._recover(raw, cons, prob, lines)
            worlds = prob.solve(list(cons.values()))
        if use_softneg and len(worlds) > 1:
            cons = soft_negatives(prob, cons, lines)
            worlds = prob.solve(list(cons.values()))
        if use_calib and not worlds:
            cons, dropped = P._calibrated_drop(prob, cons)
            if dropped:
                worlds = prob.solve(list(cons.values()))

        if len(worlds) == 1:
            out[iid] = {"case": "unique", "assignment": prob.render(worlds[0])}
        elif worlds:
            out[iid] = {"case": "ambiguous",
                        "assignments": [prob.render(w) for w
                                        in worlds[:P.RENDER_CAP]]}
        else:
            indexed = [(i, cons[i]) for i in sorted(cons)]
            core = (pick_core(prob, indexed) if use_mus else sorted(cons))
            out[iid] = {"case": "inconsistent",
                        "conflicts": [lines[i] for i in (core or [])]}
    return out


def soft_negatives(prob, cons, lines):
    """Candidate component (under test): a line read as NONE that names a
    person and a clock time is treated as a negative block claim when adding
    it keeps the item satisfiable and removes worlds.

    The rationale: no padding line in this task mentions a clock time, and the
    two inert families that do -- a refused request and an unresolved question
    -- were measured to be entailed as negatives anyway, so reading them that
    way is free. The risk is a *positive* block statement the model missed,
    where the negative reading is actively wrong.
    """
    import re
    TIME = re.compile(r"\b\d{1,2}:\d{2}\b")
    cur = dict(cons)
    base = len(prob.solve(list(cur.values())))
    for i, line in enumerate(lines):
        if i in cur:
            continue
        times = TIME.findall(line)
        names = [p for p in prob.people if p in line]
        if len(times) != 1 or len(names) != 1:
            continue
        cand = ("nblock", names[0], times[0])
        if not prob.valid(cand):
            continue
        trial = dict(cur)
        trial[i] = cand
        n = len(prob.solve(list(trial.values())))
        if n and n < base:
            cur, base = trial, n
    return cur


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--items", default="items.json")
    ap.add_argument("--key", default="visible_key.json")
    a = ap.parse_args()
    items = json.load(open(a.items, encoding="utf-8"))
    key = json.load(open(a.key, encoding="utf-8"))
    log = json.load(open(a.log, encoding="utf-8"))

    variants = [
        ("extraction only",            0, 0, 1, 0),
        ("+ recover",                  1, 0, 1, 0),
        ("+ recover + calib",          1, 1, 1, 0),
        ("+ recover + calib, no mus",  1, 1, 0, 0),
        ("+ recover + calib + softneg", 1, 1, 1, 1),
        ("+ recover + softneg",        1, 0, 1, 1),
    ]
    print(f"replaying {a.log}  ({len({r['item'] for r in log})} items)\n")
    for name, rec, cal, m, sn in variants:
        sub = replay(items, log, rec, cal, m, sn)
        r = score(key, sub, items)
        pc = r["per_case_rate"]
        print(f"  {name:30s} macro={r['macro_exact_match']:.4f}  "
              f"u={pc['unique']:.2f} a={pc['ambiguous']:.2f} "
              f"i={pc['inconsistent']:.2f}")
