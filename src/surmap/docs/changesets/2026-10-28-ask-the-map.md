# Ask the map

**Date:** 2026-10-28
**Type:** Feature
**Packages:** surmap

Added `surmap.mapqa`. `MapQa.ask` posts to the Meta responses API
and returns `{answer, landmark_ids, highlight_points}` after checking
every id against the snapshot. `report` returns Markdown.
`ask_voice` transcribes with `muse-voice-transcribe-1.0`, then asks.
`python -m surmap.mapqa` exposes `ask`, `report`, `ask-voice`, and
`serve` (`POST /ask`).

The snapshot loader reads `surmap.semantic_map_snapshot.v1` JSON.
`before_call` and `on_usage` always run. `UsageLedger` is used only
when `surmap.usage` imports. The demo file is
`examples/mapqa-disaster-snapshot.json`.

Verification: 494 passed, 6 skipped. The new tests are
`tests/test_mapqa_snapshot.py`, `tests/test_mapqa_ask.py`,
`tests/test_mapqa_voice.py`, `tests/test_mapqa_cli.py`, and
`tests/test_mapqa_http.py`.
