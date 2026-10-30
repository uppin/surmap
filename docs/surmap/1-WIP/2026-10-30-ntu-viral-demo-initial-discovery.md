# Initial Discovery: NTU VIRAL outdoor drone scene

**Changeset**: [2026-10-30-ntu-viral-demo.md](./2026-10-30-ntu-viral-demo.md)
**Date**: 2026-10-30
**Passes**: 1

## Combined Conclusions

- **NTU VIRAL** (ntu-aris.github.io/ntu_viral_dataset): a UAV with two
  time-synchronised uEye 1221LE monochrome cameras, 752×480 at 10 Hz,
  externally triggered (stamps ≤ 3 ms apart), plus LiDARs, IMU, UWB.
  Licence CC BY-NC-SA 4.0, non-commercial academic use; the user's use is
  a personal hobby. Primary host: Hugging Face
  `Yuan-Shenghai/NTU-VIRAL-DATASET`, byte-for-byte from NTU Dataverse,
  with `SHA256SUMS.txt`. `sequences/sbs_01.zip` (Biological Sciences
  front square, 354 s): 3,775,725,925 B, SHA-256
  `16063577be7b0d8b6ca89e40cf3ec45d603469048e7d989d25bab88f3950c390`.
- **Format:** each sequence zip holds a ROS 1 bag; images on
  `/left/image_raw`, `/right/image_raw` (`sensor_msgs/Image`).
- **Calibration** is not in the zip. The dataset authors' VINS-Fusion
  config (`brytsknguyen/VINS-Fusion@3d8bf9e`
  `config/ntuviral/viral_stereo_imu_config.yaml`, `camLeft.yaml`,
  `camRight.yaml`): PINHOLE, 752×480; left fx 425.0259 fy 426.7976 cx
  386.0152 cy 241.9130, k1 −0.28811 k2 0.07458 p1 7.784e−4 p2 −2.278e−4;
  right fx 431.3364 fy 432.7528 cx 354.8956 cy 232.5509, k1 −0.30027
  k2 0.09054 p1 3.330e−5 p2 8.990e−5; `body_T_cam1` (left, t_y −0.1243)
  and `body_T_cam0` (right, t_y +0.1348) in a forward-right-down body →
  baseline ≈ 0.259 m.
- **Reader:** `rosbags` 0.11.9 (pure Python, typed; user-approved
  dependency). `typestore.deserialize_ros1` returns `object`, so a typed
  adapter must contain it.
- The pipeline needs EuRoC layout (`mav0/cam0|cam1/data/<t_ns>.png`,
  `sensor.yaml`); `ensure_dataset` dispatches on `dataset_format`.

## Exploration 1: dataset, calibration and reader — 2026-10-30

**Agent**: parent WebSearch/WebFetch/curl/Read
**Scope**: an outdoor drone stereo scene the demo can play

### Sequence

1. WebSearch NTU VIRAL, MARS-LVIG, UZH-FPV, Mid-Air — licence, cameras, access.
2. WebFetch ntu-aris.github.io/ntu_viral_dataset — sequences, licence, hosting.
3. curl Hugging Face API trees: sequences, calibration, official_docs; `SHA256SUMS.txt`.
4. curl `SENSORS_AND_CALIBRATION.md`, `official_docs/sensor_calibration.md` — topics, pinhole model.
5. curl `BASELINES.md` → VINS-Fusion config; `camLeft.yaml`, `camRight.yaml`.
6. `uv add rosbags`; mypy probe of `rosbags.rosbag1.Reader` / `deserialize_ros1`.

### Findings

UZH-FPV is fisheye (186° FOV), MARS-LVIG single camera; NTU VIRAL is the
only checked outdoor UAV stereo set with a pinhole calibration.
