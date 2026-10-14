# Rota solving under a fixed, weak model

The weak model (`ibm-granite/granite-4.2-8b`) does one job here: translate each
line of the shift notes into one constraint from a closed vocabulary. It never
counts solutions, never decides whether an item is unique, ambiguous or
contradictory, and never chooses what to cite. All of that is done exactly, by
enumerating the 720 possible worlds of an item and reasoning over the set.

- **Constraint extraction is model-based.** Nothing in the answering pipeline
  pattern-matches the notes.
- **Everything downstream is symbolic**: world enumeration, case decision, and
  minimal-unsatisfiable-subset search for the citations.

| budget | macro exact match | n | observed range | per-kind (u / a / i) |
|---|---|---|---|---|
| 1x | **0.481 +/- 0.040** | 15 | 0.417 - 0.533 | 0.45 / 0.44 / 0.55 |
| 3x | **0.504 +/- 0.043** | 9 | 0.450 - 0.583 | 0.50 / 0.47 / 0.55 |
| 10x | **0.504 +/- 0.034** | 9 | 0.450 - 0.550 | 0.52 / 0.45 / 0.60 |
| the same model with no formal layer | **0.000 +/- 0.000** | 9 | - | 0.00 / 0.00 / 0.00 |

Provided scorer, `visible_key.json`; `dev/summarise_runs.py` pools them. 1x
carries n=15 because the `-vote` and `-repair` ablation cells at one call are
the same code path as `full` and so measure the shipped system again. A single
re-run lands anywhere in the observed range, not on the mean -- the spread is a
property of `temperature=1.0`, not of the system. See
[WRITEUP.md](WRITEUP.md) for how the model was characterised, why each
component exists, what was removed, and where the system breaks --
including why the curve is nearly flat.

## Running it

Python **3.13** (developed on 3.13.7; needs 3.9+).

```bash
pip install -r requirements.txt           # openai==2.35.1, nothing else
# optional: pip install -r requirements-dev.txt   # only for the PDF tools
cp .env.example .env                      # then put the endpoint key in it
./run items.json --budget 1x  --out answers.json
./run items.json --budget 3x  --out answers_3x.json
./run items.json --budget 10x --out answers_10x.json
```

`run` is a shell launcher over `python3 -m rota.main`; `run.cmd` is the same for
Windows. Set `PYTHON=python3.13` to pick an interpreter.

**On Windows, check which Python you are using.** `python3` and `python` are
often different interpreters there — `python3` frequently resolves to the
Microsoft Store stub — so a dependency installed for one is missing for the
other. Install and run with the same one, e.g. `python -m pip install -r
requirements.txt` then `PYTHON=python ./run ...`. Anything that needs the
endpoint now says so explicitly instead of raising a bare
`ModuleNotFoundError`.

Scoring, with the provided scorer:

```bash
python3 score.py visible_key.json answers.json
```

Before trusting a run, check the things that are auto-fails rather than low
scores — output format, citations occurring verbatim and quoting exactly one
line each, every assignment naming the whole rota, and the budget holding in
both directions:

```bash
./run items.json --budget 3x --out answers.json --trace trace.json
python3 verify.py items.json answers.json --trace trace.json
```

A sample of actual output, one run per budget, is in [results/](results/).

### Call settings and the budget

Every model call goes through `rota/client.py`, which is the only place that
talks to the endpoint. It pins `temperature=1.0`, `top_p=0.95` and
`extra_body={"reasoning": {"enabled": False}}`, and sends
`X-Item-Id: <item id>` on every request.

The budget is enforced locally as well as at the graders' proxy: the client
refuses the call that would exceed it and raises, so an orchestration bug
fails loudly here instead of quietly over-running at grading time. Every item
gets at least one call; `1x` is exactly one.

## The ablation

```bash
# the live table: every arm re-run end to end, three runs per cell
python3 ablate.py --items items.json --key visible_key.json \
    --budgets 1x,3x,10x --runs 3 --plan focused --outdir runs/ablation

# the symbolic arms again, replayed over recorded extractions: no new calls,
# and so no sampling noise in the comparison
python3 dev/replay.py fixtures/extraction_1x.json fixtures/extraction_3pass.json \
    > runs/replay_table.md

# assemble ABLATION.md from the tracked template and the two tables
python3 dev/build_ablation.py --outdir runs/ablation \
    --replay runs/replay_table.md
```

`ablate.py` writes, for every cell of the table, the `answers.json`,
`score.json` and per-item trace that produced it, so any number can be traced
back to the answers behind it. **[ABLATION.md](ABLATION.md) is the deliverable.**
[ABLATION.template.md](ABLATION.template.md) is its source — the prose, with
two placeholders that `dev/build_ablation.py` fills from
`runs/ablation/*_score.json` and the replay output, so no figure in the
deliverable is ever hand-typed. Edit the template; regenerate the other.

Individual arms can be run by hand:

```bash
./run items.json --budget 3x --out /tmp/a.json --drop repair
./run items.json --budget 1x --out /tmp/b.json --drop solver
```

## Layout

| path | what it is |
|---|---|
| [run](run), [run.cmd](run.cmd) | the documented entrypoint |
| [rota/solver.py](rota/solver.py) | world enumeration, constraint semantics, minimal-conflict search |
| [rota/extract.py](rota/extract.py) | the constraint vocabulary, the prompt, the strict parser |
| [rota/pipeline.py](rota/pipeline.py) | budget-aware orchestration: when to spend a call and on what |
| [rota/client.py](rota/client.py) | the only call site: pinned sampling, `X-Item-Id`, budget cap |
| [rota/main.py](rota/main.py) | CLI, parallelism, budget reporting |
| [ablate.py](ablate.py) | reproduces the ablation table |
| [verify.py](verify.py) | pre-flight checks for the four auto-fail conditions |
| [dev/](dev/) | characterisation probes and measurements; not part of the pipeline |
| [fixtures/](fixtures/) | recorded extractions and scores, so every measurement replays from a clean checkout with no model calls |

`dev/` is kept because the writeup's claims come from it, and each script
reproduces exactly one measurement:

| script | the claim it establishes |
|---|---|
| `probe_model.py` | the model cannot do the task end to end, and is near-perfect at spotting inert lines |
| `refparse.py` | a regex reference parser over the *visible* pool, for per-line ground truth |
| `check_semantics.py` | reference parser + solver = macro 1.0000, so the symbolic layer is correct |
| `check_entailment.py` | over-reading wishes is free (64/64 entailed), past-tense station history is not (0/25) |
| `check_null_family.py` | over-reading unresolved questions is free too (31/31) |
| `calibrate.py` | per-emitted-code precision: the `TRUST` order in `solver.py` |
| `probe_format.py`, `probe_format2.py` | reply-format variants; how the preamble was stopped |
| `replay.py` | the symbolic ablation arms, over fixed extractions, with no sampling noise |
| `tune_aggregation.py` | every way of combining extractions loses to selecting one |
| `check_error_structure.py` | 4% of lines are wrong identically every time; 0.47 is the resampling ceiling |
| `check_restatements.py` | why the restatement-agreement component was removed |
| `check_model_sensitivity.py` | the answers depend on the model's output |
| `build_ablation.py` | assembles `ABLATION.md` from the template and the two result tables |
| `measure_variance.py` | run-to-run spread of the full system, which bounds every other claim |
| `summarise_runs.py` | pools every run into the n=9 headline figures |
| `validate_submission.py` | 77 checks against the brief, incl. headers and sampling on an intercepted request |

`refparse.py` is regex over the visible phrasing pool and is used **only** for
measurement — to pin down the generator's semantics and to test the solver
against the key without spending a model call. It is not reachable from
`rota/`, and the held-out set's disjoint phrasing is exactly why the answering
pipeline does not work that way.
