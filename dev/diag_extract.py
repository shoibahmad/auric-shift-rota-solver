"""DEV ONLY. Per-line extraction diagnosis against the reference parser.

Reads a --calls-log written by rota.main and reports, per line family, how
often the model produced the constraint the reference parser produces. This is
the measurement that drove every prompt change.
"""
import json
import sys
import os
import collections

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dev.refparse import parse_item                                  # noqa: E402
from rota.extract import parse_header, body_lines, parse_codes       # noqa: E402
from rota.solver import Problem                                      # noqa: E402

# Model output can contain any character; the Windows console codepage
# cannot. Printing a raw reply must not crash a measurement script.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass
log = json.load(open(sys.argv[1], encoding="utf-8"))
items = {i["id"]: i for i in json.load(open("items.json", encoding="utf-8"))}

# first reply per item = the full extraction pass
first = {}
for rec in log:
    first.setdefault(rec["item"], rec)

hit = collections.Counter()
tot = collections.Counter()
errs = collections.defaultdict(list)
trunc = []

for iid, rec in sorted(first.items()):
    it = items[iid]
    people, blocks, stations, holders = parse_header(it["text"])
    prob = Problem(people, blocks, stations, holders)
    lines = body_lines(it["text"])
    got, raw = parse_codes(rec["reply"], len(lines), prob)
    ref = {}
    for i, (line, tag, c) in enumerate(parse_item(it)["tags"]):
        ref[i] = (tag, c)
    n_emitted = len({i for i in range(len(lines))
                     if i in raw})
    if n_emitted < len(lines):
        trunc.append((iid, n_emitted, len(lines)))
    for i in range(len(lines)):
        tag, c = ref[i]
        fam = tag if tag != "hard" else c[0]
        tot[fam] += 1
        want = c if tag == "hard" else None
        if got.get(i) == want:
            hit[fam] += 1
        else:
            errs[fam].append((iid, lines[i][:88], want, got.get(i),
                              raw.get(i)))

print(f"items: {len(first)}")
print(f"\nreplies that did not cover every line: {len(trunc)}")
for iid, n, m in trunc[:12]:
    print(f"  {iid}: {n}/{m} lines answered")

print("\nper-family exact agreement with the reference parser")
order = sorted(tot, key=lambda f: -tot[f])
for fam in order:
    print(f"  {fam:10s} {hit[fam]:4d}/{tot[fam]:4d} = {hit[fam]/tot[fam]:6.1%}")
print(f"  {'TOTAL':10s} {sum(hit.values()):4d}/{sum(tot.values()):4d} = "
      f"{sum(hit.values())/sum(tot.values()):6.1%}")

print("\nmisses by family (up to 4 each)")
for fam in order:
    if not errs[fam]:
        continue
    print(f"\n-- {fam} --")
    for iid, line, want, gotc, rawc in errs[fam][:4]:
        print(f"  {iid} {line!r}")
        print(f"     want={want}  got={gotc}  raw={rawc!r}")
