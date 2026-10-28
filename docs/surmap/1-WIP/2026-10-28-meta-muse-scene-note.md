# Changeset: Meta Model API scene note

**Date**: 2026-10-28
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 3 — one package, HTTP adapter seam, unit tests plus a loopback transport test

## Workflow

- [wf 1] ✅ 2026-10-28 `/plan-red` Plan — PRD, changeset, initial discovery · PRD + this file
- [wf 2] ✅ 2026-10-28 `/plan-red` Red — acceptance and failing lower-tier tests, committed · collection error, `surmap.labelling` missing
- [wf 3] ✅ 2026-10-28 `/green` Green — implement until every red test passes · 18 passed, 1 skipped (`SURMAP_LIVE_META` unset)
  - [x] `MetaMuseSceneClient.note` posts hosted `muse-spark-1.3` and returns message `output_text`
  - [x] JPEG goes out as an `input_image` data URL; `reasoning.effort` defaults to `low`
  - [x] Muse Wonder and Muse Spark Open ids are refused; the API key is not logged
  - [x] Live call is skipped unless `SURMAP_LIVE_META=1`
  - [x] HACKATHON.md Meta Model API scene-note cell names the client
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded
  - [ ] HACKATHON.md and README.md state the scene-note client
  - [ ] `docs/surmap/changelog/2026-10-28-meta-muse-scene-note.md` written
  - [ ] Changeset, PRD, and discovery companion deleted from `1-WIP/`

## Initial Discovery

Full codebase exploration that grounded this plan: [initial-discovery.md](./2026-10-28-meta-muse-scene-note-initial-discovery.md).

State A below is distilled from that file. Do not duplicate grep traces or file dumps here.

## Background

PR #28 records three hackathon credit sources and calls none of them. Follow-up
task 2 is the Meta Model API scene note: one civilian search-and-rescue
description of a mapped frame, from hosted Muse Spark, with no flight advice.

## State A

- No `src/surmap/labelling/` package.
- `HACKATHON.md` status for the Meta Model API row is "Planned". The credits
  intro says none of the three sources is called from `src/`.
- README names `muse-spark-1.3` as the scene-note id and does not name a client.
- The owner's 2026-10-28 call showed `POST /v1/responses`, a reasoning item
  then a message item, and a default reasoning effort of `high`.

## State B

- `MetaMuseSceneClient` in `surmap.labelling.meta_muse` posts
  `https://api.meta.ai/v1/responses` with model `muse-spark-1.3`,
  `reasoning.effort` `low`, and the JPEG as `input_image`.
- `note` returns only `output_text` from `message` output items.
- Wonder and `meta-models/muse-spark-open-1026` are refused.
- `MODEL_API_KEY` is read at call time and does not appear in errors or `repr`.
- A live test runs only when `SURMAP_LIVE_META=1`.
- The HACKATHON.md scene-note cell and the README scene-note line describe that client.

## Delta

- Add the labelling package, the client, the stdlib transport, and tests.
- Edit the credits wording that would otherwise still say the scene note is uncalled.

## Verification

- `uv run ruff check src tests` — pass
- `uv run ruff format --check src tests` — pass
- `uv run mypy` — pass (strict)
- `uv run pytest -q` — 486 passed, 6 skipped
- The live test stays skipped unless `SURMAP_LIVE_META=1` (not set for this run).

## Decisions & Trade-offs

- Branch parent is `cursor/readme-meta-models-24f9` because PR #28 is not merged
  and `HACKATHON.md` is not on `main`.
- Stdlib `http.client` instead of a new HTTP library. Redirects are not followed,
  so the bearer token stays on the one request.
- `docs/architecture.md` §3.2 is left unchanged; PR #18 already edits it, and
  this client is the scene note, not the per-landmark label record.
