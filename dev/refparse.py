"""DEV ONLY. Regex reference parser over the VISIBLE phrasing pool.

Used to learn the generator's semantics (which line families assert a
constraint and which are inert) and to validate the symbolic solver.
It is NOT part of the shipped answering pipeline -- the held-out set uses a
disjoint phrasing pool, so regex over these templates would not transfer.
"""
import re
import json

HEDGES = [
    "i'm fairly sure ", "from what i recall, ", "as far as i know, ",
    "i believe ", "going off the roster, ", "if memory serves, ",
    "my recollection is that ", "unless i have this wrong, ",
    "speaking from memory, ", "i'm reasonably confident ",
]
RESTATE = [
    "it bears repeating: ", "this came up more than once, so: ",
    "noted twice in the handover: ",
    "worth restating, since it came up twice in handover: ",
]


def strip_prefixes(line):
    s = line.strip()
    changed = True
    while changed:
        changed = False
        low = s.casefold()
        for p in RESTATE + HEDGES:
            if low.startswith(p):
                s = s[len(p):]
                changed = True
                break
    return s


def parse_header(text):
    h = text.split("\n")[0]
    names = [x.strip() for x in
             re.search(r"staff on the rota: ([^.]+)\.", h).group(1).split(",")]
    blocks = re.search(r"Blocks run (.+?), one person per block", h).group(1)
    blocks = [b.strip() for b in blocks.split(",")]
    stations = re.search(r"stations, one person on each: ([^.]+)\.", h).group(1)
    stations = [s.strip() for s in stations.split(",")]
    holders = re.search(r"people on a station are ([^;]+);", h).group(1)
    holders = [x.strip() for x in holders.split(",")]
    return names, blocks, stations, holders


# ---- constraint forms -------------------------------------------------
# ('block', p, b)        p is on block b
# ('nblock', p, b)       p is not on block b
# ('station', p, s)      p is on station s
# ('nstation', p, s)     p is not on station s
# ('before', p, q)       p's block is earlier than q's
# ('imm', p, q)          q is on the block immediately after p's
# ('between', p, q, r)   p strictly between q and r (either order)
# ('sbefore', s, p)      the person on station s is earlier than p

def build(names, blocks, stations):
    N = "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))
    B = "|".join(re.escape(b) for b in blocks)
    S = "|".join(re.escape(s) for s in stations)

    def R(pat):
        pat = (pat.replace("<P>", "(?P<p>" + N + ")")
                  .replace("<Q>", "(?P<q>" + N + ")")
                  .replace("<R>", "(?P<r>" + N + ")")
                  .replace("<B>", "(?P<b>" + B + ")")
                  .replace("<S>", "(?P<s>" + S + ")"))
        return re.compile("^" + pat + "$", re.I)

    rules = []

    def add(pat, fn, tag="hard"):
        rules.append((R(pat), fn, tag))

    # --- block, positive
    for pat in [r"<P> is on the <B> block\.",
                r"The <B> block is <P>'s\.",
                r"<B> is when <P> is scheduled\.",
                r"<P> takes <B>, as things stand\.",
                r"Whoever drew the <B> block, it was <P>\.",
                r"<P> is the one who opens up at <B>\."]:
        add(pat, lambda m: ("block", m["p"], m["b"]))

    # --- block, negative
    for pat in [r"<P> is not on the <B> block\.",
                r"The <B> block is not <P>'s\.",
                r"You will not find <P> on the <B> block\.",
                r"<B> is the one block <P> is definitely not on\.",
                r"<P> is unavailable at <B>\.",
                r"<P> has a standing commitment that rules out the <B> block entirely\."]:
        add(pat, lambda m: ("nblock", m["p"], m["b"]))

    # --- block, negative via a thwarted wish / counterfactual (hypothesis)
    for pat in [r"<P> lobbied for <B> without success\.",
                r"<P> wanted <B> and did not get it\.",
                r"<P> put in for the <B> block and was turned down\.",
                r"<P> asked to move to the <B> block; the request was declined\.",
                r"If <P> had taken the <B> block the handover would have been smoother\.",
                r"<P> would have been a better fit for the <B> block\.",
                r"Putting <P> on the <B> block would have solved the parking problem\.",
                r"Had the rota gone the other way, <P> would be on <B>\."]:
        add(pat, lambda m: ("nblock", m["p"], m["b"]), tag="wish")

    # --- explicit non-statements about a block
    for pat in [r"There was some disagreement about whether <P> had <B>\.",
                r"Nobody could remember whether <P> was down for the <B> block\.",
                r"The question of <P> on <B> was left open in the handover\.",
                r"<P> and the <B> block came up, but nothing was minuted\."]:
        add(pat, lambda m: None, tag="null")

    # --- station, positive
    for pat in [r"<P> is on <S>\.", r"<P> is assigned to <S>\.",
                r"<S> is <P>'s station\.", r"<S> is covered by <P>\.",
                r"The <S> station is down to <P>\.", r"<P> has <S> this week\."]:
        add(pat, lambda m: ("station", m["p"], m["s"].lower()))

    # --- station, negative
    for pat in [r"<P> is not on <S>\.", r"<P> is not assigned to <S>\.",
                r"<P> has not been put on <S>\.", r"<S> is not <P>'s station\.",
                r"<S> is covered by someone other than <P>\.",
                r"You can rule <P> out for <S>\."]:
        add(pat, lambda m: ("nstation", m["p"], m["s"].lower()))

    # --- station, past tense (hypothesis under test)
    for pat in [r"In the spring <P> held <S> for a while\.",
                r"Back in the old arrangement, <P> took <S>\.",
                r"Last month <P> was on <S>\.",
                r"On the previous cycle <S> was <P>'s\."]:
        add(pat, lambda m: ("station", m["p"], m["s"].lower()), tag="past")

    # --- order
    add(r"<P> comes later in the day than <Q>\.", lambda m: ("before", m["q"], m["p"]))
    add(r"<P> works earlier in the day than <Q>\.", lambda m: ("before", m["p"], m["q"]))
    add(r"<P>'s block falls somewhere earlier than <Q>'s\.", lambda m: ("before", m["p"], m["q"]))
    add(r"<P> is done before <Q> starts\.", lambda m: ("before", m["p"], m["q"]))
    add(r"By the time <P> starts, <Q> has already been on\.", lambda m: ("before", m["q"], m["p"]))
    add(r"<P> takes over from <Q> later in the day\.", lambda m: ("before", m["q"], m["p"]))

    # --- adjacency
    add(r"<P> is on the block directly after <Q>\.", lambda m: ("imm", m["q"], m["p"]))
    add(r"<P> is on the block immediately before <Q>\.", lambda m: ("imm", m["p"], m["q"]))
    add(r"<P> relieves <Q> directly, with no block in between\.", lambda m: ("imm", m["q"], m["p"]))
    add(r"<P> then <Q>, back to back\.", lambda m: ("imm", m["p"], m["q"]))
    add(r"<P> hands straight over to <Q>\.", lambda m: ("imm", m["p"], m["q"]))
    add(r"There is no block between <P>'s and <Q>'s, in that order\.", lambda m: ("imm", m["p"], m["q"]))

    # --- betweenness (strict, unordered)
    for pat in [r"<P> sits between <Q> and <R> on the rota\.",
                r"<P> works at some point between <Q> and <R>, not necessarily adjacent to either\.",
                r"Put <P> between <Q> and <R>, though not necessarily next to either\.",
                r"<P> is on after one of <Q> and <R> and before the other\.",
                r"<P>'s block falls between <Q>'s and <R>'s, in one order or the other\."]:
        add(pat, lambda m: ("between", m["p"], m["q"], m["r"]))
    add(r"Whichever way round <Q> and <R> are, <P> is between them\.",
        lambda m: ("between", m["p"], m["q"], m["r"]))

    # --- station holder vs person, order
    add(r"The <S> station is covered earlier in the day than <P>'s block\.",
        lambda m: ("sbefore", m["s"].lower(), m["p"]))
    add(r"Whoever is on <S> works earlier in the day than <P>\.",
        lambda m: ("sbefore", m["s"].lower(), m["p"]))
    add(r"The person on <S> precedes <P>\.", lambda m: ("sbefore", m["s"].lower(), m["p"]))
    add(r"<P> is on later than whoever has <S>\.", lambda m: ("sbefore", m["s"].lower(), m["p"]))
    add(r"Whoever has <S> is done before <P> starts\.", lambda m: ("sbefore", m["s"].lower(), m["p"]))
    add(r"<S> is covered before <P> comes on\.", lambda m: ("sbefore", m["s"].lower(), m["p"]))
    return rules


PADDING = [
    r"The visitor log was moved to the front desk in March\.",
    r"Nobody has claimed the jacket left in the break room\.",
    r"The recycling collection has moved to Wednesdays\.",
    r"Catering is unchanged from last week\.",
    r"The site coordinator noted that the car park resurfacing runs through the end of the month\.",
    r"Deliveries continue to arrive through the north gate\.",
    r".* car-share when their shifts allow\.",
    r".*filled in the equipment survey\.",
    r".*has the spare key to the supply cupboard\.",
    r".*joined the site walkaround in March\.",
    r".*completed the fire-safety refresher last quarter\.",
    r".*keeps the sign-in sheet in the top drawer\.",
    r".*sat on the interview panel in February\.",
    r".*is the point of contact for the fire drill\.",
    r".*has been chasing the maintenance ticket for the printer\.",
    r".*left a note about the recycling bins\.",
    r".*appeared on the old emergency contact sheet\.",
    r".*attended the supplier training day in the spring\.",
]
PADRE = [re.compile("^" + p + "$", re.I) for p in PADDING]


def parse_line(line, rules):
    s = strip_prefixes(line)
    for rx in PADRE:
        if rx.match(s):
            return None, "pad"
    for rx, fn, tag in rules:
        m = rx.match(s)
        if m:
            return fn(m), tag
    return None, "UNPARSED"


def parse_item(item, include=("hard", "wish", "past")):
    names, blocks, stations, holders = parse_header(item["text"])
    rules = build(names, blocks, stations)
    cons, unparsed, tags = [], [], []
    for line in item["text"].split("\n")[1:]:
        line = line.strip()
        if not line:
            continue
        c, tag = parse_line(line, rules)
        if tag == "UNPARSED":
            unparsed.append(line)
        tags.append((line, tag, c))
        if c is not None and tag in include:
            cons.append((line, c))
    return dict(names=names, blocks=blocks, stations=stations, holders=holders,
                cons=cons, unparsed=unparsed, tags=tags)


if __name__ == "__main__":
    items = json.load(open("items.json"))
    bad = 0
    for it in items:
        p = parse_item(it)
        for u in p["unparsed"]:
            bad += 1
            print(it["id"], "UNPARSED:", u)
    print("total unparsed lines:", bad)
