# Disaster mission demo

**Date:** 2026-10-29
**Feature:** One-command search-and-rescue mission

Added `scripts/mission_demo.py`. Offline, the default, exports the
recorded SITL fixture to EuRoC, projects a fixture mask cloud with
`points_in_mask`, writes a `surmap.semantic_map_snapshot.v1` file,
opens the survey viewer on `127.0.0.1:8770`, and answers "Where are
the survivors?". Impact metrics compare those points with the `people`
array in the disaster-block ground-truth JSON and record the basis
`fixtures`. Live mode calls Meta, Baseten, and Modal only when
`SURMAP_LIVE_META`, `SURMAP_LIVE_BASETEN`, and `SURMAP_LIVE_MODAL` are
set. Live mode feeds the capture through `StreamingRtabmapBackend`
(PR #38) and reads `map_snapshot()` as the cloud. Runbook:
`docs/mission-demo.md`. Gazebo overview:
`docs/simulation/gazebo-disaster-world.md`.
