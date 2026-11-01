# Ask the map

**Date:** 2026-10-28
**Feature:** Map question answering

Responders can ask one semantic-map snapshot a question, by text or
by a WAV recording, and get a JSON answer that cites object ids and
lat/lon. The same client writes a Markdown situation report. A local
`POST /ask` serves the web viewer. The model is Meta Model API
`muse-wonder-1.0`; a `wonder-full` model is refused. Commands and
the HTTP contract are in `docs/mapqa.md`.

`surmap.mapqa.answer(question, snapshot_path=...)` is the function
the mission-demo viewer imports. It returns highlight points as
map-frame `x`, `y`, `z`. It calls Meta only when `SURMAP_LIVE_META=1`;
otherwise `MapQa.ask` reads a deterministic label-match fixture.

Verification: `uv run pytest -q` — 497 passed, 6 skipped. Ruff and
mypy (strict) clean. The live Meta call stays skipped unless
`SURMAP_LIVE_META=1`.
