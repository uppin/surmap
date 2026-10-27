# Initial Discovery — CM5 stereo reconstruction

## Combined Conclusions

- The stack merged to `main`: `cm5_server.stream_survey` pairs frames
  and streams `SlamBackend.static_points` (designation 1) plus object
  points, but the only backend with points in tests is a fake — frame
  **bytes never reach any point-producing code**. `StereoFramePair`
  carries refs, not pixels, so reconstruction needs a new frame-aware
  seam in the CM5 stream, not a new `SlamBackend`.
- Geometry help exists: `surmap.geometry.to_map_frame(point, pose)`.
- No numpy/Pillow in the project dependencies today.
- Dataset verified by hand before planning: ETH3D SLAM `cables_2`
  (98 stereo frames, calibration + extrinsics per camera). Ten pairs
  were cut to `tests/fixtures/eth3d_cables2/` (892 KB total). The pair
  is unrectified (right principal point offset); a prototype with
  principal-point alignment + SAD block matching yielded ~12k valid
  points, median depth 0.60 m on pair 1 — detections are assertable.
- Real RTAB-Map is not available in CI and stays the pose source
  behind `SlamBackend` later; this change keeps pose behind that port
  (in-memory pose in tests) and makes the **points** real.

## Exploration 1 — dataset + prototype pass (2026-10-27)

Downloaded `cables_2_mono.zip` + `cables_2_stereo.zip` from
eth3d.net; read `calibration.txt` (fx 726.29, cx 354.65, cy 186.47),
`calibration2.txt` (fx 726.04, cx 385.73, cy 262.20) and
`extrinsics_1_2.txt` (baseline 0.0898 m, near-identity rotation);
checked image sizes (739×458 / 742×464); prototyped alignment +
block matching in numpy (see Combined Conclusions for the result);
read `src/surmap/geometry.py` and the merged survey modules.
