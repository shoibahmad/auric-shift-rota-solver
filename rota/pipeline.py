"""Budget-aware orchestration.

One call per item buys a full line-by-line extraction. Two free symbolic
repairs then run, and at 1x that is the entire system. Everything beyond the
first call is the solver telling the extractor where it is probably wrong and
spending the remaining budget only there.

The signal that makes this possible is cheap and comes free with an exhaustive
enumerator: the number of worlds consistent with what was extracted. The brief
fixes the shape of a legitimate answer -- an item has one world, two to four,
or none -- so a count above four is a proof that the extraction is wrong,
established without reference to any key:

    count > 4   a constraint was missed    -> re-read the lines read as NONE
    count == 0  a constraint was invented  -> re-read the lines in the core
    1..4        plausible                  -> extract again, keep the better

A paid repair is never a retry of the item. It is a re-read of the handful of
lines the solver has just proved are carrying the error -- three of twenty for
a contradiction, the untranslated dozen for an under-constrained item.

Two findings shaped this file more than any prompt wording:

  * the two *free* repairs -- `soft_negatives` and `_calibrated_drop` -- are
    worth more than any paid one, because both act on proofs rather than on
    guesses, and both work at 1x where there is no budget to spend;
  * combining several extractions is worse than choosing between them. See
    `pick_verdict`.
"""
import collections
import re

from .extract import (parse_header, body_lines, build_prompt, parse_codes,
                      parse_one)
from .solver import Problem, mus, pick_core, least_trusted

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


def pick_verdict(cands):
    """Choose among several finished verdicts for one item.

    Selection, not merging -- and this is the design's second correction.
    The first budget loop merged repeated extractions line by line; the second
    voted on whole verdicts. Replaying one recorded three-pass log through
    every rule (`dev/tune_aggregation.py`) showed both losing to a *single*
    pass. On that log the three individual passes scored 0.533, 0.400 and
    0.550, while line-by-line merging scored 0.483, verdict-majority 0.517,
    constraint-union 0.517 and agree-only-intersection 0.383. The model's
    errors are systematic rather than independent noise, so averaging
    reinforces them; merging additionally discards a constraint that only one
    lucky pass found, which is precisely the constraint worth keeping when
    under-extraction is the dominant error.

    What does work is discarding the passes that are *provably* wrong and
    keeping the best survivor. A world count above four cannot be right
    whatever the item is, so candidates are ordered by that and the first of
    the best rank wins -- first, so that a resample overrides the original
    extraction only when the original is demonstrably broken. On the same log
    this scores 0.567, above the best single pass and well above the 0.494 a
    single pass averages.

    One refinement, from watching 3x come in *below* 1x: a contradiction has
    to be corroborated to win. An under-constrained first pass that is
    re-sampled into an unsatisfiable one looks like progress to the rank
    alone -- no worlds is a count the task permits, too many is not -- and
    four genuinely-inconsistent items were being traded for four wrong
    `unique` answers that way. So a contradiction counts only if it was the
    first thing the system concluded, or if a second candidate reaches the
    same core independently. A contradiction the system found once, late, and
    never again, is a mistranslation.
    """
    if not cands:
        return None
    pool = sorted(cands, key=lambda v: rank(len(v[2])))
    best = rank(len(pool[0][2]))
    pool = [v for v in pool if rank(len(v[2])) == best]
    if len(cands) > 1:
        sat = [v for v in pool if v[2]]
        unsat = [v for v in pool if not v[2]]
        cores = collections.Counter(v[1] for v in unsat)
        corroborated = [v for v in unsat
                        if cores[v[1]] > 1 or v is cands[0]]
        if sat and unsat and not corroborated:
            pool = sat
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
            cands.append(v)
            cur = pick_verdict(cands)
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
            # A core is three lines, so a re-read is cheap and can be done
            # more than once -- which it must be. The first version of this
            # took a single re-read as authoritative and overwrote the core
            # whenever the model came back with anything different. At
            # temperature 1.0 the model comes back with something different
            # all the time: individual full extractions of the same item score
            # anywhere from 0.400 to 0.550, so one disagreement is not evidence
            # that the first reading was wrong. Instead the re-reads are votes
            # on those lines, and the original keeps its reading unless the
            # re-reads actually agree with each other against it.
            reads = {i: [base.get(i)] for i in core}
            n_reads = 0
            while n_reads < 2 and client.left(iid) > 0:
                new, _ = _extract_pass(client, iid, prob, lines, comps,
                                       focus=core, fmt=fmt)
                n_reads += 1
                for i in core:
                    reads[i].append(new.get(i))
            cand = dict(base)
            changed = False
            for i in core:
                tally = collections.Counter(reads[i])
                top, votes = tally.most_common(1)[0]
                # strict majority of all readings, original included
                if votes * 2 > len(reads[i]) and top != base.get(i):
                    changed = True
                    if top is None:
                        cand.pop(i, None)
                    else:
                        cand[i] = top
            trace.append(("repair-core", len(core), n_reads, int(changed)))
            if not changed:
                # The re-reads did not agree on anything different. That is the
                # strongest evidence available that the contradiction is in the
                # notes rather than in the reading, so stop and cite it.
                break
            cands.append(verdict(prob, cand, lines, comps))
            cur = pick_verdict(cands)
        elif comps["vote"] and len(passes) < votes_max:
            new, _ = _extract_pass(client, iid, prob, lines, comps, fmt=fmt)
            passes.append(new)
            cands.append(verdict(prob, new, lines, comps))
            cur = pick_verdict(cands)
            trace.append(("resample", len(passes), len(cur[2])))
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
    """Ablation arm: no formal layer at all -- the model is asked for the
    answer and its reply is parsed as the answer.

    At 3x and 10x it gets to spend its budget the only way a system without a
    formal layer can: ask again and take the most common verdict. Without that
    the arm would be a one-call system compared against a ten-call one, and
    the ablation would be measuring the budget rather than the component.
    """
    iid = item["id"]
    txt = item["text"] + (
        "\n\nDecide the rota. Reply with JSON only, one of:\n"
        '{"case":"unique","assignment":{"Name":{"block":"07:00",'
        '"station":"intake"}}}\n'
        '{"case":"ambiguous","assignments":[{...},{...}]}\n'
        '{"case":"inconsistent","conflicts":["line from the notes","..."]}')
    msgs = [{"role": "user", "content": txt}]
    replies = [client.chat(iid, msgs, max_tokens=900)]
    while client.left(iid) > 0 and len(replies) < 5:
        replies.append(client.chat(iid, msgs, max_tokens=900))
    if len(replies) > 1:
        parsed = [_parse_raw(r, prob) for r in replies]
        cases = collections.Counter(p.get("case") for p in parsed
                                    if isinstance(p, dict))
        if cases:
            best = cases.most_common(1)[0][0]
            for r, p in zip(replies, parsed):
                if isinstance(p, dict) and p.get("case") == best:
                    return Solved("raw", r, None, {}, lines,
                                  client.used(iid), None)
    return Solved("raw", replies[0], None, {}, lines, client.used(iid), None)


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
