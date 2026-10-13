# Recorded extractions

Three runs of the extraction step, saved so that every measurement the writeup
cites is reproducible from a clean checkout without spending a model call.

| file | what it is |
|---|---|
| `extraction_1x.json` | one full pass over all 60 items |
| `extraction_3pass.json` | three independent passes per item |
| `extraction_5pass.json` | five independent passes per item |

Each entry is `{"item": id, "reply": text}` — the model's raw reply, with the
prompt stripped out, since that is all the replay scripts read. Stripping takes
the three files from 3.8 MB to 534 KB.

They exist because the expensive and noisy half of this system is the model and
the cheap, deterministic half is everything after it. Replaying a *fixed*
extraction makes a comparison exact: two variants of the symbolic layer see
literally the same model output, with none of the sampling noise a fresh run at
`temperature=1.0` would add — and that noise (SD 0.034–0.043) is larger than
several of the effects being measured.

```bash
python3 dev/replay.py fixtures/extraction_1x.json fixtures/extraction_3pass.json
python3 dev/check_error_structure.py fixtures/extraction_5pass.json
python3 dev/check_model_sensitivity.py fixtures/extraction_1x.json
python3 dev/tune_aggregation.py fixtures/extraction_3pass.json
python3 dev/calibrate.py fixtures/extraction_1x.json
```

Regenerate one with `./run items.json --budget 1x --out /tmp/a.json
--calls-log /tmp/log.json` (that log keeps the prompts; strip to `item`/`reply`
to match these).
