# Recorded live runs

`scripts/mission_demo.py` replays `demo/recordings/mission/` by default
when it exists, so the offline demo shows real model responses without
an API key. Without it, the demo falls back to fixtures.

Record one from a machine that has the keys:

```bash
source ~/.surmap-keys            # exports MODEL_API_KEY (and BASETEN_API_KEY)
export SURMAP_LIVE_META=1        # add SURMAP_LIVE_BASETEN=1 for open-weight labels
uv run python scripts/mission_demo.py --live --capture ~/sitl-runs/disaster-01 \
    --record demo/recordings/mission --no-viewer
```

What is written:

| File | Contents |
|---|---|
| `manifest.json` | `surmap.model_recording.v1`, UTC time of the first call, capture name, services, models, call count |
| `calls.jsonl` | One line per model call: role, provider, model, URL, request body, full response, UTC time, elapsed seconds |
| `semantic_map_snapshot.json` | The snapshot the live run wrote |
| `impact.json` | The live run's report, without the local EuRoC path |

Auth headers are never recorded. Images in request bodies are replaced
by their size and SHA-256 prefix. Values of `MODEL_API_KEY`,
`BASETEN_API_KEY`, `MODAL_PROXY_TOKEN_ID`, `MODAL_PROXY_TOKEN_SECRET`,
and `HF_TOKEN`, and the Modal endpoint URLs, are scrubbed from every
file. Read `calls.jsonl` before committing anyway.

Replay feeds each recorded response back through the client that made
it (`surmap.mission.demo.replay_model_calls`) and labels it in the
report and viewer as "recorded live response from `<model>` at
`<UTC time>`". `--fixtures` ignores the recording.
