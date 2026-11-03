# 2026-11-03 — Streaming sidecar feeds RTAB-Map identity odometry covariance

**Category:** Correctness (bug, found by the Bevy perfect-world loop)
**Source:** PR #89 (`feat/bevy-sim-photoreal-rtabmap-stream`), stack `#sim-disaster` n1
**Packages:** deploy/rtabmap-stream, surmap.slam
**Consent:** Developer, 2026-11-03: "let's wrap the PR with TODO and we'll address the correctness in next PRs".
**Priority:** 1
**Status:** Fixed in code (2026-11-03, camera-calibration-rpc changeset):
`deploy/rtabmap-stream/main.cpp` now passes the odometry covariance
to `Rtabmap::process`, prepared as RTAB-Map's `RtabmapThread` does
(`odom_covariance.h`: sanity check, largest value carried across
dropped nodes, cleared on odometry reset), unit-tested by
`odom_covariance_test.cpp` in the image build and pinned by
`tests/test_rtabmap_stream_covariance.py`. What remains is the end-to-end proof in
`2026-11-03-bevy-loop-closure-acceptance.md` (map-corrected end
error ≤ odometry's over the full loop), which needs the loop capture.

## What is wrong

`deploy/rtabmap-stream/main.cpp` calls `slam.process(data, odomPose)`. RTAB-Map's third
argument, the odometry covariance, defaults to `cv::Mat::eye(6,6)` — 1 m and 1 rad of
uncertainty on every odometry link — so the graph barely trusts odometry and weak
proximity/loop links drag the optimised map by metres. Every live RTAB-Map run in SurMap
is affected, not only the simulation.

## Evidence

Full 182 m Bevy survey loop (487 frames at 4 Hz, lockstep, anchored to the truth at
frame 1, never re-fitted): odometry ends 1.48 m from the truth (0.81 %), but the
map-corrected pose (`getMapCorrection() * odomPose`) ends 34–36 m off with peaks of
37–47 m, and is not repeatable between identical runs (2.2 m vs 33.7 m at the end).
Stricter loop verification (`Vis/MinInliers=40`, `RGBD/OptimizeMaxError=1.0`,
`RGBD/ProximityBySpace=false`) does not change it. Top-down plot: odometry on the
truth around the whole loop; the corrected track leaves it at the first corner.

## The fix to try first

`slam.process(data, odomPose, info.reg.covariance.empty() ? cv::Mat::eye(6, 6, CV_64FC1) : info.reg.covariance)`,
rebuild the image, re-run the loop; acceptance: map-corrected end error ≤ odometry's,
and the closure correction at the return to the start is small (< 0.5 m). Pairs with
`2026-11-03-bevy-loop-closure-acceptance.md`.
