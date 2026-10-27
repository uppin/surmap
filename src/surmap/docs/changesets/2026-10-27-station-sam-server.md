# Station SAM server

**Date:** 2026-10-27
**Type:** Feature
**Packages:** surmap

Added `stream_analysis` and `station_service_module` in
`surmap.survey.station_server`. Frames are admitted concurrently
through the n3 gate (one analysis at a time); admitted frames answer
as `SamFrameDetections` in arrival order, dropped frames get no
answer. Verification: V1 fail→pass handler integration tests,
including a deterministic drop test (389 passed at wrap, mypy strict
and Ruff clean).
