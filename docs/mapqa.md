# Ask the map

Status: responders can question one semantic-map snapshot. The answer
cites object ids and lat/lon. A situation report is Markdown. A local
`POST /ask` serves the web viewer.

The snapshot file is UTF-8 JSON, schema
`surmap.semantic_map_snapshot.v1`. This package reads that file. It
does not write one. `landmarks` and `dynamic` share one object shape:
`id`, `xyz` (x east, y north, z up), `lat`, `lon`, `alt`, `label`,
`description`, `model_id`, `motion`, `t_ns`, `anchor_t_ns`,
`offset_ns`, `observations`, `mask_points`. `origin` is the earliest
GPS fix or `null`.

The model is Meta Model API. Text goes to
`POST https://api.meta.ai/v1/responses`. A WAV question goes to
`POST https://api.meta.ai/v1/asr/transcribe` and the transcript is
then asked. Auth is `Authorization: Bearer $MODEL_API_KEY`. Reply
text is `output[]` message content of type `output_text`. Token
counts are `usage.input_tokens`, `usage.output_tokens`, and
`usage.output_tokens_details.reasoning_tokens`.

## What it will not call

`muse-wonder-1.0` is the default (`SURMAP_MAPQA_MODEL` overrides it).
Any model whose name contains `wonder-full` — including
`muse-wonder-full` and `Muse Wonder Full` — is refused before a
request. Muse Wonder Full is not served on this API.

Reasoning effort is `high`. `max_output_tokens` is at least 8192,
because that budget covers reasoning tokens and the visible answer.
A reply with no text is sent once more, then fails.

Voice transcription uses `muse-voice-transcribe-1.0`. The file must
be a RIFF/WAVE clip: mono, 16-bit PCM, 16 kHz or 24 kHz.

## WSL

Run these from the repo root in WSL. `uv run python` uses the
project environment. Put the key in the shell with single quotes.
Do not commit it, and do not write it into a file in this repo.

```bash
cd ~/surmap
export MODEL_API_KEY='your-key'

uv run python -m surmap.mapqa ask \
  --snapshot examples/mapqa-disaster-snapshot.json \
  --question "Where is the person who needs rescue?"

uv run python -m surmap.mapqa report \
  --snapshot examples/mapqa-disaster-snapshot.json

uv run python -m surmap.mapqa ask-voice \
  --snapshot examples/mapqa-disaster-snapshot.json \
  --audio question.wav

uv run python -m surmap.mapqa serve \
  --snapshot examples/mapqa-disaster-snapshot.json \
  --host 127.0.0.1 \
  --port 8765
```

`ask` and `ask-voice` print one JSON object. `report` prints
Markdown. `serve` listens until interrupted.

A live call from the test suite prints the same JSON. It stays
skipped unless you opt in:

```bash
SURMAP_LIVE_META=1 uv run python -m pytest -q tests/test_mapqa_http.py -k live -s
```

## POST /ask

The viewer posts JSON and reads JSON. `snapshot_path` is optional.
When it is omitted, the server uses the snapshot it was started
with. When it is set, it is a local filesystem path.

```bash
curl -s -X POST http://127.0.0.1:8765/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"Where is the person who needs rescue?"}'
```

`200` body:

```json
{
  "answer": "A person is on the roof of the collapsed building.",
  "landmark_ids": ["3"],
  "highlight_points": [{"lat": 37.0002173913, "lon": -121.9997930354}]
}
```

`landmark_ids` are ids from `landmarks` or `dynamic`. An id that is
not on the map is rejected. A cited object that has a lat/lon must
come with at least one highlight point. Highlight `lat` is -90..90
and `lon` is -180..180.

Errors are `{"error": "..."}`. `400` means the question or the model
name was refused. `404` means `snapshot_path` is not a file. `502`
means the model reply was empty or not the contract.

Responses include `Access-Control-Allow-Origin: *` so a viewer on
another local origin can read them. `OPTIONS /ask` answers the
preflight.

## Hooks

`MapQa` takes `before_call(model, payload)` and `on_usage(usage)`.
`before_call` runs before each attempt, including the one retry.
`on_usage` receives `ModelUsage(model, input_tokens, output_tokens,
reasoning_tokens)` after each responses call.

If `surmap.usage` imports, the same calls also go through
`UsageLedger` as provider `meta` (`check` before the request,
`UsageRecord` after). If that module is not installed, only the
hooks run.

## Demo snapshot

`examples/mapqa-disaster-snapshot.json` is a civilian rescue scene:
a collapsed apartment building, a person on the remaining roof, a
road blocked by rubble, and a civilian van. It is not a military
scene.
