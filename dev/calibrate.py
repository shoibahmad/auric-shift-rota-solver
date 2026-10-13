"""DEV ONLY. Per-code-kind precision of the extractor.

Not recall -- precision: given that the model emitted a code of kind K, how
often is K (with its arguments) what the line actually says? That is the
number the solver needs, because when an extraction is contradictory the
question is which of the colliding constraints to disbelieve.

    python3 dev/calibrate.py fixtures/extraction_1x.json
"""
import json
import sys
import os
import collections

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dev.refparse import parse_item                               # noqa: E402
from rota.extract import parse_header, body_lines, parse_codes    # noqa: E402
from rota.solver import Problem                                   # noqa: E402

# Model output can contain any character; the Windows console codepage
# cannot. Printing a raw reply must not crash a measurement script.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass
log = json.load(open(sys.argv[1], encoding="utf-8"))
items = {i["id"]: i for i in json.load(open("items.json", encoding="utf-8"))}

first = {}
for rec in log:
    first.setdefault(rec["item"], rec)

emitted = collections.Counter()
correct = collections.Counter()
confuse = collections.Counter()

for iid, rec in first.items():
    it = items[iid]
    people, blocks, stations, holders = parse_header(it["text"])
    prob = Problem(people, blocks, stations, holders)
    lines = body_lines(it["text"])
    got, _raw = parse_codes(rec["reply"], len(lines), prob)
    ref = {i: (tag, c) for i, (_l, tag, c) in
           enumerate(parse_item(it)["tags"])}
    for i, c in got.items():
        tag, want = ref.get(i, ("?", None))
        emitted[c[0]] += 1
        if tag == "hard" and want == c:
            correct[c[0]] += 1
        else:
            truth = want[0] if (tag == "hard" and want) else f"inert/{tag}"
            confuse[(c[0], truth)] += 1

print("precision of each emitted code kind "
      "(emitted -> actually says that)\n")
rows = []
for k in emitted:
    rows.append((correct[k] / emitted[k], k, correct[k], emitted[k]))
for p, k, c, n in sorted(rows):
    print(f"  {k:9s} {c:3d}/{n:3d} = {p:6.1%}")
print(f"\n  overall   {sum(correct.values()):3d}/{sum(emitted.values()):3d} = "
      f"{sum(correct.values())/max(1, sum(emitted.values())):6.1%}")

print("\nwhere a wrong code came from (emitted <- truth), top 14")
for (k, t), n in confuse.most_common(14):
    print(f"  {k:9s} <- {t:16s} {n}")

print("\nsuggested deletion order, least trustworthy first:")
print("  " + ", ".join(f'"{k}"' for _p, k, _c, _n in sorted(rows)))
