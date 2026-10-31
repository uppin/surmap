# Changeset: Demo SAM prompt on the page, with a per-scene default

**Date**: 2026-10-31
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 2 — optional prompt on two SAM ports, one `DatasetSpec` field, a form on the page; `demo`, `survey`, `scripts`

## Workflow

- [wf 1] ✅ 2026-10-31 `/plan-red` Plan — changeset, initial discovery · this file + discovery companion
  - [x] Record initial discovery
  - [x] Cross-check `src/surmap/docs/todo/` and `code-issues/` (oversized `demo/server.py`, `demo/page.py` — small additions only)
  - [x] Create changeset (no PRD: a demo control, no product surface)
- [wf 2] ✅ 2026-10-31 `/plan-red` Red — acceptance and failing lower-tier tests · 14 red (missing `sam_prompt` / `prompt=` kwargs, no prompt box), 689 existing green
  - [x] Acceptance tests (page + stream) written and failing for the right reason
  - [x] Port/adapter tests written and failing
- [wf 3] ✅ 2026-10-31 `/green` Green — implement until every red test passes · 703 passed / 3 skipped; ruff, format, mypy strict green; fake-SAM smoke on KITTI
  - [x] Ports: `VideoSamDetector.reset(prompt=None)`, `VideoSamStreamer.stream(frame_paths, prompt=None)`; in-memory adapters record the prompt
  - [x] `Sam31VideoStreamer.stream(..., prompt=)` prompts and labels with it; ONNX `Sam3VideoDetector.reset(prompt=)` rejects a concept other than its export's
  - [x] `CentredBoxVideoSamDetector.reset(prompt=)` relabels
  - [x] `DatasetSpec.sam_prompt` (EuRoC `box`, KITTI `car`, NTU `person`)
  - [x] `DemoPlayer(sam_prompt=)`; server resolves `?prompt=` → launcher override → scene default; fixed for an ONNX export
  - [x] Page: SAM prompt form in the SAM pane (`/?dataset=…&prompt=…`), read-only when fixed; stream opened with the prompt; run title carries it
  - [x] Launcher: `--sam-label` defaults to the scene's prompt
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs, then open the PR ready ·
  - [ ] Verification executed — result recorded
  - [ ] `README.md` §Demo — the prompt box and per-scene defaults
  - [ ] Changelog entry `docs/surmap/changelog/2026-10-31-demo-sam-prompt.md`
  - [ ] Changeset and discovery companion deleted from `1-WIP/`

## Initial Discovery

[initial-discovery.md](./2026-10-31-demo-sam-prompt-initial-discovery.md).

## Summary

The SAM concept prompt was fixed for the server's lifetime by `--sam-label`
(default `object`), so KITTI showed cars only because the run was started with
`car`. The page gains a prompt box in the SAM pane; applying it restarts the
stream with that prompt. Each scene carries its own default prompt.

## Technical Changes

### State A (Current)

- One prompt, baked into the SAM adapter in `make_demo_server`; the ports take no prompt.
- `--sam-label` defaults to `object` for every scene.
- The page has no prompt control.

### State B (Target)

- `VideoSamDetector.reset(prompt: str | None = None)` and
  `VideoSamStreamer.stream(frame_paths, prompt: str | None = None)`: `None`
  keeps the adapter's configured prompt. The ONNX adapter's concept is fixed
  at export, so it raises on a different prompt.
- `DatasetSpec.sam_prompt` gives each scene its default.
- A run's prompt is resolved per stream: `/stream?prompt=` (non-blank,
  ≤ 100 chars) → launcher `--sam-label` → the scene's default. With an ONNX
  export the export's label is used and the page box is read-only.
- The page's SAM pane has a GET form (`dataset`, `prompt`) → `/?dataset=…&prompt=…`;
  the stream URL carries the box's value; Restart keeps it; switching
  scene drops it (the new scene's default applies). The persisted run's
  title names the prompt.

### Delta

Prompt moves from construction time to playback time. A live change
mid-run is out of scope: SAM 3.1 prompts per 16-frame window ahead of
playback, so a restart keeps every result attributable to one prompt.

## Verification

- `uv run pytest -q` green with the new tests; ruff, format, mypy strict green.
- Manual: `scripts/demo.py --sam-fake --dataset kitti-2011-09-26-drive-0009`
  → SAM pane shows `car`; apply `person` → the stream restarts and the
  SAM labels read `person`.
