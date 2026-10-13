"""Run every documented command and record exactly what it printed.

Writes runs/command_outputs.json for dev/build_commands_pdf.py. Nothing is
transcribed by hand: whatever a command prints, including a failure, is what
the PDF shows.

Commands that would take hours are run in a clearly-labelled reduced form and
marked `reduced`, with the full invocation recorded alongside so the PDF can
print the real command and the honest note that its output came from a smaller
run.

    python3 dev/capture_commands.py [--skip-api]
"""
import argparse
import io
import json
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable

# section, command shown, command actually run, needs_api, reduced-note
CMDS = [
    ("Setup", "pip install -r requirements.txt",
     [PY, "-m", "pip", "install", "-q", "-r", "requirements.txt"], False, None),
    ("Setup", "python -c \"import openai, sys; print(sys.version, openai.__version__)\"",
     [PY, "-c", "import openai,sys;print(sys.version.split()[0],'openai',openai.__version__)"],
     False, None),

    ("The entrypoint", "./run items.json --budget 1x --out answers_1x.json --trace trace_1x.json",
     [PY, "-m", "rota.main", "items.json", "--budget", "1x",
      "--out", "runs/cmd/answers_1x.json", "--trace", "runs/cmd/trace_1x.json",
      "--workers", "10"], True, None),
    ("The entrypoint", "python3 score.py visible_key.json answers_1x.json",
     [PY, "score.py", "visible_key.json", "runs/cmd/answers_1x.json"], False, None),
    ("The entrypoint", "python3 verify.py items.json answers_1x.json --trace trace_1x.json",
     [PY, "verify.py", "items.json", "runs/cmd/answers_1x.json",
      "--trace", "runs/cmd/trace_1x.json"], False, None),

    ("The entrypoint", "./run items.json --budget 3x --out answers_3x.json --trace trace_3x.json",
     [PY, "-m", "rota.main", "items.json", "--budget", "3x",
      "--out", "runs/cmd/answers_3x.json", "--trace", "runs/cmd/trace_3x.json",
      "--workers", "10"], True, None),
    ("The entrypoint", "python3 score.py visible_key.json answers_3x.json",
     [PY, "score.py", "visible_key.json", "runs/cmd/answers_3x.json"], False, None),
    ("The entrypoint", "python3 verify.py items.json answers_3x.json --trace trace_3x.json",
     [PY, "verify.py", "items.json", "runs/cmd/answers_3x.json",
      "--trace", "runs/cmd/trace_3x.json"], False, None),

    ("The entrypoint", "./run items.json --budget 10x --out answers_10x.json --trace trace_10x.json",
     [PY, "-m", "rota.main", "items.json", "--budget", "10x",
      "--out", "runs/cmd/answers_10x.json", "--trace", "runs/cmd/trace_10x.json",
      "--workers", "10"], True, None),
    ("The entrypoint", "python3 score.py visible_key.json answers_10x.json",
     [PY, "score.py", "visible_key.json", "runs/cmd/answers_10x.json"], False, None),

    ("Ablation arms by hand",
     "./run items.json --budget 1x --out nosolver.json --drop solver",
     [PY, "-m", "rota.main", "items.json", "--budget", "1x",
      "--out", "runs/cmd/nosolver.json", "--drop", "solver",
      "--workers", "10"], True, None),
    ("Ablation arms by hand", "python3 score.py visible_key.json nosolver.json",
     [PY, "score.py", "visible_key.json", "runs/cmd/nosolver.json"], False, None),

    ("Ablation",
     "python3 ablate.py --items items.json --key visible_key.json \\\n"
     "    --budgets 1x,3x,10x --runs 3 --plan full --outdir runs/ablation",
     [PY, "ablate.py", "--items", "items.json", "--key", "visible_key.json",
      "--budgets", "1x", "--runs", "1", "--arms", "full,-mus",
      "--outdir", "runs/cmd/abl", "--workers", "10"], True,
     "The full grid is 90 cells and takes about two hours. Shown here: the "
     "same command reduced to --budgets 1x --runs 1 --arms full,-mus, so the "
     "output is real but small. The complete table it produces is ABLATION.md."),

    ("Ablation", "python3 dev/replay.py fixtures/extraction_1x.json \\\n"
     "    fixtures/extraction_3pass.json fixtures/extraction_5pass.json",
     [PY, "dev/replay.py", "fixtures/extraction_1x.json",
      "fixtures/extraction_3pass.json", "fixtures/extraction_5pass.json"],
     False, None),
    ("Ablation", "python3 dev/build_ablation.py --outdir runs/ablation \\\n"
     "    --replay runs/replay_table.md",
     [PY, "dev/build_ablation.py", "--outdir", "runs/ablation",
      "--replay", "runs/replay_table.md"], False, None),

    ("Measurements (no model calls)",
     "python3 dev/check_semantics.py", [PY, "dev/check_semantics.py"], False, None),
    ("Measurements (no model calls)",
     "python3 dev/check_entailment.py", [PY, "dev/check_entailment.py"], False, None),
    ("Measurements (no model calls)",
     "python3 dev/check_null_family.py", [PY, "dev/check_null_family.py"], False, None),
    ("Measurements (no model calls)",
     "python3 dev/check_restatements.py", [PY, "dev/check_restatements.py"], False, None),
    ("Measurements (no model calls)",
     "python3 dev/refparse.py", [PY, "dev/refparse.py"], False, None),
    ("Measurements (no model calls)",
     "python3 dev/check_error_structure.py fixtures/extraction_5pass.json",
     [PY, "dev/check_error_structure.py", "fixtures/extraction_5pass.json"],
     False, None),
    ("Measurements (no model calls)",
     "python3 dev/check_model_sensitivity.py fixtures/extraction_1x.json",
     [PY, "dev/check_model_sensitivity.py", "fixtures/extraction_1x.json"],
     False, None),
    ("Measurements (no model calls)",
     "python3 dev/calibrate.py fixtures/extraction_1x.json",
     [PY, "dev/calibrate.py", "fixtures/extraction_1x.json"], False, None),
    ("Measurements (no model calls)",
     "python3 dev/tune_aggregation.py fixtures/extraction_3pass.json",
     [PY, "dev/tune_aggregation.py", "fixtures/extraction_3pass.json"],
     False, None),
    ("Measurements (no model calls)",
     "python3 dev/summarise_runs.py", [PY, "dev/summarise_runs.py"], False, None),

    ("Checks", "python3 dev/validate_submission.py",
     [PY, "dev/validate_submission.py"], False, None),
    ("Checks", "python3 dev/page_count.py WRITEUP.md",
     [PY, "dev/page_count.py", "WRITEUP.md"], False, None),
    ("Checks", "python3 score.py visible_key.json visible_key.json",
     [PY, "score.py", "visible_key.json", "visible_key.json"], False, None),
]


def clean(txt):
    """Progress bars use \\r; keep only what a terminal would finally show."""
    out = []
    for line in txt.replace("\r\n", "\n").split("\n"):
        out.append(line.split("\r")[-1] if "\r" in line else line)
    txt = "\n".join(out)
    txt = re.sub(r"\n{3,}", "\n\n", txt)
    return txt.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-api", action="store_true",
                    help="skip commands that spend model calls")
    ap.add_argument("--out", default="runs/command_outputs.json")
    a = ap.parse_args()

    os.makedirs(os.path.join(ROOT, "runs/cmd"), exist_ok=True)
    results = []
    for section, shown, argv, needs_api, note in CMDS:
        if needs_api and a.skip_api:
            continue
        t0 = time.time()
        sys.stderr.write(f"  running: {shown.splitlines()[0][:70]}\n")
        sys.stderr.flush()
        try:
            r = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True,
                               timeout=5400, encoding="utf-8", errors="replace")
            out = clean((r.stdout or "") + ("\n" + r.stderr if r.stderr else ""))
            code = r.returncode
        except subprocess.TimeoutExpired:
            out, code = "(timed out)", -1
        results.append({"section": section, "command": shown, "output": out,
                        "exit": code, "seconds": round(time.time() - t0, 1),
                        "note": note})

    with io.open(os.path.join(ROOT, a.out), "w", encoding="utf-8",
                 newline="\n") as fh:
        json.dump(results, fh, indent=1, ensure_ascii=False)
    bad = [r["command"] for r in results if r["exit"] != 0]
    print(f"\ncaptured {len(results)} commands -> {a.out}")
    print(f"non-zero exits: {bad if bad else 'none'}")


if __name__ == "__main__":
    main()
