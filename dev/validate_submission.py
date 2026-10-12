"""Check the submission against every hard requirement in the brief.

Static checks plus one intercepted request, so the claims about headers and
sampling parameters are verified on the wire rather than by reading the source.
Does not need an API key and makes no real model call.

    python3 dev/validate_submission.py
"""
import io
import json
import os
import re
import subprocess
import sys

# Model output can contain any character; the Windows console codepage
# cannot. Printing a raw reply must not crash a measurement script.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

PASS, FAIL, WARN = [], [], []


def check(ok, label, detail=""):
    (PASS if ok else FAIL).append((label, detail))


def warn(label, detail=""):
    WARN.append((label, detail))


def read(path):
    return io.open(os.path.join(ROOT, path), encoding="utf-8").read()


def git(*args):
    return subprocess.run(["git"] + list(args), cwd=ROOT,
                          capture_output=True, text=True).stdout.strip()


# ---------------------------------------------------------------------------
# 1. The entrypoint
# ---------------------------------------------------------------------------
check(os.path.exists(os.path.join(ROOT, "run")), "repo-root `run` launcher exists")
check(os.path.exists(os.path.join(ROOT, "run.cmd")), "`run.cmd` for Windows exists")

mode = git("ls-files", "-s", "run").split()[0] if git("ls-files", "run") else ""
check(mode == "100755", "`run` is committed executable (100755)", f"mode={mode}")

eol = git("ls-files", "--eol", "run")
check("w/lf" in eol and "i/lf" in eol,
      "`run` has LF endings (CRLF would break the shebang)", eol)

runsrc = read("run")
check(runsrc.startswith("#!"), "`run` has a shebang", runsrc.splitlines()[0])
check("rota.main" in runsrc, "`run` dispatches to the documented module")

# the brief's exact invocation shape
import rota.main as rmain                                        # noqa: E402
ap_src = read("rota/main.py")
check('"--budget"' in ap_src and '"--out"' in ap_src,
      "entrypoint accepts --budget and --out")
check(set(rmain.BUDGETS) == {"1x", "3x", "10x"},
      "budgets are exactly 1x / 3x / 10x", str(sorted(rmain.BUDGETS)))
check(rmain.BUDGETS == {"1x": 1, "3x": 3, "10x": 10},
      "budget caps map to 1 / 3 / 10 calls per item")

# ---------------------------------------------------------------------------
# 2. Dependencies and Python version
# ---------------------------------------------------------------------------
reqs = [l.strip() for l in read("requirements.txt").splitlines() if l.strip()]
check(bool(reqs) and all("==" in r for r in reqs),
      "every dependency is pinned with ==", "; ".join(reqs))
readme = read("README.md")
check(re.search(r"Python\s*\*?\*?3\.\d+", readme) is not None,
      "README states the Python version",
      (re.search(r"Python[^\n]{0,60}", readme) or [""])[0])

# ---------------------------------------------------------------------------
# 3. Secrets
# ---------------------------------------------------------------------------
tracked = git("ls-files").splitlines()
check(".env" not in tracked, "`.env` is NOT tracked by git")
check(".gitignore" in tracked and ".env" in read(".gitignore"),
      "`.env` is gitignored")
leaks = []
for f in tracked:
    if f in (".env.example", "CANDIDATE_BRIEF.md"):
        continue
    try:
        body = read(f)
    except Exception:
        continue
    if re.search(r"sk-or-v1-[0-9a-f]{16,}", body):
        leaks.append(f)
check(not leaks, "no real API key in any tracked file", str(leaks))

# ---------------------------------------------------------------------------
# 4. No frontier model, no fine-tuning, no per-item logic in the pipeline
# ---------------------------------------------------------------------------
pipeline_src = "".join(read(f"rota/{f}") for f in
                       ("client.py", "extract.py", "pipeline.py", "solver.py",
                        "main.py", "__init__.py"))
banned = re.findall(r"(?i)\b(claude|gpt-4|gpt-3|anthropic|openai\.com|gemini|"
                    r"sonnet|opus|mistral|llama)\b", pipeline_src)
check(not banned, "no frontier-model reference in the answering pipeline",
      str(sorted(set(banned))))
check("fine_tune" not in pipeline_src and "finetune" not in pipeline_src,
      "no fine-tuning in the pipeline")

item_ids = re.findall(r"B2-\d{3}", pipeline_src)
check(not item_ids, "no item id hard-coded in the pipeline", str(set(item_ids)))
check("dev." not in pipeline_src and "refparse" not in pipeline_src,
      "the pipeline does not import the dev/ regex reference parser")

default_model = re.search(r'DEFAULT_MODEL\s*=\s*"([^"]+)"', read("rota/client.py"))
check(default_model and default_model.group(1) == "ibm-granite/granite-4.2-8b",
      "default model is the fixed weak model",
      default_model.group(1) if default_model else "not found")

# ---------------------------------------------------------------------------
# 5. On-the-wire check: headers and sampling parameters
# ---------------------------------------------------------------------------
import httpx                                                     # noqa: E402
from rota.client import ModelClient                              # noqa: E402

captured = {}


def handler(request: httpx.Request) -> httpx.Response:
    captured["headers"] = dict(request.headers)
    captured["body"] = json.loads(request.content.decode())
    captured["url"] = str(request.url)
    return httpx.Response(200, json={
        "id": "x", "object": "chat.completion", "created": 0,
        "model": "ibm-granite/granite-4.2-8b",
        "choices": [{"index": 0, "finish_reason": "stop",
                     "message": {"role": "assistant", "content": "1. -"}}],
    })


os.environ.setdefault("OPENROUTER_API_KEY", "sk-or-v1-TESTONLY")
cli = ModelClient(budget=3, api_key="sk-or-v1-TESTONLY")
cli.client = cli.client.copy(http_client=httpx.Client(
    transport=httpx.MockTransport(handler)))
cli.chat("B2-042", [{"role": "user", "content": "ping"}], max_tokens=16)

h = {k.lower(): v for k, v in captured.get("headers", {}).items()}
b = captured.get("body", {})
check(h.get("x-item-id") == "B2-042",
      "X-Item-Id header carries the item id on a real request",
      f"x-item-id={h.get('x-item-id')!r}")
check(b.get("temperature") == 1.0, "temperature=1.0 on the wire",
      f"temperature={b.get('temperature')}")
check(b.get("top_p") == 0.95, "top_p=0.95 on the wire",
      f"top_p={b.get('top_p')}")
check(b.get("reasoning") == {"enabled": False},
      'extra_body reasoning {"enabled": false} on the wire',
      f"reasoning={b.get('reasoning')}")
check(b.get("model") == "ibm-granite/granite-4.2-8b",
      "the fixed model id is on the wire", f"model={b.get('model')}")

# budget enforcement, both directions
from rota.client import BudgetExceeded                           # noqa: E402
cli2 = ModelClient(budget=1, api_key="sk-or-v1-TESTONLY")
cli2.client = cli2.client.copy(http_client=httpx.Client(
    transport=httpx.MockTransport(handler)))
cli2.chat("B2-000", [{"role": "user", "content": "ping"}], max_tokens=8)
try:
    cli2.chat("B2-000", [{"role": "user", "content": "ping"}], max_tokens=8)
    check(False, "client refuses a call over the per-item cap")
except BudgetExceeded:
    check(True, "client refuses a call over the per-item cap (raises)")

# a failed call must not consume a second budget slot
fails = {"n": 0}


def flaky(request: httpx.Request) -> httpx.Response:
    fails["n"] += 1
    if fails["n"] < 2:
        return httpx.Response(503, json={"error": "transient"})
    return handler(request)


cli3 = ModelClient(budget=1, api_key="sk-or-v1-TESTONLY", max_retries=3)
cli3.client = cli3.client.copy(http_client=httpx.Client(
    transport=httpx.MockTransport(flaky)))
cli3.chat("B2-001", [{"role": "user", "content": "ping"}], max_tokens=8)
check(cli3.used("B2-001") == 1,
      "a retried transport failure counts as one logical call",
      f"used={cli3.used('B2-001')} after {fails['n']} attempts")

# ---------------------------------------------------------------------------
# 5b. Transfer robustness: the held-out set is generated from a different seed,
# so the item vocabulary may not be spelled the way the visible set spells it.
# A token must be accepted on what it DENOTES, and rejected when it denotes
# nothing. This is a regression guard: station names are lower-case in every
# visible header, which hid a bug that dropped every station constraint when
# they were not.
# ---------------------------------------------------------------------------
from rota.extract import parse_header as _ph, parse_one as _po    # noqa: E402
from rota.solver import Problem as _Prob                          # noqa: E402

HDR = ("Shift notes, Bay 4. 5 staff on the rota: Samuel, Tomas, Meera, Rohan, "
       "Ayesha. Blocks run 07:00, 09:00, 11:00, 13:00, 15:00, one person per "
       "block, and each person works exactly one block. There are 3 stations, "
       "one person on each: {st}. The people on a station are Samuel, Meera, "
       "Ayesha; the rest are on no station.\nx")

for label, st in [("lower-case", "intake, calibration, packing"),
                  ("capitalised", "Intake, Calibration, Packing")]:
    people, blocks, stations, holders = _ph(HDR.format(st=st))
    prob = _Prob(people, blocks, stations, holders)
    accepted = {
        "STATION Samuel Intake": "station",
        "STATION Samuel intake": "station",
        "NOT_STATION Meera packing": "nstation",
        "STATION_EARLIER Calibration Rohan": "sbefore",
        "BLOCK Tomas 9:00": "block",
        "BLOCK tomas 09:00": "block",
    }
    ok = True
    for code, kind in accepted.items():
        c = _po(code, prob)
        if c is None or c[0] != kind:
            ok = False
    check(ok, f"vocabulary resolved case-insensitively ({label} header)")
    # and the constraint must carry the HEADER's spelling, since the scorer
    # compares case-sensitively
    c = _po("STATION Samuel intake", prob)
    check(c is not None and c[2] in stations,
          f"constraint carries the header's spelling ({label})", str(c))
    # invented vocabulary is still refused
    refused = all(_po(x, prob) is None for x in
                  ("STATION Samuel reception", "BLOCK Nobody 09:00",
                   "EARLIER Samuel Gandalf"))
    check(refused, f"invented names and stations still rejected ({label})")

# ---------------------------------------------------------------------------
# 6. Deliverables
# ---------------------------------------------------------------------------
for f, label in [("WRITEUP.md", "the two pages"),
                 ("ABLATION.md", "the ablation table"),
                 ("ablate.py", "the ablation is reproducible"),
                 ("verify.py", "pre-flight verifier")]:
    check(os.path.exists(os.path.join(ROOT, f)), f"{label} ({f}) exists")

w = read("WRITEUP.md").lower()
required = {
    "states model-based vs symbolic": "extraction is model-based" in w,
    "how the model was characterised": "characterising the model" in w,
    "why each component exists": "why each component exists" in w,
    "what was built and removed": "built and then removed" in w,
    "where it breaks": "where it breaks" in w,
    "what you would do with a month": "with a month" in w,
    "different writers / phrasing transfer": "written by people" in w,
    "how many runs each number came from": "three runs" in w,
}
for label, ok in required.items():
    check(ok, f"writeup covers: {label}")

abl = read("ABLATION.md")
check("<!--" not in abl, "ABLATION.md has no unfilled placeholders")
arms = re.findall(r"\| `(-?\w+)` \|", abl)
check(len(set(arms)) >= 8, "ablation covers every component arm",
      f"{len(set(arms))} arms: {sorted(set(arms))}")

# answers.json format, on the shipped samples
sys.path.insert(0, ROOT)
items = json.load(io.open(os.path.join(ROOT, "items.json"), encoding="utf-8"))
ids = {i["id"] for i in items}
for b in ("1x", "3x", "10x"):
    p = os.path.join(ROOT, "results", f"run_{b}.json")
    if not os.path.exists(p):
        warn(f"sample output for {b} missing")
        continue
    sub = json.load(io.open(p, encoding="utf-8"))
    shapes_ok = True
    for iid, v in sub.items():
        c = v.get("case")
        if c == "unique" and not isinstance(v.get("assignment"), dict):
            shapes_ok = False
        if c == "ambiguous" and not isinstance(v.get("assignments"), list):
            shapes_ok = False
        if c == "inconsistent" and not isinstance(v.get("conflicts"), list):
            shapes_ok = False
    check(set(sub) == ids and shapes_ok,
          f"results/run_{b}.json covers every item in a legal shape",
          f"{len(sub)} entries")

# ---------------------------------------------------------------------------
# 7. Every dev script still runs
#
# The writeup cites these by name, so a signature change in one that silently
# breaks another is a real defect -- it happened once, when replay() was
# refactored and check_model_sensitivity.py stopped running.
# ---------------------------------------------------------------------------
import py_compile                                                # noqa: E402
import glob                                                      # noqa: E402

for path in sorted(glob.glob(os.path.join(ROOT, "dev", "*.py"))):
    name = os.path.basename(path)
    try:
        py_compile.compile(path, doraise=True)
        ok, detail = True, ""
    except Exception as exc:                                     # noqa: BLE001
        ok, detail = False, repr(exc)[:90]
    check(ok, f"dev/{name} compiles", detail)

# the API-free ones are actually executed, with their real arguments
RUNNABLE = [
    ("dev/check_semantics.py", []),
    ("dev/check_entailment.py", []),
    ("dev/check_null_family.py", []),
    ("dev/check_restatements.py", []),
    ("dev/refparse.py", []),
    ("dev/check_error_structure.py", ["runs/p5_calls.json"]),
    ("dev/check_model_sensitivity.py", ["runs/fmt_dash_calls.json"]),
    ("dev/replay.py", ["runs/fmt_dash_calls.json"]),
    ("dev/calibrate.py", ["runs/fmt_dash_calls.json"]),
    ("dev/diag_extract.py", ["runs/fmt_dash_calls.json"]),
]
for script, args in RUNNABLE:
    if args and not all(os.path.exists(os.path.join(ROOT, a)) for a in args):
        warn(f"{script} not executed (needs a recorded calls log)",
             " ".join(args))
        continue
    r = subprocess.run([sys.executable, script] + args, cwd=ROOT,
                       capture_output=True, text=True, timeout=900)
    check(r.returncode == 0, f"{script} runs clean",
          (r.stderr.strip().splitlines() or [""])[-1][:90])

# ---------------------------------------------------------------------------
print("=" * 72)
print(f"PASS {len(PASS)}   FAIL {len(FAIL)}   WARN {len(WARN)}")
print("=" * 72)
for label, detail in PASS:
    print(f"  ok    {label}" + (f"  [{detail}]" if detail else ""))
for label, detail in WARN:
    print(f"  warn  {label}" + (f"  [{detail}]" if detail else ""))
for label, detail in FAIL:
    print(f"  FAIL  {label}" + (f"  [{detail}]" if detail else ""))
sys.exit(1 if FAIL else 0)
