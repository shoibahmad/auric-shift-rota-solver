"""Verify the review archive before it is sent.

Static checks only; dev/check_zip_live.sh does the extract-and-run half.

    python3 dev/check_zip.py [path]
"""
import hashlib
import io
import os
import py_compile
import re
import sys
import tempfile
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import glob

if len(sys.argv) > 1:
    ZIP = sys.argv[1]
else:
    found = sorted(glob.glob(os.path.join(ROOT, "dist", "*.zip")))
    if not found:
        sys.exit("No .zip in dist/. Build one with dev/build_review_zip.py")
    if len(found) > 1:
        sys.exit(f"Several archives in dist/, name one: "
                 f"{[os.path.basename(f) for f in found]}")
    ZIP = found[0]

# The archive may have been renamed for sending; the folder inside it has not,
# so take the prefix from the file rather than assuming it.
with zipfile.ZipFile(ZIP) as _z:
    tops = {n.split("/")[0] for n in _z.namelist()}
if len(tops) != 1:
    sys.exit(f"expected one top-level folder, found {sorted(tops)}")
PREFIX = tops.pop() + "/"

OK, BAD = [], []


def check(cond, label, detail=""):
    (OK if cond else BAD).append((label, detail))


z = zipfile.ZipFile(ZIP)
names = z.namelist()
inner = [n[len(PREFIX):] for n in names if n.startswith(PREFIX)]

# -- 1. integrity -----------------------------------------------------------
check(z.testzip() is None, "archive integrity (CRC of every member)")
check(all(n.startswith(PREFIX) for n in names),
      "every path under a single top-level folder")
check(not any(".." in n or n.startswith("/") for n in names),
      "no path traversal (no .. or absolute paths)")

# -- 2. required content ----------------------------------------------------
REQUIRED = [
    "run", "run.cmd", "requirements.txt", "README.md", "WRITEUP.md",
    "ABLATION.md", "score.py", "verify.py", "ablate.py", "items.json",
    "visible_key.json", "example_answers.json", ".env.example",
    "rota/__init__.py", "rota/main.py", "rota/client.py", "rota/extract.py",
    "rota/pipeline.py", "rota/solver.py",
    "results/run_1x.json", "results/run_3x.json", "results/run_10x.json",
    "fixtures/extraction_1x.json", "fixtures/extraction_3pass.json",
    "fixtures/extraction_5pass.json",
]
miss = [f for f in REQUIRED if f not in inner]
check(not miss, f"all {len(REQUIRED)} required files present", str(miss))

check(sum(1 for f in inner if f.startswith("fixtures/scores/")) >= 100,
      "recorded scores shipped (headline reproduces offline)",
      f"{sum(1 for f in inner if f.startswith('fixtures/scores/'))} files")
check(sum(1 for f in inner if f.startswith("dev/") and f.endswith(".py")) >= 20,
      "dev measurement scripts shipped",
      f"{sum(1 for f in inner if f.startswith('dev/') and f.endswith('.py'))}")

# -- 3. nothing that should not travel --------------------------------------
JUNK = r"__pycache__|\.venv|(^|/)runs/|(^|/)interview/|(^|/)\.git/|\.zip$|" \
       r"CANDIDATE_BRIEF|(^|/)(answers|trace|nosolver|a_)[^/]*\.json$|\.pyc$"
junk = [f for f in inner if re.search(JUNK, f)]
check(not junk, "no junk, run artifacts or private material", str(junk[:5]))

# -- 4. secrets -------------------------------------------------------------
has_env = ".env" in inner
if has_env:
    body = z.read(PREFIX + ".env").decode()
    m = re.search(r"OPENROUTER_API_KEY=(sk-or-v1-[0-9a-f]{40,})", body)
    check(bool(m), ".env carries a well-formed key (included on request)",
          f"sk-or-v1-{m.group(1)[9:17]}..." if m else "MALFORMED")
    check("ibm-granite/granite-4.2-8b" in body, ".env names the fixed model")
    check("openrouter.ai/api/v1" in body, ".env names the provided endpoint")
else:
    check(True, ".env excluded (no key in archive)")

# the key must not be loose in any OTHER file
others = [f for f in inner if f != ".env"
          and re.search(r"sk-or-v1-[0-9a-f]{40,}",
                        z.read(PREFIX + f).decode("utf-8", "ignore"))]
check(not others, "no key in any file other than .env", str(others))

# -- 5. the launcher ---------------------------------------------------------
info = z.getinfo(PREFIX + "run")
mode = (info.external_attr >> 16) & 0o777
check(bool(mode & 0o111), "`run` is executable in the archive", oct(mode))
raw = z.read(PREFIX + "run")
check(b"\r\n" not in raw, "`run` has LF endings (CRLF breaks the shebang)")
check(raw.startswith(b"#!"), "`run` has a shebang",
      raw.split(b"\n")[0].decode())

# -- 6. the python actually compiles ----------------------------------------
bad = []
with tempfile.TemporaryDirectory() as td:
    for f in [x for x in inner if x.endswith(".py")]:
        p = os.path.join(td, os.path.basename(f))
        io.open(p, "wb").write(z.read(PREFIX + f))
        try:
            py_compile.compile(p, doraise=True)
        except Exception:                                        # noqa: BLE001
            bad.append(f)
check(not bad, f"all {sum(1 for x in inner if x.endswith('.py'))} "
      f".py files compile", str(bad))

# -- 7. not stale: archive matches the working tree -------------------------
stale = []
for f in ["README.md", "WRITEUP.md", "ABLATION.md", "requirements.txt",
          "rota/pipeline.py", "rota/solver.py", "rota/client.py",
          "rota/extract.py", "rota/main.py", "run", "score.py", "verify.py"]:
    disk = io.open(os.path.join(ROOT, f), "rb").read()
    arc = z.read(PREFIX + f)
    if f == "run":
        disk = disk.replace(b"\r\n", b"\n")
    if hashlib.sha256(disk).digest() != hashlib.sha256(arc).digest():
        stale.append(f)
check(not stale, "archive matches the current working tree", str(stale))

# -- 8. the documents are the finished ones ---------------------------------
w = z.read(PREFIX + "WRITEUP.md").decode()
check("0.481" in w and "n=15" in w.replace("| 15 |", "n=15"),
      "WRITEUP carries the final pooled figures")
a = z.read(PREFIX + "ABLATION.md").decode()
check("<!--" not in a, "ABLATION.md has no unfilled placeholders")
check(a.count("| `") >= 10, "ABLATION.md has the full arm table",
      f"{a.count('| `')} rows")

# ---------------------------------------------------------------------------
size = os.path.getsize(ZIP)
print(f"{ZIP}")
print(f"{size/1024:.0f} KB, {len(names)} entries\n")
print("=" * 70)
print(f"PASS {len(OK)}   FAIL {len(BAD)}")
print("=" * 70)
for lab, det in OK:
    print(f"  ok    {lab}" + (f"  [{det}]" if det else ""))
for lab, det in BAD:
    print(f"  FAIL  {lab}" + (f"  [{det}]" if det else ""))
sys.exit(1 if BAD else 0)
