---
name: product-overview
description: Answer what SurMap is and whether it can do a given thing — passive drone survey from stereo video and GPS into a GPS-anchored semantic map. Covers what each part ships, its vocabulary, where its live state and docs are, and its documented limits, with the repository paths to read instead of reciting. Use for "can SurMap do X", "does the on-board pipeline support Y", "what is a track / checkpoint / static point", "is this live", or any capability, coverage or terminology question about SurMap.
---

# What SurMap is, and what it can actually do

SurMap is one product: a **passive drone surveyor**. A drone flown by someone
(or something) else carries it; SurMap observes and maps, and never flies.

Source of truth, in order: `README.md` (scope, hardware, model policy),
`docs/architecture.md` (design of record, §6 data contracts),
`src/surmap/` (the implemented scaffold), `tests/` (what is proven).

## The product in one view

| Part | Where it runs | What it does | Code / docs |
|---|---|---|---|
| On-board capture + detection | Raspberry Pi CM5 + Coral Edge TPU + stereo camera | Synchronised stereo frames and GPS checkpoints; labelled detections with track IDs, including moving objects | `docs/architecture.md` §2.1, §5–§6; contracts in `src/surmap/types.py` |
| On-board mapping | CM5 CPU | RTAB-Map estimates the camera trajectory for registration only — never for steering; static-scene points from RTAB-Map, detected objects reconstructed from the stereo pair as separate layers | `src/surmap/slam/` (`base.py` protocol, `rtabmap.py` adapter, `fake.py` for tests), `src/surmap/geometry.py` |
| Motion split | On-board / pipeline | Static objects merge into the map; moving objects stay timestamped tracks and are never baked into the static scene | `src/surmap/motion.py` (`classify_motion`), `Motion` in `src/surmap/types.py` |
| Base station | ROS2 workstation, RTX 5060 Ti | SAM 3.1 segmentation projected onto the point cloud; semantic labels via the newest Meta Llama model on a Models API; one continuously updated, GPS-anchored semantic map | `docs/architecture.md` §2.2, §3; `README.md` model policy |
| Simulation / replay | Third machine, unchosen hardware | Synthetic stereo/GPS with known ground truth, and replay of recorded sessions in the same format as real flights, so the pipeline can be built without flying | `docs/architecture.md` §2.3, §5 |

## Vocabulary (from `src/surmap/types.py`)

- **StereoFramePair** — one synchronised left/right pair (`frame_id`, `t_ns`,
  image references, `calibration_id`). Payloads are referenced, never embedded.
- **GpsCheckpoint** — a GPS fix (`t_ns`, lat/lon/alt, `accuracy_m`) on the same
  clock domain as the frames.
- **Detection** — one labelled box in one frame (`label`, `score`,
  `detector_model_id` — the Edge TPU model that produced it).
- **Track / ObjectTrack3D** — detections associated over time; in 3D, a track's
  `ObjectPoints` observations (points already in the map frame, with centroid).
- **Motion** — `STATIC`, `MOVING` or `UNKNOWN`. Only static objects merge into
  the static map.
- **Pose** — camera pose in the map frame (position + quaternion), from the
  SLAM backend's trajectory.

## Documented limits — answer from these, do not improvise

- **Passive only.** No flight control, no interface to a flight controller, no
  autonomous navigation, path planning, obstacle avoidance, mission
  orchestration or route replanning. Deferred until the passive pipeline works
  end to end on real footage (`README.md`).
- **RTAB-Map output is never a control signal.** It registers points into one
  map; nothing feeds back into steering.
- **Model policy: Meta first.** SAM 3.1 for segmentation, newest Meta Llama
  for labelling. Documented exceptions: the Edge TPU detector (Meta publishes
  no Edge TPU detector) and RTAB-Map (not a learned model). V-JEPA is deferred.
- **Unverified numbers.** SAM 3.1 throughput/VRAM on the RTX 5060 Ti and the
  stereo module's lens baseline must be measured, not assumed
  (`docs/architecture.md` §3.1, `docs/camera-elp-stereo.md`).
- **Not in the baseline:** the Raspberry Pi AI Camera. Do not design a stage
  around it without a named need.

## How to answer a capability question

1. Classify it: in scope now, explicitly deferred, or undecided (open decision
   in `docs/architecture.md`).
2. Cite the path and section you derived it from; quote the contract or test
   that proves an implemented claim (`tests/test_geometry.py`,
   `tests/test_motion.py`, `tests/test_slam.py`, `tests/test_types.py`).
3. Separate *implemented in the scaffold* from *designed but not yet built* —
   most of the pipeline above is design plus contracts, not finished code.
