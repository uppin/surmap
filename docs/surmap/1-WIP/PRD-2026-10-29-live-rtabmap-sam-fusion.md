# Live RTAB-Map + SAM fusion demo — PRD

**Date**: 2026-10-29
**PRD Type**: Enhancement
**Status**: 🚧 In Progress
**Audience**: the implementing agent. Read `AGENTS.md` first and
follow it: TDD (`tdd` skill), fluent tests (`fluent-tests` skill),
and the `pr-lifecycle` flow (changeset plus `-initial-discovery.md`
companion in this directory, `[wf]` rows, a draft PR as `uppin`, and
the wrap before ready). Suggested classification: **Feature · adds**
(preset *feature*).
**Depends on**: `PRD-2026-10-29-live-rtabmap-streaming.md` (this
directory), which provides `StreamingRtabmapBackend`, live poses,
keyframe updates and graph updates. Build this as the **next node of
a stack** on that PR's branch, or start after it merges. Do not
reimplement any of it here.

## Affected Features

- **Primary**: Browser demo — `src/surmap/demo/server.py` and
  `scripts/demo.py`, documented in `README.md` § *Demo*.
- **Primary**: Station SAM adapter — `src/surmap/survey/sam3.py` and
  `src/surmap/survey/sam.py`. The adapter is reused as is. Only the
  model-provisioning tooling is new.
- **Secondary**: Stereo reconstruction — `src/surmap/survey/stereo.py`.
  Points need their source pixel (`architecture.md` §6
  `PointCloud`: *"The point ↔ pixel link is mandatory"*).
- **Secondary**: `README.md` (*Station SAM note*) and
  `docs/architecture.md` §5 / §6. The demo becomes a local stand-in
  for the `surmap_fuse` step.
- **Not affected**: the CM5 server, the station RPC server and the
  wire protocol (`proto/`).

## Summary

One demo page where RTAB-Map and SAM work **together, live**:

- RTAB-Map builds the map in real time, as delivered by the
  dependency PRD.
- SAM segments the left frames as they play. Each mask claims the
  stereo points under it.
- RTAB-Map's pose for that frame places those points in the map
  frame.
- The map panel shows a **semantic object layer**, coloured by
  label, on top of RTAB-Map's grey static cloud and the trajectory.
  Both layers grow during playback.

This is the `fuse` step of `docs/architecture.md` §5 (*masks × cloud
× RTAB-Map pose*), run locally in the demo process.

## Background

Today the pieces exist but have never met:

- `Sam3Detector` (`src/surmap/survey/sam3.py`) runs any ONNX model
  that honours the contract: `image` float32 `[1,3,H,W]` in, `masks`
  `[1,N,H,W]` and `scores` `[1,N]` out. It returns `SamDetection`s
  with a box and a mask polygon in frame pixels. Only a **fake**
  model exists (`tests/fixtures/sam3_fake/fake_sam3.onnx`, which
  segments brighter-than-grey regions).
- The real SAM 3.1 checkpoint (`facebook/sam3.1` on Hugging Face) is
  license-gated. Exporting it to the ONNX contract above is described
  as a station provisioning step, but no tooling for it exists.
- The demo shows stereo points, Coral boxes and (after the
  dependency PRD) a live RTAB-Map map. It has no segmentation.
- `StereoReconstructor.reconstruct` returns camera-frame `Vec3`s
  without their source pixel. The demo re-projects them
  (`project_overlay`), which is lossy for mask membership.

Development host: an Apple Silicon Mac with no CUDA. SAM will run on
ONNX Runtime's CPU provider here (CoreML is optional, see M0). Expect
seconds per frame for the real model. SAM therefore runs **off the
playback loop, best effort**, through the existing `AnalysisGate`
(`AnalysisMode.BEST_EFFORT_DROP`). Playback never waits for SAM, the
same way it never waits for RTAB-Map.

## Proposed Changes

### What's Changing

**1. Real SAM 3.1 provisioning — `scripts/export_sam3_onnx.py`**

- Downloads `facebook/sam3.1`. This requires the user to have
  accepted the license on Hugging Face and logged in with
  `huggingface-cli login`. The script fails with that instruction
  when it cannot authenticate.
- Exports to the **existing** ONNX contract in `sam3.py`'s module
  docs. SAM 3 is promptable by concept (noun phrase). The contract
  has no prompt input, so phase 1 **bakes a concept prompt list into
  the export** (`--concepts "car,person,chair,…"`) and writes a
  sidecar `labels.json` mapping each output mask to its concept.
  Extending the contract with a runtime text-prompt input (so Coral
  labels can steer SAM, `architecture.md` §3.1) is out of scope here.
- Output goes to `~/.cache/surmap/sam3/` (override with
  `$SURMAP_SAM3_DIR`), never into the repo. The script verifies its
  output against the contract by running one inference through
  `OnnxSam3Session`.
- Tooling dependencies (`torch`, the SAM 3 reference package, `onnx`)
  are **tooling-only**, run via `uv run --with …` as
  `scripts/make_fake_sam3_model.py` already does. They must not enter
  `pyproject.toml` runtime dependencies. Adding *any* dependency is
  an action the repo reserves for the developer. **Halt ⛔** with the
  exact list before adding one (`pr-lifecycle` § *Halts*).
- Fallback order if the SAM 3.1 export is infeasible (op support,
  size): SAM 3, then SAM 2 automatic-mask mode, per
  `architecture.md` §3.1. Record the chosen model in the changeset.
  The contract does not change.

**2. Label support in `Sam3Detector`**

- Optional `labels: Sequence[str]`. When it is given, mask *i* gets
  label `labels[i]` instead of the single `label`. Default behaviour
  is unchanged, and so are the fake model's tests.

**3. Pixel-linked stereo points**

- Add a variant of `StereoReconstructor.reconstruct` that returns
  each point with its source `(u, v)`, e.g. a frozen `PixelPoint(u,
  v, xyz)`. The existing method keeps its signature and output: it
  calls the new one and drops the pixels. Existing tests stay green
  unchanged.

**4. Fusion — `surmap.demo.fusion` (pure, fully unit tested)**

- `points_in_mask(points, mask_polygon) -> tuple[PixelPoint, ...]`
  does a point-in-polygon test on `(u, v)`. Rasterize the polygon
  once per detection, as a mask lookup, so it stays O(points).
- `place_segment(...)` takes the claimed camera-frame points and the
  frame's pose, and returns a `SegmentObservation(frame_id, t_ns,
  label, score, node_ref, points_map)`. The camera→map transform is
  `surmap.geometry.to_map_frame` (as `cm5_server.py` uses it); reuse it, do
  not copy it.
- **Re-placement on loop closure.** Each observation records which
  RTAB-Map keyframe it hangs off (the nearest keyframe at or before
  its frame) and its offset from that keyframe. When the dependency
  backend emits a `graph` update, observations are re-placed from
  their keyframe's new pose, so object points move with the static
  cloud.
- **Unposed frames are never placed.** If the frame has no pose
  (RTAB-Map lost, or the frame was dropped), its segments are kept as
  unposed and counted, never put on the map with a guessed pose
  (`architecture.md` §9).
- `SemanticLayer` accumulates observations per label, with a
  voxel-downsampled point set (bounded, like `MAX_MAP_POINTS`), and
  reports counts per label.
- **Scope guardrail (`AGENTS.md`).** The semantic layer is a
  *separate* layer on top of RTAB-Map's output. Nothing is ever fed
  back into RTAB-Map (no `process_frame` input, no point injection
  into its map). It is also kept separate from the static cloud in
  every payload. Segments overlapping a Coral track that the existing
  motion classifier marks *moving* are **excluded** from the
  accumulated layer. Send them only as per-frame overlay outlines,
  so moving objects are never fused into the static scene. Use the
  classifier as it is; do not re-tune it.

**5. Demo wiring**

- New flags on `scripts/demo.py`:
  - `--sam3-model PATH` (default `$SURMAP_SAM3_MODEL`, else
    `~/.cache/surmap/sam3/sam3.1.onnx` when present, else SAM off);
  - `--sam3-device {auto,cpu,cuda}`;
  - `--sam3-labels PATH` (default: the `labels.json` next to the
    model);
  - `--sam-stride N` (offer every Nth frame to SAM; default 1, with
    best-effort drop).
- SAM runs on a worker thread through `Sam3Detector` and
  `AnalysisGate(BEST_EFFORT_DROP)`. The player offers frames and
  never awaits a result on the pacing loop. Results come back
  tagged with `frame_id`. The frame's pose is looked up when the
  result arrives, from the dependency backend's poses. If the pose
  is not there yet, the segment is parked briefly (≤ 2 s) and then
  counted unposed.
- New SSE events:
  - `segments`: per SAM result, `frame_id`, then `label`, `score`,
    `box` and `polygon` for each detection, keyed by `frame_id` like
    `detections`;
  - the `map` event from the dependency PRD gains `semantic`: per
    label, sampled XY points and a count.
- Page:
  - mask outlines are drawn on the video, translucent and coloured
    by label, alongside the Coral boxes;
  - the map draws a semantic layer over the grey cloud, coloured by
    label, with a legend;
  - the stats panel shows the SAM provider, SAM ms per frame,
    analysed and dropped counts, and posed and unposed segments.
- **Honesty banner.** When the model is the fake fixture (path or
  manifest match), the page header shows **"FAKE SAM model — masks
  are not semantic"**. The demo may run with the fake model; it must
  never pass it off as SAM.
- `final` gains the final semantic layer, re-placed against the
  final optimized graph.

### What's Staying the Same

- The SAM ONNX contract: image in, masks and scores out.
- The station server, its RPC and `AnalysisGate`'s semantics.
- The RTAB-Map backend from the dependency PRD, used as is.
- `frame`, `detections` and `final` keep their existing fields. New
  data goes only in new fields and events.
- No runtime dependency changes, no ROS, nothing installed on the
  host beyond the user's own Hugging Face login.

## Impact Analysis

### Technical Impact

- New: the export script (tooling only), `surmap.demo.fusion`, the
  pixel-linked stereo variant, label mapping in `Sam3Detector`, and
  the demo threads, events and UI.
- **Performance risk.** Real SAM 3.1 on a Mac CPU will be slow
  (expected seconds per frame). The best-effort drop keeps playback
  and RTAB-Map live, and the semantic layer fills in at SAM's pace.
  Measure it in M0, and try ONNX Runtime's CoreML provider. If
  CoreML helps, `--sam3-device auto` may prefer it on macOS. That is
  a provider change only, with the same session code.
- Memory: the real model is several GB. Load it once per server, not
  per stream.
- Threads: the SAM worker sits beside the RTAB-Map backend's threads.
  All of them are joined on completion, disconnect and error, through
  the player's `finally`.

### User Impact

- One demo run shows video with Coral boxes and SAM masks, and a
  live map with the static cloud, the trajectory and labelled object
  points.
- One-time setup for the real model: accept the license, run
  `huggingface-cli login`, then `uv run python
  scripts/export_sam3_onnx.py`.

## Implementation Plan

Milestones map to TODOs under the changeset's Green row. M0 is a
gate: record its results in the changeset's `## Initial Discovery`.

- **M0 — Feasibility spike (gate).**
  - Export SAM 3.1, with baked concepts, to the ONNX contract.
  - Record the model size, the export blockers, and ms per frame at
    the demo's 376×240 resolution on CPU, and on CoreML if available.
  - Check mask quality on five EuRoC frames: save the overlays and
    record their paths.

  **Halt ⛔** if the export needs dependencies (list them) or fails.
  The options are: a) SAM 3 or SAM 2 per the fallback order, b) ship
  the demo wiring against the fake model first with real
  provisioning deferred (a deferral needs the developer's word), or
  c) re-plan.
- **M1 — Pixel-linked stereo** (red tests first). Each pixel maps to
  the same `xyz` the existing method returns, and the old method's
  output is unchanged.
- **M2 — Fusion core.** Unit tests:
  - mask membership;
  - the camera→map transform matches `to_map_frame`;
  - re-placement after a `graph` update moves the points by the
    keyframe's correction;
  - unposed frames are never placed;
  - moving-track overlap is excluded from the layer;
  - the layer bound and downsampling hold.
- **M3 — Label mapping** in `Sam3Detector`, tested with the fake
  model and a labels list.
- **M4 — Demo wiring**, with fake streaming RTAB-Map and SAM
  backends. Tests:
  - SAM never blocks pacing, even with a stalled SAM fake;
  - `segments` events are keyed by `frame_id`;
  - the semantic data reaches `map` events during playback;
  - `final` carries the re-placed layer;
  - the fake-model banner flag is set;
  - all workers are closed on completion, disconnect and error.
- **M5 — E2E with the fake model** (runs in normal `pytest`, no
  Docker). Drive `DemoPlayer` over the 90-pair fixture with the fake
  SAM model and an in-memory SLAM backend. Assert that labelled
  semantic points appear in the map frame.

  Real-container plus fake-SAM e2e: extend the dependency PRD's gated
  e2e. Assert that the semantic points are posed by real RTAB-Map
  poses.
- **M6 — Manual verification with the real model.** Run:

  ```bash
  uv run python scripts/demo.py --coral-model-dir tests/fixtures/coral_model \
      --sam3-model ~/.cache/surmap/sam3/sam3.1.onnx
  ```

  on full V1_01. Record in `## Verification`: SAM ms per frame,
  analysed and dropped counts, labels seen, semantic point counts,
  whether points stayed attached across a loop closure, and
  screenshot paths.
- **Wrap.** Fold State B into `README.md` (*Demo*, *Station SAM
  note*) and `docs/architecture.md` (§5 fuse prototype note, §6
  pixel link). Write a changelog entry in `docs/surmap/changelog/`.
  Delete this PRD, the changeset and the companion from `1-WIP/`,
  then ready the PR.

All four gates (`ruff format --check`, `ruff check`, strict `mypy`,
`pytest -q`) must be green before every commit and push. No new
`# noqa` or `# type: ignore`. The ONNX Runtime boundary stays behind
the typed `Sam3Session` protocol.

## Acceptance Criteria

- [ ] M0 recorded. A real SAM 3.1 (or a recorded fallback) ONNX
      export meets the contract and runs on this Mac.
- [ ] `scripts/export_sam3_onnx.py` provisions the model
      reproducibly, outside the repo, with tooling-only dependencies.
- [ ] Pixel-linked stereo points exist, and the existing
      `reconstruct` output is unchanged.
- [ ] Live fusion: during playback, SAM-labelled object points
      appear in the map frame, posed by RTAB-Map, and grow alongside
      the RTAB-Map cloud.
- [ ] Loop-closure graph updates re-place semantic points with the
      static cloud.
- [ ] Unposed segments are never placed. Moving-object segments are
      never accumulated into the layer. Nothing is written back into
      RTAB-Map.
- [ ] SAM never blocks playback or RTAB-Map. Drops are counted and
      shown.
- [ ] The fake model is visibly labelled as fake on the page.
- [ ] Fake-model e2e passes in the normal suite. The gated
      real-container e2e also covers semantic points.
- [ ] Full-sequence manual run with the real model is recorded.
- [ ] All four gates are green, the docs are wrapped, and no
      `1-WIP/` files remain in the ready PR.

## Out of scope

- A runtime prompt input in the ONNX contract, with Coral labels
  steering SAM concepts (`architecture.md` §3.1). This is the
  natural follow-up.
- Routing SAM through the station RPC server, or running the CM5 and
  the station as separate processes. The demo calls the same
  `Sam3Detector` adapter in-process.
- Landmarks, LLM labelling and GPS anchoring (`surmap_landmarks`,
  `surmap_map`).
- CUDA or station-GPU tuning.
- SAM video-mode tracking identities. Per-image mode is used here.

## References

- `PRD-2026-10-29-live-rtabmap-streaming.md` (this directory): the
  dependency.
- `src/surmap/survey/sam3.py`, `src/surmap/survey/sam.py`: the
  adapter, the ONNX contract and `AnalysisGate`.
- `scripts/make_fake_sam3_model.py`, `tests/fixtures/sam3_fake/`:
  the fake model and the tooling-only dependency pattern.
- `tests/test_sam3.py`, `tests/test_survey_station_sam3_e2e.py`: SAM
  test patterns.
- `src/surmap/survey/stereo.py`: the reconstructor to extend.
- `src/surmap/geometry.py`: `to_map_frame` (reuse it,
  never copy it).
- `src/surmap/motion.py`, `src/surmap/moving/`, `src/surmap/survey/moving_stream.py`: the moving
  classification used for the exclusion rule.
- `src/surmap/demo/server.py`, `tests/test_demo.py`: the demo player,
  the SSE events and their tests.
- `docs/architecture.md` §1 (scope), §3.1 (SAM 3.1 and fallbacks),
  §5 (fuse), §6 (`PointCloud`, `Segment`, `SemanticMap` layers), §9
  (unposed).
- `facebook/sam3.1` on Hugging Face (license-gated).
