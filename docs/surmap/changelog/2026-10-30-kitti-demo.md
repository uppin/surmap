# KITTI outdoor demo scene

**Date:** 2026-10-30
**Feature:** browser demo / dataset registry

A second scene: KITTI raw `2011_09_26_drive_0009` (a 45 s Karlsruhe city
drive), fetched once from KITTI's own S3 host with its calibration zip
(both size + SHA-256 pinned) and converted locally to the demo's EuRoC
layout — grey rectified `image_00`/`image_01` named by cam0's
timestamps, `sensor.yaml` from `P_rect`/`S_rect` with zero distortion and
the baseline from `P_rect_01`. KITTI is CC BY-NC-SA 3.0 for academic use;
the page credits it and the data is never re-hosted.

Scenes now set their display size, playback rate, overlay depth stops
and keyframe depth cap (sent to the sidecar as `max_depth_m`); EuRoC
keeps its previous values. Batch mode is refused for a scene without an
IMU.

Verification: gates green (pytest 555 passed, 2 skipped); EuRoC
real-container e2e green. Full KITTI drive with the Coral detector on an
Apple Silicon host: 252 m travelled, floor plan ≈ 197 × 223 m, keypoints
on 338/447 frames, detections car 1227 / person 120 / truck 33 / bus 14;
the emulated sidecar (63 ms median per pair) dropped 55 pairs at 10 Hz.
