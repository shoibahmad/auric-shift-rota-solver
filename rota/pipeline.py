"""Budget-aware orchestration.

One call per item buys a full line-by-line extraction. Everything after that is
the solver telling the extractor where it is probably wrong, and spending the
remaining budget only there.

The signal that makes targeted repair possible is cheap and comes free with an
exhaustive enumerator: the number of worlds consistent with what was extracted.
The brief fixes the shape of a legitimate answer -- an ambiguous item has two
to four worlds -- so a count outside {0} U [1,4] is a proof that the extraction
is wrong, before anything is compared to a key:

    count > 4   a constraint was missed       -> re-read the lines read as NONE
    count == 0  a constraint was invented     -> re-read the lines in the core
    1..4        plausible                     -> spend what is left on voting

Repair is therefore never a retry of the whole item. It is a re-read of the
handful of lines the solver has just proved are carrying the error.
"""
import collections
import re

from .extract import (parse_header, body_lines, build_prompt, parse_codes,
                      parse_one)
from .solver import Problem, mus, pick_core, least_trusted, trust

AMBIG_MAX = 4          # the brief: an ambiguous item has two to four worlds
RENDER_CAP = 24        # keep answers.json sane when extraction collapses

DEFAULT_COMPONENTS = {
    "solver": True,     # symbolic enumeration and case decision
    "rules": True,      # the inert-family guidance in the extraction prompt
    "strict": True,     # drop codes that do not validate, never repair them
    "recover": True,    # free re-parse of dropped codes when under-constrained
    "vote": True,       # self-consistency over repeated extractions
    "repair": True,     # count-triggered targeted re-reads
    "mus": True,        # minimal core citation (vs citing every constraint)
    "calib": True,      # drop a distrusted constraint when the core is too
                        # small to be a real conflict -- free, no model call
    "softneg": True,    # read a missed name+time line as a negative -- free
}

# Reply shape. Not a component -- it is one choice with three settings, kept
# out of the on/off component dict so the ablation arms stay boolean.
FMT = "dash"


def merge_votes(passes, n_lines):
    """{line -> constraint} from several extractions, by per-line majority.

    Voting per line rather than per item is the point: two extractions that
    each get a different line wrong combine into one that gets both right,
    which a vote over whole answers cannot do. It also repairs truncation for
    free -- a line one pass never reached is supplied by another.

    A constraint needs half the passes behind it. Abstentions count as votes
    for NONE, so a line that only one pass in three read as a constraint is
    dropped, which is the safer direction: a missing constraint shows up as an
    impossible world count and can be repaired, an invented one can fake a
    contradiction that looks entirely legitimate.
    """
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


def rank(n_worlds):
    """How plausible is a world count, knowing only what the brief says?

    An item has exactly one world, two to four, or none. A count above four is
    a proof of under-extraction that needs no key to see, so it ranks below
    every count the task permits; among those, fewer is closer to the window.
    """
    return (0, 0) if n_worlds <= AMBIG_MAX else (1, n_worlds)


def verdict(prob, cons, lines, comps):
    """One extraction's finished verdict: (case, signature, worlds, core).

    The signature is what a vote compares -- the rendered world set for a
    satisfiable extraction, the cited core for a contradictory one -- so two
    passes that reach the same answer by different constraint sets count as
    agreeing, which is the agreement that matters.
    """
    cons = dict(cons)
    worlds = prob.solve(list(cons.values()))
    if comps["softneg"] and len(worlds) > 1:
        cons = soft_negatives(prob, cons, lines)
        worlds = prob.solve(list(cons.values()))
    if comps["calib"] and not worlds:
        cons, dropped = _calibrated_drop(prob, cons)
        if dropped:
            worlds = prob.solve(list(cons.values()))
    if worlds:
        case = "unique" if len(worlds) == 1 else "ambiguous"
        sig = frozenset(tuple(sorted(
            (p, f["block"], f.get("station", "")) for p, f in
            prob.render(w).items())) for w in worlds)
        return case, ("sat", len(worlds), sig), worlds, None, cons
    indexed = [(i, cons[i]) for i in sorted(cons)]
    core = pick_core(prob, indexed) if comps["mus"] else sorted(cons)
    return "inconsistent", ("unsat", frozenset(core or ())), [], core, cons


def vote_verdicts(cands):
    """Pick a verdict from several, by majority on the case and then on the
    answer itself.

    Voting on the finished verdict rather than on the constraint set is the fix
    for a real failure: at ten calls an item is extracted five times, and
    per-line majority merging quietly *removes* a constraint that only two
    passes found. When that constraint is the one the contradiction rests on,
    a correctly-detected inconsistent item turns satisfiable, and the 10x
    score came in below the 3x score because of it. A verdict a majority of
    passes reached independently cannot be dissolved that way.

    `cands` is a list of (case, sig, worlds, core, cons). Ties on the case go
    to the more constrained reading -- inconsistent over ambiguous over unique
    -- because the counts that lose a tie are the ones produced by dropping a
    constraint, not by inventing one.
    """
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


class Solved:
    """What the pipeline knows about one item when it stops."""

    def __init__(self, case, worlds, core_idx, cons, lines, calls, trace):
        self.case = case
        self.worlds = worlds
        self.core_idx = core_idx
        self.cons = cons
        self.lines = lines
        self.calls = calls
        self.trace = trace


def _extract_pass(client, item_id, prob, lines, comps, focus=None, fmt=None):
    msgs = build_prompt(prob.people, prob.blocks, prob.stations, prob.holders,
                        lines, focus=focus, fmt=fmt or FMT)
    if not comps["rules"]:
        msgs = _strip_rules(msgs)
    # generous: a single derailed line must not cost the tail of the list
    n = len(focus) if focus is not None else len(lines)
    reply = client.chat(item_id, msgs, max_tokens=250 + 40 * n)
    cons, raw = parse_codes(reply, len(lines), prob)
    if not comps["strict"]:
        cons = dict(cons)
        cons.update(_lenient(raw, cons, prob))
    return cons, raw


def _strip_rules(msgs):
    """Ablation arm: the same prompt without the inert-family guidance."""
    out = []
    for m in msgs:
        c = m["content"]
        if "RULES:" in c:
            head, _, tail = c.partition("RULES:")
            _, _, rest = tail.partition("EXAMPLE")
            c = head + "EXAMPLE" + rest
        out.append({"role": m["role"], "content": c})
    return out


def _lenient(raw, have, prob):
    """Ablation arm: accept codes the strict parser dropped, by snapping each
    unknown token to the closest name or station."""
    import difflib
    extra = {}
    for i, code in raw.items():
        if i in have:
            continue
        toks = code.split()
        fixed = []
        for t in toks:
            t2 = t.strip("<>[]{},.\"'")
            if t2.upper() == t2 and "_" in t2 or t2.isupper():
                fixed.append(t2)
                continue
            pool = list(prob.people) + list(prob.stations) + list(prob.blocks)
            near = difflib.get_close_matches(t2, pool, n=1, cutoff=0.6)
            fixed.append(near[0] if near else t2)
        c = parse_one(" ".join(fixed), prob)
        if c is not None:
            extra[i] = c
    return extra


MIN_CORE = 3           # the brief: every conflicting set here has >= 3 lines
TIME_RE = re.compile(r"\b\d{1,2}:\d{2}\b")


def soft_negatives(prob, cons, lines):
    """Free repair for under-extraction, no model call.

    A line read as asserting nothing, which nonetheless names exactly one
    person and exactly one clock time, is tried as a negative block claim.
    Three measurements make this cheap rather than reckless:

      * no inert line in this task mentions a clock time except the two
        families below, so the filter is nearly specific on its own;
      * a refused request ("lobbied for 11:00 without success") and an
          unresolved question ("nobody could remember whether") were measured
          to be entailed as negatives in every world of every consistent item
          -- 64/64 and 31/31 -- so reading them negatively changes nothing;
      * the candidate is kept only if it removes worlds and leaves at least
        one, so a reading that contradicts the rest of the extraction is
        never adopted.

    What it cannot catch is a *positive* block statement the model missed:
    there the negative reading is actively wrong. That is the price, and it is
    paid rarely enough to be worth +0.05 macro on a fixed extraction.
    """
    cur = dict(cons)
    base = len(prob.solve(list(cur.values())))
    for i, line in enumerate(lines):
        if i in cur:
            continue
        times = TIME_RE.findall(line)
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


def _calibrated_drop(prob, cons, tries=3):
    """Free repair for a contradiction that is too small to be real.

    An unsatisfiable extraction is either a real contradiction in the notes or
    an invented constraint. One signal separates them without spending a call:
    the size of the smallest conflicting set. Every conflicting set in this
    task has at least three statements in it, so a two-statement core is not a
    conflict the notes contain -- it is two readings of the notes colliding,
    and the answer built on it is wrong whichever case the item really is.
    There is therefore nothing to lose by disbelieving one of the two, and the
    one to disbelieve is the one from the code kind the extractor is measured
    to get wrong most often.
    """
    cur = dict(cons)
    dropped = []
    for _ in range(tries):
        indexed = [(i, cur[i]) for i in sorted(cur)]
        if prob.sat([c for _k, c in indexed]):
            break
        core = mus(prob, indexed)
        if not core or len(core) >= MIN_CORE:
            break
        victim = least_trusted(core, dict(indexed))
        dropped.append((victim, cur.pop(victim)))
    return cur, dropped


def _recover(raw, cons, prob, lines):
    """Free repair, no model call: when the extraction is under-constrained,
    re-parse the codes the strict parser dropped and keep only the ones that
    move the world count toward the window a real item can occupy."""
    cand = _lenient(raw, cons, prob)
    if not cand:
        return cons
    best = dict(cons)
    base = len(prob.solve(list(best.values())))
    for i, c in cand.items():
        trial = dict(best)
        trial[i] = c
        n = len(prob.solve(list(trial.values())))
        if n and n < base:
            best, base = trial, n
    return best


def solve_item(item, client, budget, comps=None, want_trace=False, fmt=None):
    """Answer one item inside its call budget."""
    comps = {**DEFAULT_COMPONENTS, **(comps or {})}
    fmt = fmt or FMT
    iid = item["id"]
    people, blocks, stations, holders = parse_header(item["text"])
    lines = body_lines(item["text"])
    prob = Problem(people, blocks, stations, holders)
    trace = []

    if not comps["solver"]:
        return _no_solver(item, client, prob, lines, comps)

    cons, raw = _extract_pass(client, iid, prob, lines, comps, fmt=fmt)
    passes = [cons]
    worlds = prob.solve(list(cons.values()))
    trace.append(("extract", len(cons), len(worlds)))

    if comps["recover"] and len(worlds) > AMBIG_MAX:
        cons = _recover(raw, cons, prob, lines)
        passes[0] = cons
        trace.append(("recover", len(cons), len(prob.solve(list(cons.values())))))

    # `verdict` applies the two free repairs -- soft negatives and the
    # calibrated drop -- and returns the finished answer for this extraction.
    # At 1x that is the whole system.

    # ---- spend what is left, guided by the count -------------------------
    # Each extraction becomes a *finished verdict*, and the answer is the
    # verdict a majority of passes reached. The earlier design merged the
    # constraint sets line by line and re-solved the merge, which failed in a
    # specific and instructive way: per-line majority DROPS a constraint only
    # two passes of five found, and when that is the constraint a contradiction
    # rests on, a correctly-detected inconsistent item silently becomes
    # satisfiable. The 10x score came in eleven points BELOW the 3x score
    # because of it. Voting on verdicts cannot dissolve a verdict that way.
    votes_max = 3 if client.budget <= 3 else 5
    core_checked = False
    nf = 0
    cands = [verdict(prob, cons, lines, comps)]
    cur = cands[0]
    while client.left(iid) > 0:
        worlds = cur[2]
        n = len(worlds)
        if n > AMBIG_MAX and comps["repair"] and nf < 3:
            # Under-constrained: a constraint was missed, and it is in a line
            # read as asserting nothing. Re-read only those lines -- not the
            # item, and not the lines already translated.
            base = cur[4]
            focus = [i for i in range(len(lines)) if i not in base]
            if not focus:
                break
            nf += 1
            new, _ = _extract_pass(client, iid, prob, lines, comps,
                                   focus=focus, fmt=fmt)
            added = {i: c for i, c in new.items() if i in focus}
            if not added:
                break
            cand = dict(base)
            cand.update(added)
            if not prob.sat(list(cand.values())):
                # Taking the whole re-read collapses the item to a
                # contradiction, so part of it is wrong. Add one at a time and
                # keep only what leaves the item satisfiable.
                cand, _w = _add_greedily(prob, base, added)
            v = verdict(prob, cand, lines, comps)
            trace.append(("repair-missing", len(cand), len(v[2])))
            if rank(len(v[2])) <= rank(n):
                cur = v
                cands.append(v)
            if len(cur[2]) >= n:
                break                       # the re-read is not converging
        elif n == 0 and comps["repair"] and not core_checked:
            # Over-constrained: either a contradiction the notes contain or a
            # constraint the model invented, and if it is invented it is in the
            # core. Re-read exactly those lines -- typically three of twenty.
            core_checked = True
            base = cur[4]
            core = cur[3] or mus(prob, [(i, base[i]) for i in sorted(base)])
            if not core:
                break
            new, _ = _extract_pass(client, iid, prob, lines, comps,
                                   focus=core, fmt=fmt)
            cand = dict(base)
            changed = False
            for i in core:
                if new.get(i) != base.get(i):
                    changed = True
                    if new.get(i) is None:
                        cand.pop(i, None)
                    else:
                        cand[i] = new[i]
            trace.append(("repair-core", len(core), int(changed)))
            if not changed:
                # The model re-read every statement in the core and stood by
                # all of them. That is the strongest evidence available that
                # the contradiction is in the notes rather than in the
                # reading, so stop and cite it.
                break
            v = verdict(prob, cand, lines, comps)
            cands.append(v)
            cur = vote_verdicts(cands)
        elif comps["vote"] and len(passes) < votes_max:
            new, _ = _extract_pass(client, iid, prob, lines, comps, fmt=fmt)
            passes.append(new)
            cands.append(verdict(prob, new, lines, comps))
            # the line-by-line merge is offered as one more candidate rather
            # than as an override: it is better than any single pass when the
            # passes differ by noise, and worse when they differ by one pass
            # finding a real constraint the others missed
            cands.append(verdict(prob, merge_votes(passes, len(lines)),
                                 lines, comps))
            cur = vote_verdicts(cands)
            trace.append(("vote", len(passes), len(cur[2])))
            core_checked = False
        else:
            break

    case, _sig, worlds, core, cons = cur
    return Solved(case, worlds, core, cons, lines, client.used(iid),
                  trace if want_trace else None)


def _add_greedily(prob, cons, added):
    """Add re-read constraints one at a time, keeping only those that leave the
    item satisfiable. Used when adding them all at once would make it unsat."""
    cur = dict(cons)
    worlds = prob.solve(list(cur.values()))
    for i, c in added.items():
        trial = dict(cur)
        trial[i] = c
        w = prob.solve(list(trial.values()))
        if w:
            cur, worlds = trial, w
    return cur, worlds


def _no_solver(item, client, prob, lines, comps):
    """Ablation arm: no formal layer. The model is asked for the answer."""
    iid = item["id"]
    txt = item["text"] + (
        "\n\nDecide the rota. Reply with JSON only, one of:\n"
        '{"case":"unique","assignment":{"Name":{"block":"07:00",'
        '"station":"intake"}}}\n'
        '{"case":"ambiguous","assignments":[{...},{...}]}\n'
        '{"case":"inconsistent","conflicts":["line from the notes","..."]}')
    reply = client.chat(iid, [{"role": "user", "content": txt}], max_tokens=900)
    return Solved("raw", reply, None, {}, lines, client.used(iid), None)


# ---------------------------------------------------------------------------
# Answer assembly
# ---------------------------------------------------------------------------

def to_answer(item, solved):
    people, blocks, stations, holders = parse_header(item["text"])
    prob = Problem(people, blocks, stations, holders)
    if solved.case == "raw":
        return _parse_raw(solved.worlds, prob)
    if solved.case == "unique":
        return {"case": "unique", "assignment": prob.render(solved.worlds[0])}
    if solved.case == "ambiguous":
        ws = solved.worlds[:RENDER_CAP]
        return {"case": "ambiguous", "assignments": [prob.render(w) for w in ws]}
    cites = [solved.lines[i] for i in (solved.core_idx or [])]
    return {"case": "inconsistent", "conflicts": cites}


def _parse_raw(reply, prob):
    """Best-effort read of a free-form model answer, for the no-solver arm."""
    import json
    import re
    s = reply or ""
    m = re.search(r"\{.*\}", s, re.S)
    if not m:
        return {"case": "unique", "assignment": {}}
    try:
        d = json.loads(m.group(0))
    except Exception:                                      # noqa: BLE001
        return {"case": "unique", "assignment": {}}
    if not isinstance(d, dict):
        return {"case": "unique", "assignment": {}}
    return d
