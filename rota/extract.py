"""Model-based constraint extraction, and the strict parser that guards it.

The model is asked to do exactly one thing: translate one line of notes into
one token of a closed vocabulary. It never counts solutions, never decides a
case, never names a conflict. Everything downstream is symbolic.

The vocabulary below is not the obvious one; it is the second design. The
first used positional arguments and angle-bracket placeholders in the spec
(`BETWEEN <p> <q> <r>`, `SBEFORE <s> <p>`) and the model, probed on single
lines, echoed the brackets back and permuted the arguments of the three-place
form. Three changes fixed most of that and are the reason for the odd-looking
surface syntax:

  * no angle brackets anywhere in the spec -- they were being copied;
  * the three-place form carries its own keywords, `MIDDLE x BETWEEN y AND z`,
    so the distinguished argument cannot be lost to argument order;
  * the station-ordering form is spelled `STATION_EARLIER`, after `SBEFORE`
    was repeatedly confused with the adjacency form.
"""
import re

# ---------------------------------------------------------------------------
# Header parsing. Deliberately symbolic: the header is a fixed preamble that
# declares the world, not one of the constraint statements whose phrasing the
# held-out set varies. It is parsed tolerantly -- several ways of finding each
# field -- so a reworded preamble degrades rather than crashes.
# ---------------------------------------------------------------------------

TIME_RE = re.compile(r"\b\d{1,2}:\d{2}\b")


def _split_list(s):
    s = s.strip().rstrip(".")
    s = re.sub(r"\s+and\s+", ", ", s)
    return [x.strip() for x in s.split(",") if x.strip()]


def parse_header(text):
    """(people, blocks, stations, holders) for one item."""
    head = text.split("\n")[0]

    people = []
    m = re.search(r"(?:staff|people)[^:]*on the rota:\s*([^.]+)\.", head, re.I)
    if not m:
        m = re.search(r"rota:\s*([^.]+)\.", head, re.I)
    if m:
        people = _split_list(m.group(1))

    m = re.search(r"[Bb]locks?\s+(?:run|are)\s+(.+?)(?:,\s*one person per|\.)",
                  head)
    blocks = TIME_RE.findall(m.group(1)) if m else []
    if not blocks:
        blocks = TIME_RE.findall(head)
    # de-duplicate, keep first-seen order (the header lists them earliest first)
    seen = set()
    blocks = [b for b in blocks if not (b in seen or seen.add(b))]

    stations = []
    m = re.search(r"stations?,?\s*one person on each:\s*([^.]+)\.", head, re.I)
    if not m:
        m = re.search(r"\d+\s+stations?[^:]*:\s*([^.]+)\.", head, re.I)
    if m:
        stations = _split_list(m.group(1))

    holders = []
    m = re.search(r"people on a station are\s*([^;.]+)", head, re.I)
    if not m:
        m = re.search(r"on a station(?:\s+are)?:?\s*([^;.]+)", head, re.I)
    if m:
        holders = [h for h in _split_list(m.group(1)) if h in people]
    if not holders:
        holders = people[:len(stations)]
    return people, blocks, stations, holders


def body_lines(text):
    """The note lines, in order, with the header dropped."""
    return [ln.strip() for ln in text.split("\n")[1:] if ln.strip()]


# ---------------------------------------------------------------------------
# The prompt
# ---------------------------------------------------------------------------

SYSTEM = (
    "You are a precise translator. You convert each line of shift notes into "
    "one formal constraint code. You never solve the rota, never explain and "
    "never comment. Your entire reply is numbered codes, one per line."
)

CODES = """CODES (use exactly one per line):
BLOCK person time            that person works that time block
NOT_BLOCK person time        that person does not work that time block
STATION person station       that person is on that station this week
NOT_STATION person station   that person is not on that station this week
EARLIER personA personB      personA's block is earlier in the day than personB's
NEXT personA personB         personB works the very next block after personA
MIDDLE personA BETWEEN personB AND personC
                             personA's block is somewhere after one of personB
                             and personC and before the other
STATION_EARLIER station person
                             whoever is on that station works earlier than that person
NONE                         the line constrains nobody"""

RULES = """RULES:
1. A hedge carries full force. "I'm fairly sure Priya is on calibration" is
   STATION Priya calibration, exactly as firmly as the unhedged sentence.
   Strip the hedge and translate what is left. The same goes for a line that
   says it is being repeated.
2. Translate only what the line asserts about the CURRENT rota. Answer NONE
   when the line asserts nothing about it, which covers four cases:
   - it is about the past: a previous week, month, cycle or arrangement, or
     what somebody used to do. A past station is not a current station.
   - it is about something that did NOT happen: a request that was refused, a
     preference, a what-if, something that would have been better or would
     have helped. Wanting a block is not having it.
   - it leaves the matter open: nobody remembers, it was never minuted, it was
     disputed, it was left to be decided. An unanswered question fixes nothing.
   - it is about anything other than who works when and where: keys, surveys,
     catering, deliveries, training, car-shares, panels, walkarounds, lost
     property, recycling, parking, paperwork.
3. Any line comparing WHEN two people work is EARLIER, naming the earlier one
   first. Use NEXT instead only when the line says the two blocks touch with
   nothing in between. "A relieves B", "A takes over from B", "by the time A
   starts B has been on" all put B earlier than A.
4. For MIDDLE, the person in the middle is named first, directly after the
   word MIDDLE, whatever order the sentence happens to use.
5. If a line refers to a person only by the station they hold -- whoever is on
   that station, the person covering it -- and compares them to a named
   person's time, that is STATION_EARLIER, naming the station first. It is
   never STATION and never NEXT.
6. A line about a station is a station code; a line about a clock time is a
   block code. Do not answer one with the other.
7. Copy names, times and station words exactly as they appear. Never use a
   name that is not on the rota."""

TERSE = """FORMAT:
Your reply must begin with the two characters `1.` and must contain no
sentence of English anywhere. Every line of your reply is at most six words
long. Never write a question mark. Never reconsider a code once you have
written it: write one code, then move straight on to the next number."""

FEWSHOT = """EXAMPLE
Rota: Alice, Bob, Carla, Dev, Erin. Blocks: 07:00, 09:00, 11:00, 13:00, 15:00.
Stations: intake, calibration, packing, held by Alice, Carla, Erin.
1. Going off the roster, Carla is not assigned to packing.
2. Bob keeps the sign-in sheet in the top drawer.
3. Dev starts the moment Erin finishes, with nothing in between.
4. Up until last week Alice had calibration.
5. Whichever way round Bob and Dev are, Alice is between them.
6. Whether Erin ended up with 15:00 was never settled.
7. Alice finishes before Dev has started.
8. I'm fairly sure the 09:00 block is Bob's.
9. The person covering intake is on earlier than Dev.
10. Erin pushed hard for 07:00 and was turned down.

ANSWER
1. NOT_STATION Carla packing
2. NONE
3. NEXT Erin Dev
4. NONE
5. MIDDLE Alice BETWEEN Bob AND Dev
6. NONE
7. EARLIER Alice Dev
8. BLOCK Bob 09:00
9. STATION_EARLIER intake Dev
10. NONE
END EXAMPLE"""

FEWSHOT_SPARSE = """EXAMPLE
Rota: Alice, Bob, Carla, Dev, Erin. Blocks: 07:00, 09:00, 11:00, 13:00, 15:00.
Stations: intake, calibration, packing, held by Alice, Carla, Erin.
1. Going off the roster, Carla is not assigned to packing.
2. Bob keeps the sign-in sheet in the top drawer.
3. Dev starts the moment Erin finishes, with nothing in between.
4. Up until last week Alice had calibration.
5. Whichever way round Bob and Dev are, Alice is between them.
6. Whether Erin ended up with 15:00 was never settled.
7. Alice finishes before Dev has started.
8. I'm fairly sure the 09:00 block is Bob's.
9. The person covering intake is on earlier than Dev.
10. Erin pushed hard for 07:00 and was turned down.

ANSWER
1. NOT_STATION Carla packing
3. NEXT Erin Dev
5. MIDDLE Alice BETWEEN Bob AND Dev
7. EARLIER Alice Dev
8. BLOCK Bob 09:00
9. STATION_EARLIER intake Dev
END EXAMPLE"""


def world_blurb(people, blocks, stations, holders):
    return (f"Rota: {', '.join(people)}. "
            f"Blocks, earliest first: {', '.join(blocks)}. "
            f"Stations: {', '.join(stations)}, held by {', '.join(holders)}. "
            f"Everyone else is on no station.")


NONE_TOKEN = {"dense": "NONE", "dash": "-"}


def build_prompt(people, blocks, stations, holders, lines, focus=None,
                 fmt="dash"):
    """The extraction prompt.

    `focus` restricts it to a subset of line numbers, which is how a repair
    pass re-reads only the lines in question.

    `fmt` selects the shape of the reply, which turned out to matter more than
    any wording in the rules. The model's dominant failure at full item length
    is not a wrong code, it is derailing into commentary part-way down the
    list and never reaching the rest of it -- so the format that wins is the
    one with the fewest output tokens to derail in:

      dense   a numbered code for every line, NONE where nothing is asserted
      dash    the same, but `-` instead of the word NONE (about a third of the
              output tokens, and the numbering still anchors the reply)
      sparse  only the lines that assert something, everything else omitted
              (shortest, but the reply no longer starts at a known number)
    """
    nums = list(focus) if focus is not None else list(range(len(lines)))
    listing = "\n".join(f"{i + 1}. {lines[i]}" for i in nums)
    none_tok = NONE_TOKEN.get(fmt, "NONE")

    if fmt == "sparse":
        ask = (f"List only the lines above that assert something about the "
               f"current rota. For each, write its number, a dot, and its "
               f"code. Omit every other line completely -- do not write a "
               f"placeholder for it. Numbers must stay in increasing order "
               f"and the last line you may mention is {nums[-1] + 1}.\n"
               f"Your reply must begin with a digit and must contain no "
               f"sentence of English anywhere. Never write a question mark "
               f"and never reconsider a code once written.")
    else:
        ask = (f"Translate the {len(nums)} lines above. Write exactly "
               f"{len(nums)} codes, one per line, each prefixed with the same "
               f"number as its line, in the same order. Write `{none_tok}` for "
               f"a line that asserts nothing. The numbers you write are "
               f"{', '.join(str(i + 1) for i in nums[:3])} ... "
               f"{nums[-1] + 1}, and the code numbered {nums[-1] + 1} must be "
               f"the last thing you write.\n"
               f"Your reply must begin with the characters `{nums[0] + 1}.` "
               f"and must contain no sentence of English anywhere. Every line "
               f"of your reply is at most six words long. Never write a "
               f"question mark. Never reconsider a code once you have written "
               f"it: write one code, then move straight on to the next "
               f"number. If a line is unclear, write `{none_tok}` and move on.")

    example = FEWSHOT if fmt != "sparse" else FEWSHOT_SPARSE
    if fmt == "dash":
        example = example.replace("\nNONE", "\n-")
    user = "\n\n".join([
        CODES.replace("NONE                         the line constrains nobody",
                      f"{none_tok:28s} the line constrains nobody"),
        RULES, example,
        world_blurb(people, blocks, stations, holders),
        f"LINES ({len(nums)} of them)\n" + listing,
        ask,
    ])
    return [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": user}]


# ---------------------------------------------------------------------------
# Parsing the reply
# ---------------------------------------------------------------------------

LINE_RE = re.compile(r"^\s*\**\s*(\d{1,3})\s*[.):\-]\s*(.+?)\s*$")
_WORD = r"[^\s,]+"


def _clean(tok):
    # Trailing punctuation only. A colon is stripped at the ends but never from
    # the middle, so "13:00" survives and "13:00?" and "packing." do not cost
    # a constraint. 37 codes in a 60-item run were lost to exactly this before
    # `?` and `;` were added.
    return tok.strip().strip("<>[]{}\"'`*,.?!;:").strip()


def parse_codes(reply, n_lines, problem):
    """{line index -> constraint} from one model reply.

    Strict by design. A code that does not parse, names someone who is not on
    the rota, or points at a station the item does not have is dropped, not
    repaired: a repaired guess is indistinguishable from an invented fact, and
    an invented fact is the one error this task punishes hardest.
    """
    out, raw = {}, {}
    for ln in (reply or "").splitlines():
        m = LINE_RE.match(ln)
        if not m:
            continue
        idx = int(m.group(1)) - 1
        if not 0 <= idx < n_lines or idx in raw:
            continue
        raw[idx] = m.group(2)
        c = parse_one(m.group(2), problem)
        if c is not None:
            out[idx] = c
    return out, raw


def parse_one(code, problem):
    """One code string -> one validated constraint, or None."""
    s = " ".join(str(code).split())
    # The model sometimes quotes the line back and then answers it:
    #   "Ingrid filled in the equipment survey." -> NONE
    # Taking what follows the arrow is a salvage, not an interpretation: the
    # code on the right is still the model's own answer.
    for arrow in ("->", "=>", ":="):
        if arrow in s:
            s = s.rsplit(arrow, 1)[1]
    s = " ".join(_clean(s).split())
    if not s:
        return None
    up = s.upper()
    if up.startswith("NONE") or s in ("-", "--", "—"):
        return None
    toks = [_clean(t) for t in s.split()]
    toks = [t for t in toks if t]
    if not toks:
        return None
    head = toks[0].upper().rstrip(":")
    args = toks[1:]

    def fin(c):
        return c if problem.valid(c) else None

    if head == "MIDDLE":
        words = [a for a in args if a.upper() not in ("BETWEEN", "AND", "&")]
        return fin(("between",) + tuple(words[:3])) if len(words) >= 3 else None
    if len(args) < 2:
        return None
    a, b = args[0], args[1]
    if head == "BLOCK":
        return fin(("block", a, b))
    if head in ("NOT_BLOCK", "NOTBLOCK", "NO_BLOCK"):
        return fin(("nblock", a, b))
    if head == "STATION":
        return fin(("station", a, b.lower()))
    if head in ("NOT_STATION", "NOTSTATION", "NO_STATION"):
        return fin(("nstation", a, b.lower()))
    if head == "EARLIER":
        return fin(("before", a, b))
    if head in ("NEXT", "IMM", "IMMEDIATE"):
        return fin(("imm", a, b))
    if head in ("STATION_EARLIER", "STATIONEARLIER", "SBEFORE"):
        # tolerate the two argument orders: the station is whichever token is
        # a station name, so a swap is recoverable without guessing.
        if a.lower() in problem.stations:
            return fin(("sbefore", a.lower(), b))
        if b.lower() in problem.stations:
            return fin(("sbefore", b.lower(), a))
        return None
    return None
