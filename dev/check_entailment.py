"""DEV ONLY. Is the wish/counterfactual family redundant or load-bearing?

"hard+wish" scored 1.00 on unique and ambiguous but lost 3 inconsistent items.
That pattern says the wish constraints never remove a world -- they are
entailed by the statements that do the work. Worth checking directly, because
if true it means over-extraction of that family is cheap on two kinds out of
three and only damages citation minimality.
"""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dev.refparse import parse_item                      # noqa: E402
from rota.solver import Problem                          # noqa: E402

# Model output can contain any character; the Windows console codepage
# cannot. Printing a raw reply must not crash a measurement script.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass
items = json.load(open("items.json"))
key = json.load(open("visible_key.json"))

tot = {"wish": [0, 0], "past": [0, 0]}
for it in items:
    hard = parse_item(it, include=("hard",))
    prob = Problem(hard["names"], hard["blocks"], hard["stations"], hard["holders"])
    worlds = prob.solve([c for _l, c in hard["cons"]])
    if not worlds:
        continue                      # inconsistent item: nothing to entail
    for fam in ("wish", "past"):
        extra = [c for line, tag, c in parse_item(it)["tags"]
                 if tag == fam and c is not None]
        for c in extra:
            tot[fam][1] += 1
            if all(prob._holds(c, p, s) for p, s in worlds):
                tot[fam][0] += 1

for fam, (ok, n) in tot.items():
    print(f"{fam:5s}: {ok}/{n} constraints hold in EVERY world of the "
          f"hard-only set ({0 if not n else ok / n:.1%})")
