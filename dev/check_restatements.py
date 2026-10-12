"""DEV ONLY. Why the restatement-agreement component was removed.

The scorer refuses a cited set containing two citations that normalise to the
same string, and it warns that a restatement normalises to the same string as
the line it restates. That implies a trap: cite a line and its restatement and
the answer is rejected however good the core is. A component was built to
avoid it -- group the lines that differ only by a prefix, force them to one
reading, never cite two from a group.

It never fires. On the visible set no two body lines normalise to the same
string: the "restatements" are re-phrasings, not re-hedgings.

    It bears repeating: Whichever way round Tomas and Rohan are, Meera is
    between them.
    Put Meera between Tomas and Rohan, though not necessarily next to either.

Those assert the same constraint in different words, so the scorer counts them
as two statements and a core may legitimately contain either. Grouping them
would need semantic matching, and the obvious symbolic proxy -- same set of
rota names mentioned -- also groups "A is earlier than B" with "A is next to
B", which are different constraints. So the component was removed rather than
guessed at.
"""
import json
import collections
import sys

sys.path.insert(0, ".")
from score import squash_stmt                                     # noqa: E402

items = json.load(open("items.json", encoding="utf-8"))
ident = 0
same_names = collections.Counter()
for it in items:
    lines = [l.strip() for l in it["text"].split("\n")[1:] if l.strip()]
    counts = collections.Counter(squash_stmt(l) for l in lines)
    ident += sum(1 for v in counts.values() if v > 1)
print(f"body-line pairs that normalise identically, whole set: {ident}")
print("-> the duplicate-citation rejection cannot fire; component removed.")
