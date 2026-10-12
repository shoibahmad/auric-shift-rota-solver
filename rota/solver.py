"""Symbolic core: the formal representation, the model enumerator and the
minimal-unsatisfiable-subset search used to localise contradictions.

Nothing here talks to a model. Everything the weak model produces is funnelled
into the `Constraint` vocabulary below and then decided exactly.

World model for one item
------------------------
  people    an ordered list of names, taken from the header
  blocks    an ordered list of time labels, earliest first
  stations  an ordered list of station labels
  holders   the subset of `people` the header puts on a station

A *world* is a pair (block_of, station_of):
  block_of    an injective map people -> blocks (one person per block)
  station_of  a bijection holders -> stations (one person on each)

With 5 people and 3 stations that is 120 * 6 = 720 worlds, so the enumerator
is exhaustive by construction: `count == 0` is inconsistency, `count == 1`
uniqueness and `count >= 2` ambiguity, with no search heuristics in between.
"""
from itertools import permutations

# ---------------------------------------------------------------------------
# Constraint vocabulary
#
# Every form the extractor may emit. Each is a tuple whose first element is the
# kind. Keep this list closed: an unparseable extraction is dropped, never
# guessed at.
#
#   ("block",    p, b)       p works block b
#   ("nblock",   p, b)       p does not work block b
#   ("station",  p, s)       p is on station s
#   ("nstation", p, s)       p is not on station s
#   ("before",   p, q)       p's block is strictly earlier than q's
#   ("imm",      p, q)       q's block is the one immediately after p's
#   ("between",  p, q, r)    p is strictly between q and r, in either order
#   ("sbefore",  s, p)       whoever is on station s is strictly earlier than p
#   ("sperson",  s, p)       whoever is on station s is p      (alias of station)
# ---------------------------------------------------------------------------

KINDS = {
    "block": 2, "nblock": 2, "station": 2, "nstation": 2,
    "before": 2, "imm": 2, "between": 3, "sbefore": 2,
}


class Problem:
    """One item's world model, plus the fast world enumeration."""

    def __init__(self, people, blocks, stations, holders):
        self.people = list(people)
        self.blocks = list(blocks)
        self.stations = list(stations)
        self.holders = list(holders)
        self.bidx = {b: i for i, b in enumerate(self.blocks)}
        # block_of as a tuple of block indices, positionally aligned to people
        self._block_worlds = [
            w for w in permutations(range(len(self.blocks)), len(self.people))
        ]
        self._station_worlds = [
            dict(zip(self.holders, p)) for p in permutations(self.stations)
        ]

    # -- constraint validation ---------------------------------------------
    def valid(self, c):
        """Is this a well-formed constraint over THIS item's vocabulary?

        The extractor is a weak model; it invents names and stations. A
        malformed constraint is dropped rather than repaired, because a
        repaired guess is indistinguishable from a hallucinated fact.
        """
        if not isinstance(c, (list, tuple)) or not c:
            return False
        k = c[0]
        if k not in KINDS or len(c) != KINDS[k] + 1:
            return False
        P, B, S = set(self.people), set(self.blocks), set(self.stations)
        if k in ("block", "nblock"):
            return c[1] in P and c[2] in B
        if k in ("station", "nstation"):
            return c[1] in P and c[2] in S
        if k in ("before", "imm"):
            return c[1] in P and c[2] in P and c[1] != c[2]
        if k == "between":
            return (c[1] in P and c[2] in P and c[3] in P
                    and len({c[1], c[2], c[3]}) == 3)
        if k == "sbefore":
            return c[1] in S and c[2] in P
        return False

    # -- semantics ----------------------------------------------------------
    def _holds(self, c, pos, stat):
        """Does constraint c hold in the world (pos, stat)?

        `pos` maps a person to a block index; `stat` maps a holder to a
        station.
        """
        k = c[0]
        if k == "block":
            return pos[c[1]] == self.bidx[c[2]]
        if k == "nblock":
            return pos[c[1]] != self.bidx[c[2]]
        if k == "station":
            return stat.get(c[1]) == c[2]
        if k == "nstation":
            # A person the header puts on no station is on no station at all,
            # so "p is not on s" is vacuously true for them.
            return stat.get(c[1]) != c[2]
        if k == "before":
            return pos[c[1]] < pos[c[2]]
        if k == "imm":
            return pos[c[2]] - pos[c[1]] == 1
        if k == "between":
            a, b, d = pos[c[1]], pos[c[2]], pos[c[3]]
            return b < a < d or d < a < b
        if k == "sbefore":
            who = next((h for h, s in stat.items() if s == c[1]), None)
            if who is None:
                return True     # no one holds it: nothing to order against
            return pos[who] < pos[c[2]]
        raise ValueError(k)

    @staticmethod
    def _needs_stations(c):
        return c[0] in ("station", "nstation", "sbefore")

    def solve(self, cons, limit=None):
        """Every world satisfying `cons`, as (pos, stat) pairs.

        Block-only constraints are applied to the 120 block worlds first and
        station-only ones to the 6 station worlds, so the product is only
        walked for the constraints that couple the two.
        """
        block_only = [c for c in cons if c[0] in ("block", "nblock", "before",
                                                  "imm", "between")]
        station_only = [c for c in cons if c[0] in ("station", "nstation")]
        coupled = [c for c in cons if c[0] == "sbefore"]

        poss = []
        for w in self._block_worlds:
            pos = dict(zip(self.people, w))
            if all(self._holds(c, pos, None) for c in block_only):
                poss.append(pos)
        if not poss:
            return []
        stats = [s for s in self._station_worlds
                 if all(self._holds(c, None, s) for c in station_only)]
        if not stats:
            return []
        if not coupled:
            out = [(p, s) for p in poss for s in stats]
            return out[:limit] if limit else out
        out = []
        for p in poss:
            for s in stats:
                if all(self._holds(c, p, s) for c in coupled):
                    out.append((p, s))
                    if limit and len(out) >= limit:
                        return out
        return out

    def sat(self, cons):
        return bool(self.solve(cons, limit=1))

    # -- rendering ----------------------------------------------------------
    def render(self, world):
        """One world as the answer format: every person, station only for
        the people the header puts on one."""
        pos, stat = world
        out = {}
        for p in self.people:
            rec = {"block": self.blocks[pos[p]]}
            if p in stat:
                rec["station"] = stat[p]
            out[p] = rec
        return out


# ---------------------------------------------------------------------------
# Minimal unsatisfiable subsets
# ---------------------------------------------------------------------------

def mus(problem, indexed, order=None):
    """A minimal unsatisfiable subset of `indexed`, by linear deletion.

    `indexed` is a list of (key, constraint). Returns the list of keys of a
    subset that is unsatisfiable and whose every proper subset is satisfiable
    -- exactly the scorer's rule: the cited statements cannot all hold at
    once, and dropping any one of them leaves a set that can.

    `order` optionally reorders the deletion sweep. Deletion keeps whichever
    statements it reaches last, so sweeping in a chosen order is how a caller
    expresses a preference between the several cores an item usually has.
    """
    items = list(indexed)
    if order is not None:
        items.sort(key=order)
    if problem.sat([c for _, c in items]):
        return None
    keep = items
    i = 0
    while i < len(keep):
        trial = keep[:i] + keep[i + 1:]
        if not problem.sat([c for _, c in trial]):
            keep = trial          # statement i was not needed
        else:
            i += 1                # statement i is load-bearing, move on
    return [k for k, _ in keep]


def all_muses(problem, indexed, cap=24):
    """Several distinct cores, found by sweeping deletion from different
    starting points. Not an exhaustive enumeration -- it is here so the
    citation layer has a choice between cores, not so it has all of them."""
    seen, out = set(), []
    n = len(indexed)
    for start in range(min(n, cap)):
        rot = indexed[start:] + indexed[:start]
        m = mus(problem, rot)
        if m is None:
            return []
        sig = frozenset(m)
        if sig not in seen:
            seen.add(sig)
            out.append(m)
    return out


# Measured precision of each emitted code kind -- given that the model wrote a
# code of this kind, how often the line actually says that. From 60 items,
# `dev/calibrate.py`, scored against the reference parser:
#
#   between 97%   station 94%   nstation 93%   before 92%
#   sbefore 89%   imm 77%       nblock 74%     block 71%
#
# The shape is intelligible rather than arbitrary. The two absolute forms are
# the least reliable because the model's characteristic error is to *resolve* a
# relative statement into an absolute one -- "Rohan is on the block directly
# after Meera" came back as `BLOCK Rohan 11:00` seven times -- and an invented
# absolute placement eliminates far more worlds than a wrong relative one.
# This order is used only to choose which of two colliding constraints to
# disbelieve; it never changes how a constraint is interpreted.
TRUST = {"between": 8, "station": 7, "nstation": 6, "before": 5,
         "sbefore": 4, "imm": 3, "nblock": 2, "block": 1}


def trust(c):
    return TRUST.get(c[0], 0)


def pick_core(problem, indexed, min_size=3):
    """The core to cite.

    Every minimal conflicting set is a correct answer, so this chooses only
    between correct ones -- when the extraction is right. When it is not, the
    choice matters: a two-statement core means two extracted constraints
    collide directly, which on this task is far more often a mistranslation
    (the same person placed on two blocks by two different readings) than a
    contradiction the notes actually contain. The brief says every conflicting
    set on this set has at least three statements in it, so a larger core is
    preferred where one exists, and the smallest is the fallback.
    """
    cores = all_muses(problem, indexed)
    if not cores:
        return None
    by_key = dict(indexed)
    big = [c for c in cores if len(c) >= min_size]
    pool = big or cores
    # among cores of the same size, cite the one built from the code kinds the
    # extractor is measured to get right most often
    return min(pool, key=lambda c: (len(c),
                                    -min(trust(by_key[k]) for k in c)))


def least_trusted(indexed_core, by_key):
    """The constraint in a core to disbelieve first."""
    return min(indexed_core, key=lambda k: trust(by_key[k]))
