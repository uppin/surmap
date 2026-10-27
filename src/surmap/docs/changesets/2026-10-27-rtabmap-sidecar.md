# RTAB-Map sidecar backend

**Date:** 2026-10-27
**Type:** Feature
**Packages:** surmap

Added `surmap.slam.sidecar.SidecarRtabmapBackend`: streamed stereo
pairs (image bytes now carried on `StereoFramePair`) are staged as a
EuRoC-style dataset and, at end of stream (`flush()`, invoked by
`stream_survey` before closing the stream), run through the pinned
RTAB-Map Docker image — `rtabmap-euroc_dataset` then
`rtabmap-export --cloud --poses` — with the exported poses and
assembled cloud parsed back into `FrameResult`s (cloud attached to
the last posed result). No RTAB-Map is installed on any host; the
image is pinned by digest (`introlab3it/rtabmap@sha256:14a58a…`).

Tooling: `scripts/fetch_rtabmap_fixture.py` pulls that image and cuts
a 90-pair EuRoC V1_01_easy subset (half resolution, CRC-verified zip
range extraction) into `tests/fixtures/euroc_v101_rtabmap/`. The CM5
process selects the backend via `--slam-backend sidecar
--calibration-dir <dataset>`. Verification: unit tests with a fake
docker runner, plus `tests/test_survey_cm5_rtabmap_e2e.py` — real CM5
socket server + real RTAB-Map container, EuRoC pairs in, >10k real
RTAB-Map points and a moving multi-pose trajectory out, server and
sidecar closed afterwards (CI runs it in the `rtabmap-e2e` job after
the fetch script, with `SURMAP_REQUIRE_RTABMAP_E2E=1`).

Proving run (manual, same pinned image/dataset): RTAB-Map 0.24.2
tracked all 90 pairs, exported 5 optimized poses travelling ~0.8 m
and a 14,874-point assembled cloud.
