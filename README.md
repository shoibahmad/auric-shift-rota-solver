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

See [WRITEUP.md](WRITEUP.md) for how the model was characterised, why each
component exists, what was removed, and where the system breaks.

## Running it

Python **3.13** (developed on 3.13.7; needs 3.9+).

```bash
pip install -r requirements.txt           # openai==2.35.1, nothing else
cp .env.example .env                      # then put the endpoint key in it
./run items.json --budget 1x  --out answers.json
./run items.json --budget 3x  --out answers_3x.json
./run items.json --budget 10x --out answers_10x.json
```

`run` is a shell launcher over `python3 -m rota.main`; `run.cmd` is the same for
Windows. Set `PYTHON=python3.13` to pick an interpreter.

Scoring, with the provided scorer:

```bash
python3 score.py visible_key.json answers.json
```

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
python3 ablate.py --items items.json --key visible_key.json \
    --budgets 1x,3x,10x --runs 3 --outdir runs/ablation
```

This writes `runs/ablation/ablation.md` and, for every cell of the table, the
`answers.json`, `score.json` and per-item trace that produced it. Results are
in [ABLATION.md](ABLATION.md).

Individual arms can be run by hand:

```bash
./run items.json --budget 3x --out /tmp/a.json --components -repair
./run items.json --budget 1x --out /tmp/b.json --components -solver
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
| [dev/](dev/) | characterisation probes and measurements; not part of the pipeline |

`dev/` is kept because the writeup's claims come from it, and each script
reproduces one measurement. `dev/refparse.py` is a regex reference parser over
the *visible* phrasing pool, used to pin down the generator's semantics and to
test the solver against the key without spending a model call. It is not
reachable from `rota/`.
