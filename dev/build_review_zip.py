"""Build the archive sent for review.

An explicit manifest rather than "everything tracked", so what ships is a
decision rather than an accident, and so the reason each group is included can
be written down next to it.

    python3 dev/build_review_zip.py [--with-env]

`.env` is excluded by default. The brief says "Keep the key private and do not
commit `.env` or the key to your submission repository", the graders re-run
against their own endpoint, and a key that travels by email outlives the review.
`--with-env` overrides that, deliberately and visibly.
"""
import argparse
import os
import re
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAME = "auric-shift-rota-solver"

# group -> (why it ships, [paths or (dir, pattern)])
MANIFEST = [
    ("the system", [
        "run", "run.cmd", "requirements.txt",
        "rota/__init__.py", "rota/main.py", "rota/client.py",
        "rota/extract.py", "rota/pipeline.py", "rota/solver.py",
    ]),
    ("what is read", [
        "README.md", "WRITEUP.md", "ABLATION.md", "ABLATION.template.md",
    ]),
    ("the task package, so it runs out of the box", [
        "items.json", "visible_key.json", "score.py", "example_answers.json",
    ]),
    ("checking a run", ["verify.py", "ablate.py"]),
    ("sample output, one run per budget", [("results", r".*")]),
    ("recorded extractions and scores: every claim reproduces with no "
     "model calls", [("fixtures", r".*")]),
    ("the measurements the writeup cites by name", [("dev", r"\.py$")]),
    ("setup", [".env.example", "requirements-dev.txt"]),
]

# Deliberately absent: CANDIDATE_BRIEF.md (theirs, not mine to return),
# .gitignore/.gitattributes (repository mechanics), runs/ (regenerable, 6.5 MB),
# interview/ (personal preparation), dist/ (this archive).


def collect():
    out = []
    for why, entries in MANIFEST:
        for e in entries:
            if isinstance(e, tuple):
                d, pat = e
                base = os.path.join(ROOT, d)
                for dp, _dn, fn in os.walk(base):
                    for f in sorted(fn):
                        rel = os.path.relpath(os.path.join(dp, f),
                                              ROOT).replace("\\", "/")
                        if re.search(pat, f) and "__pycache__" not in rel:
                            out.append((rel, why))
            else:
                out.append((e, why))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--with-env", action="store_true",
                    help="include the real .env (the brief says not to)")
    a = ap.parse_args()

    files = collect()
    if a.with_env:
        files.append((".env", "THE REAL API KEY, included on request"))

    missing = [f for f, _ in files if not os.path.exists(os.path.join(ROOT, f))]
    if missing:
        sys.exit(f"missing: {missing}")

    os.makedirs(os.path.join(ROOT, "dist"), exist_ok=True)
    out = os.path.join(ROOT, "dist", f"{NAME}.zip")
    if os.path.exists(out):
        os.remove(out)

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for rel, _why in files:
            src = os.path.join(ROOT, rel)
            info = zipfile.ZipInfo(f"{NAME}/{rel}")
            info.compress_type = zipfile.ZIP_DEFLATED
            data = open(src, "rb").read()
            # the launcher must arrive executable, and with LF endings
            if rel in ("run",):
                info.external_attr = 0o755 << 16
                data = data.replace(b"\r\n", b"\n")
            else:
                info.external_attr = 0o644 << 16
            info.date_time = (2026, 1, 1, 0, 0, 0)
            z.writestr(info, data)

    size = os.path.getsize(out)
    print(f"wrote {out}  ({size / 1024:.0f} KB, {len(files)} files)\n")
    last = None
    for rel, why in files:
        if why != last:
            print(f"  {why}:")
            last = why
        print(f"    {rel}")
    if a.with_env:
        print("\n  *** .env IS IN THIS ARCHIVE — it carries a live API key ***")


if __name__ == "__main__":
    main()
