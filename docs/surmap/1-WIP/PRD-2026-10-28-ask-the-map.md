# Ask the map — PRD

**Date**: 2026-10-28
**PRD Type**: Enhancement

## Affected Features

- **Primary Feature**: Ask the map (`docs/mapqa.md`, written at wrap) — responders question a semantic-map snapshot and receive cited answers.
- **Related**: semantic map snapshot schema on PR #35. This feature reads the file. It does not write one and does not change that schema.

## Summary

A responder can ask a question of one GPS-anchored semantic map, including by voice, and get a strict JSON answer that cites object ids and lat/lon. The same client can write a Markdown situation report. A small HTTP `POST /ask` serves the web viewer.

## Background

SurMap maps a civilian disaster scene. Responders need to ask the map where people and blockages are without a second coordinate format. The model is Meta Model API, Muse Wonder (`muse-wonder-1.0`), not Muse Wonder Full.

## Proposed Changes

### What's Changing

- `ask(question)` returns `{answer, landmark_ids, highlight_points}` and rejects ids that are not on the map.
- `report()` returns a Markdown situation report.
- `ask_voice(audio_path)` transcribes with `muse-voice-transcribe-1.0`, then asks.
- CLI: `python -m surmap.mapqa ask|report|ask-voice`, plus `serve` for `POST /ask`.
- A civilian demo snapshot: collapsed building, person on a roof, blocked road, vehicle.

### What's Staying the Same

- Passive survey only. No flight control, navigation, or mission orchestration.
- `README.md`, `HACKATHON.md`, and `docs/architecture.md` are not edited.
- No API key is committed. Live calls require `SURMAP_LIVE_META=1`.

## Impact Analysis

### Technical Impact

- New package `src/surmap/mapqa/`. Stdlib HTTP and urllib only.
- Optional import of `surmap.usage` when that module exists.

## Acceptance Criteria

- A fake transport proves the request shape, the wonder-full refusal, the one retry, citation checks, voice-then-ask, the CLI printout, and `POST /ask`.
- The demo snapshot is humanitarian.
- Ruff, mypy, and pytest are green. The live test stays skipped unless `SURMAP_LIVE_META=1`.
