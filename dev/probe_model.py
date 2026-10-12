"""DEV ONLY. Characterising the weak model before designing around it.

Three probes, each answering one design question:

  A. naive     -- can it do the whole task end to end? (the 0.0% baseline)
  B. lines     -- can it classify ONE line into the constraint vocabulary?
  C. inert     -- does it correctly refuse to extract from the inert families
                  (padding, past-tense station history, thwarted wishes,
                  explicitly-open questions)?

B and C are the ones that decide the architecture: if per-line translation is
reliable and whole-task reasoning is not, the model should only ever be asked
to translate.
"""
import json
import os
import sys
import random
import collections

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rota.client import ModelClient                      # noqa: E402
from dev.refparse import parse_item                      # noqa: E402

ITEMS = json.load(open("items.json"))
BY_ID = {i["id"]: i for i in ITEMS}


def probe_naive(client, n=6):
    """Whole task, one shot, no harness."""
    print("\n=== A. naive one-shot (no harness) ===")
    for it in ITEMS[:n]:
        msg = [{"role": "user", "content": it["text"] + (
            "\n\nWork out the rota. Reply with JSON only: either "
            '{"case":"unique","assignment":{...}} or '
            '{"case":"ambiguous","assignments":[...]} or '
            '{"case":"inconsistent","conflicts":[...]}.')}]
        out = client.chat(it["id"], msg, max_tokens=700)
        head = " ".join(out.split())[:220]
        print(f"  {it['id']}: {head}")


LINE_PROMPT = """You turn one line of shift notes into a formal constraint.

Reply with ONE of these and nothing else:
BLOCK <person> <time>        the person works that time block
NOT_BLOCK <person> <time>    the person does not work that time block
STATION <person> <station>   the person is on that station now
NOT_STATION <person> <station>
BEFORE <a> <b>               a's block is earlier than b's
IMM <a> <b>                  b is on the block right after a
BETWEEN <a> <b> <c>          a is strictly between b and c, either order
SBEFORE <station> <person>   whoever is on that station is earlier
NONE                         the line says nothing about who is where now

Line: {line}
Answer:"""


def probe_lines(client, n=70, seed=0):
    """Per-line translation accuracy against the reference parser."""
    print("\n=== B. per-line translation ===")
    rng = random.Random(seed)
    pool = []
    for it in ITEMS:
        for line, tag, c in parse_item(it)["tags"]:
            pool.append((it["id"], line, tag, c))
    rng.shuffle(pool)
    # keep the mix honest: half real constraints, half inert
    real = [x for x in pool if x[2] == "hard"][:n // 2]
    inert = [x for x in pool if x[2] in ("pad", "null", "past", "wish")][:n - n // 2]
    sample = real + inert
    rng.shuffle(sample)

    right = collections.Counter()
    total = collections.Counter()
    errs = []
    for iid, line, tag, c in sample:
        out = client.chat(iid, [{"role": "user",
                                 "content": LINE_PROMPT.format(line=line)}],
                          max_tokens=40).strip().splitlines()
        got = out[0].strip() if out else ""
        want = to_text(c) if tag == "hard" else "NONE"
        bucket = "real" if tag == "hard" else tag
        total[bucket] += 1
        if got.upper().replace(",", " ").split() == want.split():
            right[bucket] += 1
        else:
            errs.append((bucket, line, want, got))
    for b in total:
        print(f"  {b:6s}: {right[b]:3d}/{total[b]:3d} = {right[b]/total[b]:.0%}")
    print("  -- sample of misses --")
    for b, line, want, got in errs[:18]:
        print(f"   [{b}] {line[:72]!r}\n        want={want!r}  got={got!r}")


def to_text(c):
    k = c[0]
    name = {"block": "BLOCK", "nblock": "NOT_BLOCK", "station": "STATION",
            "nstation": "NOT_STATION", "before": "BEFORE", "imm": "IMM",
            "between": "BETWEEN", "sbefore": "SBEFORE"}[k]
    return " ".join([name] + [str(x) for x in c[1:]])


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    cli = ModelClient(budget=10 ** 6)
    print("endpoint:", cli.base_url, "model:", cli.model)
    if which in ("all", "a"):
        probe_naive(cli)
    if which in ("all", "b"):
        probe_lines(cli)
    print("\ntotal model calls:", cli.total_calls())
