"""Why resampling does not help: are the errors systematic or stochastic?

This is the measurement behind the plateau. For every line of every item,
compare the five independent extractions in a recorded 5-pass log against the
reference parser and sort the line into one of four buckets:

  all right        every pass got it
  all wrong, agreed    every pass gave the SAME wrong answer
  all wrong, split     every pass wrong, but not on the same thing
  mixed            some passes right, some wrong

Only the last two buckets are recoverable by resampling. The first "all wrong,
agreed" bucket is a wall: no number of extra calls touches it, because the
model is not being noisy, it is being consistently mistaken.

    python3 dev/check_error_structure.py runs/p5_calls.json
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

passes = collections.defaultdict(list)
for rec in log:
    passes[rec["item"]].append(rec["reply"])

bucket = collections.Counter()
agreed_wrong = collections.Counter()

for iid, replies in passes.items():
    it = items[iid]
    people, blocks, stations, holders = parse_header(it["text"])
    prob = Problem(people, blocks, stations, holders)
    lines = body_lines(it["text"])
    ref = {i: (tag, c) for i, (_l, tag, c) in
           enumerate(parse_item(it)["tags"])}
    got = [parse_codes(r, len(lines), prob)[0] for r in replies]
    for i in range(len(lines)):
        tag, want = ref.get(i, ("?", None))
        truth = want if tag == "hard" else None
        answers = [g.get(i) for g in got]
        right = [a == truth for a in answers]
        if all(right):
            bucket["all right"] += 1
        elif not any(right):
            if len(set(answers)) == 1:
                bucket["all wrong, agreed"] += 1
                kind = (answers[0][0] if answers[0] else "NONE",
                        truth[0] if truth else "inert")
                agreed_wrong[kind] += 1
            else:
                bucket["all wrong, split"] += 1
        else:
            bucket["mixed"] += 1

tot = sum(bucket.values())
print(f"{len(passes)} items, {len(next(iter(passes.values())))} passes each, "
      f"{tot} line-judgements\n")
for k in ("all right", "all wrong, agreed", "all wrong, split", "mixed"):
    print(f"  {k:20s} {bucket[k]:5d}  {bucket[k]/tot:6.1%}")
rec = bucket["mixed"] + bucket["all wrong, split"]
print(f"\n  recoverable by resampling at all: {rec/tot:.1%} of lines")
print(f"  hard wall (same wrong answer every time): "
      f"{bucket['all wrong, agreed']/tot:.1%}")

# The item-level consequence, which is the number that explains the plateau.
# An item scores only if its whole reading is right, so a single permanently-
# wrong line loses it however many calls are spent on it.
walls = collections.Counter()
for iid, replies in passes.items():
    it = items[iid]
    people, blocks, stations, holders = parse_header(it["text"])
    prob = Problem(people, blocks, stations, holders)
    lines = body_lines(it["text"])
    ref = {i: (tag, c) for i, (_l, tag, c) in enumerate(parse_item(it)["tags"])}
    got = [parse_codes(r, len(lines), prob)[0] for r in replies]
    n = 0
    for i in range(len(lines)):
        tag, want = ref.get(i, ("?", None))
        truth = want if tag == "hard" else None
        answers = [g.get(i) for g in got]
        if not any(a == truth for a in answers) and len(set(answers)) == 1:
            n += 1
    walls[n] += 1
clean = walls[0] / len(passes)
print(f"\nitems with no permanently-wrong line: {walls[0]}/{len(passes)} "
      f"= {clean:.1%}")
print(f"  -- the ceiling no amount of resampling can pass: {clean:.2f} macro")
print(f"  walls per item: {dict(sorted(walls.items()))}")

print("\nthe agreed-wrong lines, by (what it said -> what it is), top 10")
for (said, truth), n in agreed_wrong.most_common(10):
    print(f"  said {said:9s} truth {truth:9s} {n}")
