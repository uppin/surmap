# oversized-file: src/surmap/demo/server.py

**Location:** `src/surmap/demo/server.py` — whole file
**Category:** oversized-file
**Detected:** 2026-10-31 by `/pr-wrap` step 4 (file-length gate; `/analyze-code-issues` not run on `surmap` yet)
**Metrics:** 1750 lines (2026-11-03; was 1514 at detection) (limit 500) · coverage not measured
**Restructure:** required — split into focused modules, `/code-restructuring` territory
**Status:** Open (a record exists only while the issue is open — fixing it deletes the file)

## Measurement history

| Run | Lines | Note |
|---|---|---|
| 2026-10-31 | 1524 → 1514 | `feat/sam-region-points`: base already 1524 (grown by #53, #54); this PR moved `DemoEvent` and `sam_event` out into `demo/events.py` with its own region placement, so it did not grow the file |
| 2026-10-31 | 1819 → 1814 | `feat/sam-surfaces`: surface assignment, persistence and rendering went to `survey/surfaces.py`, `demo/events.py`, `demo/history.py` and the new `demo/surface_render.py`; the browser `cloud_regions` round-trip it replaced was deleted |
| 2026-10-31 | 1814 → 1836 | `feat/demo-sam-prompt` (after merging `feat/sam-surfaces`): prompt resolution and the SAM pane markup went into `demo/sam_prompt.py`; the +22 is the per-run prompt plumbed through `DemoPlayer`, `make_demo_server` and the stream handler |
| 2026-11-02 | 2188 → 2089 | `feat/demo-object-feed`: the 3D render and its session state (pose, Follow, picking ids) moved to the new `demo/cloud_view.py`, rewound-moment surfaces to `demo/surface_timeline.py`; the file shrank |
| 2026-11-02 | 2089 → 2140 | `feat/demo-run-export-import`: the archive logic is the new `demo/run_archive.py`; the +51 are the two routes and the handlers that stream an export out and an upload in (candidates to move next to `run_archive.py`) |
| 2026-11-02 | 2174 → 2215 | `fix/demo-dense-depth-t-ns`: the per-pixel depth read is `slam/dense.display_depth` and the journalled SAM source `demo/sam_journal.py`; the +41 are the run-scoped dense-depth route and the Rebuild RTAB-Map route and `start_run` override |
| 2026-11-03 | 2215 → 1750 | `refactor/demo-run-engine-split` (#77): `DemoRunHost`, `_RunEngine`, `_Preparation`, `_record_map` and `TAKEOVER_TIMEOUT_S` moved to `demo/runs.py` (440 lines) and `PlaybackControls` to `demo/playback.py` (71); the display / floor-plan / HTTP / workers splits below are still open |

## What the tool found

A 1750-line module (1514 when detected) three and a half times the 500-line limit. Coverage was not measured (no merged
coverage run on `surmap`); "not measured" is not "clean".

## Why it matters here

Every demo feature lands here — dataset preparation glue, playback (`DemoPlayer`), the held-frame
display (`_Display`), the detection and SAM workers, floor-plan rendering, the HTTP handler and
`make_demo_server`. A change to any of them is reviewed inside a file nobody can hold in their head,
and per-PR growth is invisible in a diff (#53 and #54 each added hundreds of lines).

## What would close it

A mechanical split at the seams already visible in the file, each module under ~300 lines:
`demo/workers.py` (`_DetectionWorker`, `_SamWorker`, `_SamStreamWorker`), `demo/display.py`
(`_HeldFrame`, `_Display`, overlay projection and colouring), `demo/floor_plan.py`
(`FloorExtent`, `render_floor_plan`, floor-plane helpers), `demo/http.py` (`_DemoHandler`,
`_DemoHttpServer`, `make_demo_server`), leaving `DemoPlayer` in `server.py`. Same green before
and after; public names (`DemoPlayer`, `make_demo_server`, `project_overlay`,
`rectified_to_raw`, `depth_colour`, `FloorExtent`) re-exported explicitly from `server.py` so
tests and scripts keep their imports.

## Verified by hand

2026-10-31 — `wc -l` at the merge base `c126ded` (1524) and at the wrap (1514); the seams above
were read from the file's class and function list (`grep -n "^class\|^def"`), not inferred. No
analyzer ran, so complexity and coverage are unknown.
