"""Does the model's output actually determine the answers?

One of the auto-fail checks is a system whose answers do not change when the
model's output changes. This demonstrates the dependence directly and without
spending a call: it replays one recorded run through the unchanged symbolic
layer three times, perturbing only the model's replies.

  real        the replies as the model produced them
  blanked     every code replaced by NONE -- the model says nothing
  shuffled    every code kept but reassigned to a different line
  negated     every polarity flipped (BLOCK <-> NOT_BLOCK, and so on)

If the symbolic layer were deciding on its own, these would agree. They do
not: nearly every item changes.

    python3 dev/check_model_sensitivity.py fixtures/extraction_1x.json
"""
import json
import random
import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dev.replay import replay, comps_for                           # noqa: E402
from score import score                                            # noqa: E402

# Model output can contain any character; the Windows console codepage
# cannot. Printing a raw reply must not crash a measurement script.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass
LINE = re.compile(r"^(\s*\**\s*\d{1,3}\s*[.):\-]\s*)(.+?)\s*$")
FLIP = [("NOT_BLOCK", "\x00"), ("BLOCK", "NOT_BLOCK"), ("\x00", "BLOCK"),
        ("NOT_STATION", "\x01"), ("STATION_EARLIER", "\x02"),
        ("STATION", "NOT_STATION"), ("\x01", "STATION"),
        ("\x02", "STATION_EARLIER")]


def perturb(log, mode, seed=7):
    rng = random.Random(seed)
    out = []
    for rec in log:
        lines = (rec.get("reply") or "").splitlines()
        codes, keep = [], []
        for ln in lines:
            m = LINE.match(ln)
            if m:
                codes.append(m.group(2))
                keep.append((m.group(1), len(codes) - 1))
            else:
                keep.append((ln, None))
        if mode == "blanked":
            codes = ["NONE"] * len(codes)
        elif mode == "shuffled":
            rng.shuffle(codes)
        elif mode == "negated":
            new = []
            for c in codes:
                for a, b in FLIP:
                    c = c.replace(a, b)
                new.append(c)
            codes = new
        reply = "\n".join(p + codes[i] if i is not None else p
                          for p, i in keep)
        out.append({**rec, "reply": reply})
    return out


if __name__ == "__main__":
    log = json.load(open(sys.argv[1], encoding="utf-8"))
    items = json.load(open("items.json", encoding="utf-8"))
    key = json.load(open("visible_key.json", encoding="utf-8"))

    comps = comps_for("full")
    base = replay(items, log, comps)
    print(f"{'perturbation':12s} {'macro':>7s}  {'items whose answer changed':>26s}")
    for mode in ("real", "blanked", "shuffled", "negated"):
        sub = replay(items, perturb(log, mode), comps)
        r = score(key, sub, items)
        diff = sum(1 for k in base if json.dumps(base[k], sort_keys=True)
                   != json.dumps(sub.get(k), sort_keys=True))
        print(f"{mode:12s} {r['macro_exact_match']:7.4f}  "
              f"{diff:>13d} / {len(base)}"
              + ("   (baseline)" if mode == "real" else ""))
