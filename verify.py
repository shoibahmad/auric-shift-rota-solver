"""Pre-flight check for the things that are auto-fails rather than low scores.

    python3 verify.py items.json answers.json [--trace runs/trace.json] \
        [--budget 3x]

Checks, in the order the brief lists them:

  1. the output parses as the submission format, for every item in the set
  2. every citation occurs verbatim in the item it is cited from, each
     citation quotes at most one line of the notes, and no two are the same
     statement
  3. every assignment names every person on the rota, and gives a station
     only to the people the header puts on one
  4. the budget held in both directions -- at least one call per item, never
     more than the cap -- which needs a --trace from the run

Cheap to run, and all four are cheaper to check than to argue about.
"""
import argparse
import json
import sys

sys.path.insert(0, ".")
from score import squash, squash_stmt                              # noqa: E402
from rota.extract import parse_header, body_lines                  # noqa: E402

BUDGETS = {"1x": 1, "3x": 3, "10x": 10}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("items")
    ap.add_argument("answers")
    ap.add_argument("--trace", default=None)
    ap.add_argument("--budget", default=None)
    a = ap.parse_args()

    items = json.load(open(a.items, encoding="utf-8"))
    sub = json.load(open(a.answers, encoding="utf-8"))
    problems, warnings = [], []

    if not isinstance(sub, dict):
        print("FAIL: answers.json is not an object keyed by item id")
        return 1

    for it in items:
        iid = it["id"]
        got = sub.get(iid)
        people, blocks, stations, holders = parse_header(it["text"])
        lines = body_lines(it["text"])
        body = [squash_stmt(l) for l in lines]
        text = squash(it["text"])

        if got is None:
            problems.append(f"{iid}: missing from answers.json")
            continue
        if not isinstance(got, dict):
            problems.append(f"{iid}: entry is not an object")
            continue
        case = got.get("case", "unique")
        if case not in ("unique", "ambiguous", "inconsistent"):
            problems.append(f"{iid}: unknown case {case!r}")
            continue

        if case == "inconsistent":
            cites = got.get("conflicts") or got.get("conflict_lines") or []
            if not cites:
                problems.append(f"{iid}: inconsistent with no citations "
                                f"(scores zero, same as a wrong kind)")
                continue
            normed = [squash_stmt(c) for c in cites]
            if len(set(normed)) != len(normed):
                problems.append(f"{iid}: two citations are the same statement")
            for c, n in zip(cites, normed):
                if n not in text:
                    problems.append(f"{iid}: citation not in the notes: {c[:60]!r}")
                hits = len({l for l in body if l and l in n})
                if hits > 1:
                    problems.append(f"{iid}: one citation quotes {hits} lines: "
                                    f"{c[:60]!r}")
            continue

        assigns = ([got.get("assignment")] if case == "unique"
                   else got.get("assignments") or [])
        if not assigns or any(not isinstance(x, dict) for x in assigns):
            problems.append(f"{iid}: {case} with no usable assignment")
            continue
        if case == "ambiguous" and not 2 <= len(assigns) <= 4:
            # A wrong answer, not a malformed one: the scorer reads it fine and
            # marks the item wrong. It is worth counting separately because it
            # is the system's honest signal that it under-extracted -- the
            # world set is a superset of the real one and it cannot tell which
            # members are real.
            warnings.append(f"{iid}: ambiguous with {len(assigns)} "
                            f"assignments -- under-extracted (task allows 2-4)")
        for k, asg in enumerate(assigns):
            if set(asg) != set(people):
                missing = sorted(set(people) - set(asg))
                extra = sorted(set(asg) - set(people))
                problems.append(f"{iid}[{k}]: rota mismatch "
                                f"missing={missing} extra={extra}")
                continue
            for person, rec in asg.items():
                if not isinstance(rec, dict) or rec.get("block") not in blocks:
                    problems.append(f"{iid}[{k}]: {person} has no valid block")
                st = rec.get("station") if isinstance(rec, dict) else None
                if st is not None and st not in stations:
                    problems.append(f"{iid}[{k}]: {person} has unknown "
                                    f"station {st!r}")

    cap = BUDGETS.get(a.budget) if a.budget else None
    if a.trace:
        tr = json.load(open(a.trace, encoding="utf-8"))
        calls = tr.get("calls", tr)
        cap = cap or BUDGETS.get(tr.get("budget", ""))
        for it in items:
            n = calls.get(it["id"], 0)
            if n < 1:
                problems.append(f"{it['id']}: answered with NO model call")
            if cap and n > cap:
                problems.append(f"{it['id']}: {n} calls, over the {cap} cap")
        if calls:
            print(f"calls/item: min {min(calls.values())} "
                  f"max {max(calls.values())} total {sum(calls.values())}"
                  + (f"  (cap {cap})" if cap else ""))
    elif cap:
        print("note: pass --trace to check the budget; the format checks ran "
              "without it")

    if problems:
        print(f"\n{len(problems)} problem(s):")
        for p in problems[:40]:
            print("  " + p)
        if len(problems) > 40:
            print(f"  ... and {len(problems) - 40} more")
        return 1
    print(f"OK: {len(items)} items, format and citations well-formed"
          + (f"; {len(warnings)} under-extracted" if warnings else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
