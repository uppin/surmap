# Initial Discovery: recognisable live floor plan and map-frame camera

**Changeset**: [2026-10-30-map-render.md](./2026-10-30-map-render.md)
**Date**: 2026-10-30
**Passes**: 1

## Combined Conclusions

- **Floor plan shimmers.** `_floor_plane_cloud` stride-samples 4,000 of
  the map's points (~1M on NTU VIRAL sbs_01 at frame ~2900); as the cloud
  grows each map event picks different points.
- **Camera detached from its trajectory.** The marker uses raw odometry;
  trajectory and cloud use the optimised graph. Measured on sbs_01
  (1,500 frames): odometry-vs-graph gap per keyframe median 1.39 m, p95
  5.19 m, max 5.32 m; one re-optimisation moved nodes by > 1 m. Odometry
  itself: 0 jumps > 1 m, 0 resets. RTAB-Map 0.24 exposes
  `Rtabmap::getMapCorrection()` (map ← odom).
- **SLAM accuracy vs Leica ground truth** (sbs_01, first 1,500 frames,
  rigid Umeyama alignment): 376×240 ATE 3.35–3.57 m, best-fit scale
  1.20–1.28; 752×480 with no drops ATE 3.34 m, scale 1.20. The authors'
  stereo calibration re-run (132 checkerboard pairs, 9×6, 80 mm, RMS
  0.359 px) gives baseline 0.2593 m — matching the registry. Giving each
  stream the other camera's intrinsics: ATE 7.95 m. So the residual
  error is stereo-only odometry on this flight, not resolution, drops or
  calibration; IMU fusion is the remaining lever.

## Exploration 1: probes — 2026-10-30

**Agent**: parent probes (scratch scripts) and Read
**Scope**: why the NTU VIRAL floor plan is unrecognisable and the camera jumps

### Sequence

1. `probe_ate.py` — ATE / scale vs `ground_truth/sbs_01/ground_truth.csv` at 376 and 752 wide, with and without drops.
2. `stereo_calib.py` — `cv2.stereoCalibrate` on `calibration/calib_stereo.zip` (authors' recipe).
3. `probe_divergence.py` — odometry vs graph per keyframe; graph jumps.
4. Grep `getMapCorrection` in the sidecar image's `Rtabmap.h` (line 349).
