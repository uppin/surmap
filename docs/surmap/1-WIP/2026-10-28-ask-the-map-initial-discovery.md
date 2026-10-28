# Initial discovery — Ask the map

## Conclusions

- `main` has no `src/surmap/mapqa/`, no `src/surmap/map/snapshot.py`, and no `src/surmap/usage.py`.
- PR #35 (`cursor/gps-anchored-map-snapshot-7f14`, open) defines `surmap.semantic_map_snapshot.v1` in `docs/semantic-map-snapshot.md` on that branch. This change reads that JSON with a local loader and does not depend on the PR.
- PR #31 (`cursor/baseten-muse-labels-1ad3`, open) defines `UsageLedger` / `UsageRecord` in `src/surmap/usage.py`. This change calls that module only when it imports. Otherwise `before_call` and `on_usage` are the only usage seam.
- Meta Model API: `POST https://api.meta.ai/v1/responses` with `Authorization: Bearer $MODEL_API_KEY`. Reply text is `output[]` items of type `message`, content blocks of type `output_text`. Usage is `usage.input_tokens`, `usage.output_tokens`, and `usage.output_tokens_details.reasoning_tokens`. Reasoning effort on this protocol is `reasoning.effort`. `max_output_tokens` counts reasoning plus visible text.
- Muse Wonder Full is not on the Model API. Any model id that normalizes to contain `wonder-full` is refused before a request.
- Speech: `muse-voice-transcribe-1.0` is `POST https://api.meta.ai/v1/asr/transcribe` (multipart `request` JSON plus `audio` WAV). The buffered JSON body has `transcript`.
- The demo server already uses the stdlib HTTP server. Ask the map does the same, so the viewer contract adds no dependency.
- `README.md`, `HACKATHON.md`, and `docs/architecture.md` stay unchanged. The feature doc is `docs/mapqa.md`.
- Scanned `src/surmap/docs/todo/` (six moving-object records) and found no `src/surmap/docs/code-issues/`. None of those records are on this path.

## Explore

Package layout is `src/surmap/<area>/`. Entrypoints use `python -m` (`surmap.survey.station_main`). Tests are pytest under `tests/`, mypy strict, Ruff `E,F,I,UP,B`, line length 100. JSON at the boundary is narrowed from `object` after `json.loads`, matching `src/surmap/usage.py` on PR #31.
