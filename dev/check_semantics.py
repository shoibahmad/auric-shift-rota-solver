"""DEV ONLY. Does the symbolic core + reference parser reproduce the key?

This is how the generator's semantics were pinned down: switch each disputed
line family on and off and see which setting makes the oracle exact.
"""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dev.refparse import parse_item                      # noqa: E402
from rota.solver import Problem, mus                     # noqa: E402
from score import score                                  # noqa: E402

# Model output can contain any character; the Windows console codepage
# cannot. Printing a raw reply must not crash a measurement script.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

def oracle_answers(items, include):
    out = {}
    for it in items:
        p = parse_item(it, include=include)
        prob = Problem(p["names"], p["blocks"], p["stations"], p["holders"])
        indexed = [(i, c) for i, (_line, c) in enumerate(p["cons"])]
        lines = [line for line, _c in p["cons"]]
        worlds = prob.solve([c for _, c in indexed])
        if len(worlds) == 1:
            out[it["id"]] = {"case": "unique",
                             "assignment": prob.render(worlds[0])}
        elif len(worlds) > 1:
            out[it["id"]] = {"case": "ambiguous",
                             "assignments": [prob.render(w) for w in worlds]}
        else:
            core = mus(prob, indexed)
            out[it["id"]] = {"case": "inconsistent",
                             "conflicts": [lines[i] for i in core]}
    return out


def report(tag, items, key, include):
    sub = oracle_answers(items, include)
    r = score(key, sub, items)
    print(f"{tag:28s} macro={r['macro_exact_match']:.4f} "
          f"per_case={r['per_case_rate']} "
          f"inc_label_only={r['inconsistent_label_only']} "
          f"amb_partial={r['ambiguous_partial']}")
    print(f"{'':28s} confusion={json.dumps(r['confusion'])}")
    return sub, r


if __name__ == "__main__":
    items = json.load(open("items.json"))
    key = json.load(open("visible_key.json"))
    for tag, inc in [
        ("hard only", ("hard",)),
        ("hard+wish", ("hard", "wish")),
        ("hard+past", ("hard", "past")),
        ("hard+wish+past", ("hard", "wish", "past")),
    ]:
        report(tag, items, key, inc)
