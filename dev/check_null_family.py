"""DEV ONLY. How costly is it to over-read the 'open question' family?

The model turned "there was some disagreement about whether Nadia had 15:00"
into NOT_BLOCK Nadia 15:00. The wish family was 100% entailed, so reading it
is free. Is the same true here, or does this family actively mislead?
"""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dev.refparse import parse_item, strip_prefixes, parse_header  # noqa: E402
from rota.solver import Problem                                    # noqa: E402
import re                                                          # noqa: E402

items = json.load(open("items.json"))

NULLPAT = [
    (r"There was some disagreement about whether (?P<p>\w+) had (?P<b>\d\d:\d\d)\.", "either"),
    (r"Nobody could remember whether (?P<p>\w+) was down for the (?P<b>\d\d:\d\d) block\.", "either"),
    (r"The question of (?P<p>\w+) on (?P<b>\d\d:\d\d) was left open in the handover\.", "either"),
    (r"(?P<p>\w+) and the (?P<b>\d\d:\d\d) block came up, but nothing was minuted\.", "either"),
]

pos_true = neg_true = both = total = 0
for it in items:
    hard = parse_item(it, include=("hard",))
    prob = Problem(hard["names"], hard["blocks"], hard["stations"], hard["holders"])
    worlds = prob.solve([c for _l, c in hard["cons"]])
    if not worlds:
        continue
    for line, tag, _c in parse_item(it)["tags"]:
        if tag != "null":
            continue
        s = strip_prefixes(line)
        for pat, _ in NULLPAT:
            m = re.match("^" + pat + "$", s, re.I)
            if not m:
                continue
            total += 1
            p, b = m["p"], m["b"]
            on = all(prob._holds(("block", p, b), w[0], w[1]) for w in worlds)
            off = all(prob._holds(("nblock", p, b), w[0], w[1]) for w in worlds)
            pos_true += on
            neg_true += off
            both += (not on and not off)

print(f"'open question' lines in consistent items: {total}")
print(f"  entailed as BLOCK     (reading it positively is free): {pos_true}")
print(f"  entailed as NOT_BLOCK (reading it negatively is free): {neg_true}")
print(f"  genuinely undetermined (either reading changes the answer): {both}")
