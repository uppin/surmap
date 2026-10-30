# Initial discovery — disaster mission demo

**Date:** 2026-10-29

## State A

Open pull requests each ship one piece of a civilian search-and-rescue
survey: Gazebo/PX4 SITL and the disaster block (#18, including #36),
Meta Muse Spark scene note (#29), Baseten labels (#31), Modal SAM
(#32), Meta SAM 3.1 (#33), mask projection (#34), the GPS snapshot
(#35), and the survey viewer (#37). Nothing runs them as one command.
The ground-truth `people` array is the survivor list. PR #36's text
said six people; the JSON on `feat/PX4_sitl` lists the ids in
`docs/simulation/gz/worlds/disaster_block_ground_truth.json`. Live
RTAB-Map streaming from PR #38 is merged into this branch.
`surmap.mapqa` exists on `cursor/ask-the-map-2463` and has no pull
request. The viewer
already delegates `POST /ask` to `surmap.mapqa.answer` when
`SURMAP_LIVE_META=1` and that package imports.

## State B

`feat/mission-demo` contains those pull requests, including #38's
streaming backend from `main`. `scripts/mission_demo.py` runs the
chain offline by default and live only behind the existing env flags.
Live mode feeds the capture to `StreamingRtabmapBackend`. Impact
metrics read the people array. The viewer shows the report. Docs:
`docs/mission-demo.md` and `docs/simulation/gazebo-disaster-world.md`.

## Delta

Merge the branches, resolve `HACKATHON.md`, `labelling/__init__.py`,
and `mask_outline` (Meta renamed it; Modal still imported the private
name). Add the mission package, tests, and the two docs. Live mode
uses #38's streaming backend. `surmap.mapqa` stays a named hook.
