# oversized-file: src/surmap/demo/server.py

**Location:** `src/surmap/demo/server.py` — whole file
**Category:** oversized-file
**Detected:** 2026-10-31 by `/pr-wrap` step 4 (file-length gate; `/analyze-code-issues` not run on `surmap` yet)
**Metrics:** 1514 lines (limit 500) · coverage not measured
**Restructure:** required — split into focused modules, `/code-restructuring` territory
**Status:** Open (a record exists only while the issue is open — fixing it deletes the file)

## Measurement history

| Run | Lines | Note |
|---|---|---|
| 2026-10-31 | 1524 → 1514 | `feat/sam-region-points`: base already 1524 (grown by #53, #54); this PR moved `DemoEvent` and `sam_event` out into `demo/events.py` with its own region placement, so it did not grow the file |
| 2026-10-31 | 1819 → 1841 | `feat/demo-sam-prompt`: prompt resolution and the SAM pane markup went into `demo/sam_prompt.py`; the +22 is the per-run prompt plumbed through `DemoPlayer`, `make_demo_server` and the stream handler |

## What the tool found

A 1514-line module three times the 500-line limit. Coverage was not measured (no merged
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
