# Generic test console — persisted runs, history scrub, 3D point cloud

**Date:** 2026-10-31
**Feature:** browser demo

The demo page became a generic testing page. Every run was persisted as
it streamed to a SQLite database (`demo-history.db` in the dataset cache,
`--history-db` to override): one row per shown frame with its JPEG,
overlay points and camera, the detections per frame, and a point-cloud
snapshot per map update. The server announced the run over SSE (`run`
event) and served the history back (`GET /runs`, `GET /runs/<id>`,
`GET /runs/<id>/snapshot?seq=N`); a snapshot joins the frame at that
position with the newest cloud at or before it, so the page's timeline
slider and ±1/±10 step buttons rewind and wind forward showing each
moment's image, overlay points, detections and point cloud — not the
final cloud. Earlier runs reopen from the persisted-runs picker.

Map and final events now also carry the raw cloud (sampled to 12,000
points, full count still reported) for the new 3D point-cloud pane: a
WebGL view in a drag-resizable, fullscreenable pane with Pan/Tilt/Zoom
buttons, drag to orbit, Shift+drag to pan, wheel to zoom and Reset view.
The server-rendered floor plan stayed as a mini-map, re-drawn from the
scrubbed cloud when scrubbing. `page.py` (650 lines with the 3D script)
was split: the WebGL script moved verbatim to `cloud_script.py`, spliced
into the page before formatting (page 479 lines).

Verification: gates green (ruff, mypy strict, pytest 619 passed /
3 skipped on the implementation; two unrelated load-sensitive failures
on a later full run — the moving-differencing frame budget and the
RTAB-Map container e2e — reproduced on the untouched base, the first
failing there too and the second skipping). No browser on the build
machine, so the WebGL pane was verified by rendered-JS syntax check and
HTTP probes, not visually.
