# Disaster labelling eval (LADI v2)

`scripts/eval_disaster_labelling.py` scores the Muse label clients on
[LADI v2](https://huggingface.co/datasets/MITLL/LADI-v2-dataset)
(MIT Lincoln Laboratory, CC BY 4.0): Civil Air Patrol aerial photos from
US disasters with twelve boolean classes: `bridges_any`, `buildings_any`,
`buildings_affected_or_greater`, `buildings_minor_or_greater`,
`debris_any`, `flooding_any`, `flooding_structures`, `roads_any`,
`roads_damage`, `trees_any`, `trees_damage`, `water_any`.

The code is in `src/surmap/evaluation/` and the offline tests are in
`tests/test_evaluation_ladi.py`.

## Data

Images come from the Hugging Face dataset viewer rows API (config
`default`, split `test` by default). Each image is re-encoded as a JPEG
at most 1024 px on its longest side. That drops the EXIF block and its
GPS tags. Images and labels are cached in `~/.cache/surmap/ladi-v2/<split>/`
(`SURMAP_LADI_CACHE` overrides this). Nothing is committed or re-hosted.

```bash
uv run python scripts/eval_disaster_labelling.py --download-only --limit 10
```

## Models

| Provider | Model | Output |
|---|---|---|
| `meta` | `muse-wonder-1.0` on the Meta Model API (`SURMAP_META_MODEL` overrides) | Responses API `text.format` JSON schema (strict), one boolean per class, `reasoning.effort` `low` |
| `baseten` | `meta-models/muse-spark-open-1026` on Baseten | `record_classes` tool call with `tool_choice` `auto` and `reasoning_effort` `low`. JSON in the reply text is the fallback, because Baseten has no JSON mode for this model |

## Gates and budget

- A model call needs `SURMAP_LIVE_META=1` with `MODEL_API_KEY`, or
  `SURMAP_LIVE_BASETEN=1` with `BASETEN_API_KEY`. The script stops before
  downloading anything when a flag or key is missing.
- `--limit` may not exceed `SURMAP_EVAL_MAX_IMAGES` (default 20). The
  default limit is 10.
- `SURMAP_BUDGET_META_CALLS` / `SURMAP_BUDGET_BASETEN_CALLS` (and
  `_TOKENS`) stop the run mid-way, as for every other client. Usage goes to
  the shared ledger (`scripts/usage_report.py`).
- A failed call is reported on stderr. It is counted as a failure and is
  not scored as "no classes".

```bash
source ~/.surmap-keys
SURMAP_LIVE_META=1 SURMAP_LIVE_BASETEN=1 \
  uv run python scripts/eval_disaster_labelling.py --provider both --limit 10 \
  --out ~/surmap-eval/ladi-test-10.json
```

## Output

A table per provider gives support, precision, recall, and F1 for each
class, then macro F1 (over classes with support) and micro F1. `--out`
writes the same numbers as JSON with the per-image truth and predictions.
Ten images are a smoke test, not a benchmark. Do not quote them as model
accuracy.

## Reasoning effort

Both providers run at `low` reasoning effort by default. `--reasoning-effort medium` or `high` applies to both; at `medium` or `high` the Baseten budget starts at 8192 tokens. The effort is written into each report.

    SURMAP_EVAL_MAX_IMAGES=100 SURMAP_LIVE_META=1 \
        uv run python scripts/eval_disaster_labelling.py --provider meta --limit 100 \
        --reasoning-effort high --out ~/surmap-eval/wonder-high.json

## SAM 3.1 on Modal

`--provider modal` scores SAM 3.1 on the self-deployed Modal endpoint. Each image is sent once per class prompt (`building`, `damaged building`, `debris`, `flooded area`, `bridge`, `road`, `tree`, `fallen tree`, `water`), so 100 images is 900 SAM calls. A class counts as predicted when SAM returns a detection scoring 0.5 or more. Only those nine classes are scored.

    source ~/.surmap-keys
    SURMAP_EVAL_MAX_IMAGES=300 SURMAP_LIVE_MODAL=1 \
        uv run python scripts/eval_disaster_labelling.py --provider modal --limit 300 \
        --out ~/surmap-eval/modal-sam-300.json
