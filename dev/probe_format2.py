"""DEV ONLY. Second round on the preamble/derail problem.

Variant A (dictate the literal first characters of the reply) stopped the
preamble. What is left is mid-list derailment: the model writes a code, then
second-guesses it in prose -- "BLOCK Nadia 09:00? No wait:" -- and the tail of
the list is never written. These variants attack that directly.
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
TARGETS = ["B2-000", "B2-002", "B2-004", "B2-007", "B2-011", "B2-013",
           "B2-020", "B2-033"]

BEGIN = ("\nYour reply must begin with the two characters `1.` and must "
         "contain no sentence of English anywhere.")

TERSE = ("\nEvery line of your reply is at most six words long. Never write a "
         "question mark. Never reconsider a code once you have written it: "
         "write one code, then move straight to the next number.")

ONCE = ("\nWrite each numbered code once and never go back. If you are unsure "
        "about a line, write NONE for it and continue to the next number.")

VARIANTS = {
    "A": BEGIN,
    "A+terse": BEGIN + TERSE,
    "A+terse+once": BEGIN + TERSE + ONCE,
}


def one(cli, iid, extra):
    it = ITEMS[iid]
    people, blocks, stations, holders = parse_header(it["text"])
    prob = Problem(people, blocks, stations, holders)
    lines = body_lines(it["text"])
    msgs = build_prompt(people, blocks, stations, holders, lines)
    msgs[-1]["content"] += extra
    reply = cli.chat(iid, msgs, max_tokens=250 + 40 * len(lines))
    cons, raw = parse_codes(reply, len(lines), prob)
    return len(raw), len(cons), len(lines)


if __name__ == "__main__":
    reps = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    cli = ModelClient(budget=10 ** 6)
    for name, extra in VARIANTS.items():
        cov = [0, 0]
        ncons = 0
        worst = []
        for iid in TARGETS:
            for _ in range(reps):
                e, c, n = one(cli, iid, extra)
                cov[0] += e
                cov[1] += n
                ncons += c
                if e < n:
                    worst.append(f"{iid}:{e}/{n}")
        print(f"{name:14s} coverage {cov[0]:4d}/{cov[1]:4d} = "
              f"{cov[0]/cov[1]:5.1%}   constraints/item "
              f"{ncons/(len(TARGETS)*reps):4.1f}   short: {' '.join(worst)}")
