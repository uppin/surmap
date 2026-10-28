# Changeset: Baseten Muse Spark Open labels

**Date**: 2026-10-28
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 3 — one package, HTTP adapter seam, unit tests on a fake transport

## Workflow

- [wf 1] ✅ 2026-10-28 `/plan-red` Plan — PRD, changeset, initial discovery · PRD + this file
- [wf 2] ✅ 2026-10-28 `/plan-red` Red — acceptance and failing lower-tier tests, committed · collection error `ModuleNotFoundError: surmap.labelling` before the adapter existed
- [wf 3] ⬜ `/green` Green — implement until every red test passes ·
  - [ ] `LabelClient`, `ObjectLabel`, and `InMemoryLabelClient`
  - [ ] `BasetenMuseLabelClient` posts the crop and parses `message.content`
  - [ ] Missing `BASETEN_API_KEY` raises before any socket
  - [ ] `reasoning_effort` is `low`; `reasoning_content` is not the label; no JSON mode
  - [ ] Live test skipped unless `SURMAP_LIVE_BASETEN=1` and the key are set
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded
  - [ ] `HACKATHON.md` Baseten row — planned → client in tree; live call gated
  - [ ] `README.md` Muse Spark Open note names the client and the verified call
  - [ ] `docs/surmap/changelog/2026-10-28-baseten-muse-labels.md`
  - [ ] `src/surmap/docs/changesets/2026-10-28-baseten-muse-labels.md`
  - [ ] Delete this changeset, the PRD, and the discovery companion

## Initial Discovery

Full codebase exploration that grounded this plan: [2026-10-28-baseten-muse-labels-initial-discovery.md](./2026-10-28-baseten-muse-labels-initial-discovery.md).

State A below is distilled from that file. Do not duplicate grep traces or file dumps here.

## Affected Packages

- **surmap**: [README.md](../../../README.md) — Muse Spark Open client note
  - [HACKATHON.md](../../../HACKATHON.md) — Baseten credit status
  - [docs/architecture.md](../../architecture.md) — §3.2 left unchanged (PR #18 edits it)

## Related Feature Documentation

- [PRD](./PRD-2026-10-28-baseten-muse-labels.md)

## Summary

Add a labelling port and a Baseten Muse Spark Open client that turns
one JPEG crop into an `ObjectLabel`, with the live call gated and the
survey loop unwired.

## Background

Follow-up task 1 on PR #28. The owner verified on 28 Oct 2026 that
`POST https://inference.baseten.co/v1/chat/completions` with
`meta-models/muse-spark-open-1026` returns an OpenAI chat completion.
`choices[0].message.content` is the answer. `reasoning_content` held
about 2,200 reasoning tokens on a trivial prompt, so the client sets
`reasoning_effort` to `low` and never treats the trace as the label.
The key is `BASETEN_API_KEY`. The repo is public.

## Scope

- **Implementation**: `LabelClient`, `ObjectLabel`, `InMemoryLabelClient`, `BasetenMuseLabelClient`
- **Testing**: fake-transport acceptance test, parse rules, missing-key guard, gated live test
- **Package documentation**: `HACKATHON.md` Baseten row and the README Muse note
- **Out of scope**: wiring the client into the survey loop, scene-note Muse Spark, Meta Model API, Modal, `docs/architecture.md` §3.2

## Technical Changes

### State A (Current)

No `surmap.labelling` package. `HACKATHON.md` lists Baseten as planned
and says nothing in `src/` calls it. README says to confirm the dated
model id before a live call. Architecture §3.2 still says the newest
Meta Llama model.

### State B (Target)

`BasetenMuseLabelClient.label_object(crop_jpeg, coarse_label, map_xyz)`
returns an `ObjectLabel`. The request goes to
`https://inference.baseten.co/v1/chat/completions` with model
`meta-models/muse-spark-open-1026`, `reasoning_effort: low`, and the
crop as a JPEG `image_url` data URL. The prompt is a civilian
disaster-response labelling request and does not ask for flight or
mission actions. The label is parsed from assistant `content` (`label:`
line, else the first non-empty line). `confidence` is `None` when that
text has no number; a `confidence:` number wins over an earlier number.
`reasoning_content` is ignored. A missing or blank key raises
`BasetenApiKeyMissing` before a socket, and error text redacts the key.
`InMemoryLabelClient` satisfies the same port without HTTP.
`HACKATHON.md` Baseten status is "client in tree; live call gated".

### Delta (What's Changing)

#### surmap

- **Architecture**: new labelling hexagon beside detection and SLAM. The survey loop does not gain a call.
- **API**: `LabelClient.label_object` → `ObjectLabel`.
- **Implementation**: stdlib `urllib` behind an injected `HttpTransport`. No new dependency.
- **Dependencies**: none added.

## Verification

**Method:** V1-fail→pass — acceptance tests for the new label client
**Command:** `uv run pytest -q tests/test_labelling_baseten_muse.py`
**Before:** collection error `ModuleNotFoundError: No module named 'surmap.labelling'` (the tests imported a package that did not exist; no assertion ran, and `urlopen` was not called).
**After:** the file reports 12 passed and 1 skipped. The skip is `test_live_baseten_labels_a_jpeg_crop` unless `SURMAP_LIVE_BASETEN=1` and `BASETEN_API_KEY` are both set. Full gates: `uv run ruff check src tests`, `uv run ruff format --check src tests`, `uv run mypy`, `uv run pytest -q`.

## Testing Plan

Fake `HttpTransport` records the POST. Tests assert model id, host
`inference.baseten.co`, a JPEG `image_url` part, and the parsed label.
A patched `urlopen` fails the test if the client opens a socket.
The live test is collected and skipped by default.

## Acceptance Tests

### surmap

- `test_fake_transport_labels_a_crop_via_baseten`
- `test_request_asks_for_low_reasoning_and_plain_text`
- `test_reply_without_a_label_prefix_uses_the_first_line`
- `test_a_stated_confidence_is_parsed_from_the_reply`
- `test_a_number_in_the_reply_is_the_confidence_when_none_is_named`
- `test_prompt_frames_a_civilian_disaster_response`
- `test_missing_api_key_raises_before_any_socket`
- `test_blank_api_key_raises_before_the_transport_is_used`
- `test_http_error_does_not_include_the_api_key`
- `test_empty_assistant_content_is_not_read_from_reasoning`
- `test_empty_crop_is_refused_before_the_transport_is_used`
- `test_in_memory_client_returns_the_label_it_was_given`
- `test_live_baseten_labels_a_jpeg_crop` (skipped unless the live env is set)

## Decisions & Trade-offs

- Stdlib `urllib` instead of a new HTTP library. A new dependency is reserved for the developer, and the repo already uses urllib.
- Protocol and in-memory client live next to the Baseten adapter (`base.py`, `memory.py`, `baseten_muse.py`) following the SLAM hexagon. The task named `baseten_muse.py`; the port is still that package.
- `reasoning_effort` is always `low`. The client has no switch that claims reasoning is off (`none`, `minimal`, or `enable_thinking`).
- Confidence prefers a `confidence:` number, otherwise the first number in the assistant text, otherwise `None`.
- `docs/architecture.md` §3.2 stays as written. PR #18 already edits it, and PR #28 left it alone for that reason.
- The branch is cut from `cursor/readme-meta-models-24f9` because PR #28 is open and `HACKATHON.md` is not on `main`.
