"""DEV ONLY. Stopping the preamble.

Reasoning is disabled at the API level and the model still writes several
hundred tokens of prose before its first code, which at 1x costs the tail of
the list. Three candidate fixes, measured on the items where it happened:

  A  tell it the literal first characters of its reply
  B  prefill the assistant turn with "1." so there is no room for a preamble
  C  just raise max_tokens and let it ramble first
"""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rota.client import ModelClient                                   # noqa: E402
from rota.extract import (parse_header, body_lines, build_prompt,
                          parse_codes)                                # noqa: E402
from rota.solver import Problem                                       # noqa: E402

ITEMS = {i["id"]: i for i in json.load(open("items.json", encoding="utf-8"))}
TARGETS = ["B2-000", "B2-011", "B2-002", "B2-004", "B2-007", "B2-013"]


def coverage(reply, n, prob, prefix=""):
    cons, raw = parse_codes(prefix + reply, n, prob)
    return len(raw), len(cons)


def variant(cli, iid, which):
    it = ITEMS[iid]
    people, blocks, stations, holders = parse_header(it["text"])
    prob = Problem(people, blocks, stations, holders)
    lines = body_lines(it["text"])
    msgs = build_prompt(people, blocks, stations, holders, lines)
    prefix = ""
    mt = 250 + 40 * len(lines)
    if which == "A":
        msgs[-1]["content"] += (
            "\nYour reply must begin with the two characters `1.` and must "
            "contain no sentence of English anywhere.")
    elif which == "B":
        msgs[-1]["content"] += (
            "\nYour reply must begin with the two characters `1.` and must "
            "contain no sentence of English anywhere.")
        msgs = msgs + [{"role": "assistant", "content": "1."}]
        prefix = "1."
    elif which == "C":
        mt = 2600
    reply = cli.chat(iid, msgs, max_tokens=mt)
    emitted, parsed = coverage(reply, len(lines), prob, prefix)
    return emitted, parsed, len(lines), (prefix + reply)[:70].replace("\n", "|")


if __name__ == "__main__":
    cli = ModelClient(budget=10 ** 6)
    for which in ("A", "B", "C"):
        print(f"\n=== variant {which} ===")
        tot = [0, 0]
        for iid in TARGETS:
            e, p, n, head = variant(cli, iid, which)
            tot[0] += e
            tot[1] += n
            print(f"  {iid}: {e:2d}/{n:2d} lines answered, {p:2d} constraints"
                  f"   head={head!r}")
        print(f"  coverage {tot[0]}/{tot[1]} = {tot[0]/tot[1]:.0%}")
