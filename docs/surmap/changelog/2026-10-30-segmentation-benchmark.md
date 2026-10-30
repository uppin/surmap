# Offline segmentation benchmark

**Date:** 2026-10-30
**Feature:** Survey scoring

`surmap.segbench` scores SAM polygons and fused landmarks from a
recorded bench. 3D numbers use Gazebo ENU at the PX4 home, 2D masks
use rectified left pixels, and the clock is simulation time in `t_ns`.
Hosted routes stay behind `SURMAP_LIVE_*` and the budget caps.
Runbook: `docs/segmentation-benchmark.md`.
