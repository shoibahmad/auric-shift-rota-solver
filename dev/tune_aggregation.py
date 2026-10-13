"""DEV ONLY. How should several extractions of one item be combined?

This is the question the curve turned on. Three aggregation rules, replayed
offline over a recorded multi-pass log so every rule sees exactly the same
model output:

  merge     per-line majority, then solve the merge          (first design)
  verdict   each pass solved separately, majority on the verdict (second)
  union     take every constraint the passes agree on wherever any of them
            speaks, and use it if the result is satisfiable      (third)

    python3 dev/tune_aggregation.py fixtures/extraction_3pass.json
    python3 dev/tune_aggregation.py fixtures/extraction_5pass.json
"""
import json
import sys
import os
import collections

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
COMPS = dict(P.DEFAULT_COMPONENTS)


# The two rejected aggregation designs, kept here rather than in the shipped
# module so the comparison in the writeup stays reproducible without leaving
# dead code in the pipeline.

def merge_votes(passes, n_lines):
    """Design 1: per-line majority over the extractions, then solve the merge.
    Abstentions count as votes for NONE."""
    out = {}
    for i in range(n_lines):
        counts = collections.Counter(p.get(i) for p in passes)
        best, n = counts.most_common(1)[0]
        if best is not None:
            out[i] = best
            continue
        alt = [(v, c) for v, c in counts.items() if v is not None]
        if alt:
            v, c = max(alt, key=lambda x: x[1])
            if c * 2 >= len(passes):
                out[i] = v
    return out


def vote_verdicts(cands):
    """Design 2: majority on the finished verdict, ties to the more
    constrained reading."""
    if not cands:
        return None
    cases = collections.Counter(c[0] for c in cands)
    order = {"inconsistent": 0, "unique": 1, "ambiguous": 2}
    best_case = min(cases, key=lambda k: (-cases[k], order[k]))
    pool = [c for c in cands if c[0] == best_case]
    sigs = collections.Counter(c[1] for c in pool)
    best_sig = max(sigs, key=lambda s: (sigs[s], -len(str(s))))
    for c in pool:
        if c[1] == best_sig:
            return c
    return pool[0]


def passes_by_item(log, items):
    """Every full-item extraction recorded for each item, in order."""
    out = collections.defaultdict(list)
    byid = {i["id"]: i for i in items}
    for rec in log:
        it = byid.get(rec["item"])
        if it is None:
            continue
        people, blocks, stations, holders = parse_header(it["text"])
        prob = Problem(people, blocks, stations, holders)
        lines = body_lines(it["text"])
        # only full passes, not focused re-reads: a focused reply mentions
        # fewer lines than the item has
        cons, raw = parse_codes(rec["reply"], len(lines), prob)
        out[rec["item"]].append(cons)
    return out


def union_merge(passes, n_lines):
    """Every constraint the passes agree on, wherever any of them speaks.

    A line that one pass read as a constraint and the others skipped is taken,
    because under-extraction is the dominant error: a missed line is far more
    likely than an invented one. A line two passes read *differently* is
    contested and goes to a majority among the readings offered.
    """
    out = {}
    for i in range(n_lines):
        offered = [p.get(i) for p in passes if p.get(i) is not None]
        if not offered:
            continue
        counts = collections.Counter(offered)
        best, n = counts.most_common(1)[0]
        if len(counts) == 1 or n * 2 > len(offered):
            out[i] = best
    return out


def answer(prob, lines, cons):
    v = P.verdict(prob, cons, lines, COMPS)
    case, _sig, worlds, core, _c = v
    if case == "unique":
        return {"case": "unique", "assignment": prob.render(worlds[0])}
    if case == "ambiguous":
        return {"case": "ambiguous",
                "assignments": [prob.render(w) for w in worlds[:P.RENDER_CAP]]}
    return {"case": "inconsistent",
            "conflicts": [lines[i] for i in (core or [])]}


def run(items, byitem, rule, k=None):
    out = {}
    for it in items:
        people, blocks, stations, holders = parse_header(it["text"])
        prob = Problem(people, blocks, stations, holders)
        lines = body_lines(it["text"])
        ps = byitem.get(it["id"], [])
        if k:
            ps = ps[:k]
        if not ps:
            out[it["id"]] = {"case": "unique", "assignment": {}}
            continue
        if rule == "single":
            out[it["id"]] = answer(prob, lines, ps[0])
        elif rule == "merge":
            out[it["id"]] = answer(prob, lines,
                                   merge_votes(ps, len(lines)))
        elif rule == "verdict":
            cands = [P.verdict(prob, p, lines, COMPS) for p in ps]
            cands.append(P.verdict(prob, merge_votes(ps, len(lines)),
                                   lines, COMPS))
            case, _s, worlds, core, cons = vote_verdicts(cands)
            out[it["id"]] = answer(prob, lines, cons)
        elif rule == "union":
            u = union_merge(ps, len(lines))
            if prob.sat(list(u.values())):
                out[it["id"]] = answer(prob, lines, u)
            else:
                cands = [P.verdict(prob, p, lines, COMPS) for p in ps]
                cands.append(P.verdict(prob, u, lines, COMPS))
                case, _s, worlds, core, cons = vote_verdicts(cands)
                out[it["id"]] = answer(prob, lines, cons)
        elif rule == "pick-rank":
            # select, do not merge: keep whichever single pass lands closest to
            # a world count the task actually permits
            cands = [P.verdict(prob, p, lines, COMPS) for p in ps]
            best = min(cands, key=lambda v: P.rank(len(v[2])))
            out[it["id"]] = answer(prob, lines, best[4])
        elif rule == "pick-fewest":
            # prefer the most decided satisfiable pass; fall back to the
            # verdict vote when every pass is contradictory
            cands = [P.verdict(prob, p, lines, COMPS) for p in ps]
            sat = [v for v in cands if v[2]]
            if sat:
                best = min(sat, key=lambda v: len(v[2]))
            else:
                best = vote_verdicts(cands)
            out[it["id"]] = answer(prob, lines, best[4])
        elif rule == "pick-rank-vote":
            # select among the passes that are individually plausible, then
            # let those agree with each other: consensus restricted to the
            # candidates that are not already provably wrong
            cands = [P.verdict(prob, p, lines, COMPS) for p in ps]
            best_rank = min(P.rank(len(v[2])) for v in cands)
            pool = [v for v in cands if P.rank(len(v[2])) == best_rank]
            chosen = vote_verdicts(pool)
            out[it["id"]] = answer(prob, lines, chosen[4])
        elif rule == "intersect":
            inter = {}
            for i in range(len(lines)):
                vals = [p.get(i) for p in ps]
                if vals and all(v == vals[0] and v is not None for v in vals):
                    inter[i] = vals[0]
            out[it["id"]] = answer(prob, lines, inter)
    return out


if __name__ == "__main__":
    log = json.load(open(sys.argv[1], encoding="utf-8"))
    items = json.load(open("items.json", encoding="utf-8"))
    key = json.load(open("visible_key.json", encoding="utf-8"))
    byitem = passes_by_item(log, items)
    npass = collections.Counter(len(v) for v in byitem.values())
    print(f"{sys.argv[1]}: passes per item {dict(sorted(npass.items()))}\n")
    maxk = max(npass)
    # how much does one pass vary? the spread bounds every merge rule
    print("  individual passes:")
    for j in range(maxk):
        sub = {}
        for it in items:
            ps = byitem.get(it["id"], [])
            if len(ps) <= j:
                continue
            people, blocks, stations, holders = parse_header(it["text"])
            prob = Problem(people, blocks, stations, holders)
            sub[it["id"]] = answer(prob, body_lines(it["text"]), ps[j])
        r = score(key, sub, items)
        pc = r["per_case_rate"]
        print(f"    pass {j + 1}      macro={r['macro_exact_match']:.4f}  "
              f"u={pc['unique']:.2f} a={pc['ambiguous']:.2f} "
              f"i={pc['inconsistent']:.2f}")
    print()
    for rule in ("single", "merge", "verdict", "union", "pick-rank",
                 "pick-rank-vote", "pick-fewest", "intersect"):
        for k in sorted({1, 3, maxk}):
            if k > maxk or (rule == "single" and k > 1):
                continue
            sub = run(items, byitem, rule, k)
            r = score(key, sub, items)
            pc = r["per_case_rate"]
            print(f"  {rule:8s} k={k:<2d} macro={r['macro_exact_match']:.4f}  "
                  f"u={pc['unique']:.2f} a={pc['ambiguous']:.2f} "
                  f"i={pc['inconsistent']:.2f}")
