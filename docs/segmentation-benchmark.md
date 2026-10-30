# Segmentation benchmark

Offline scores for the three SAM routes on a recorded disaster-block
flight. The bench does not fly the aircraft and does not call a model
unless `run` or `label` is started with the matching `SURMAP_LIVE_*`
flag. Design of the survey is [architecture.md](architecture.md). The
SLAM ↔ segmentation field names. PR #48
(`docs/segmentation-protocol-guidelines.md` on
`feat/segmentation-protocol-guidelines`) is the handoff note. This
bench follows it where the code already agrees. Disagreements are
listed at the end.

## Scoring frame and clock

Until the map frame is decided, every number in a report is measured in
one place: `surmap.segbench.conventions.DEFAULT_SCORING`.

| Field | Default | What it means |
|---|---|---|
| `map_frame` | `gazebo_enu` | Gazebo ENU metres. The origin is the PX4 home anchor. |
| `pixel_space` | `rectified` | Rectified left-camera pixels. |
| `clock` | `sim_time` | Simulation time, stored in `t_ns` as integer nanoseconds. |
| `match_radius_m` | `3.0` | A survivor landmark matches a person inside this radius. |

A bench file may override those four fields under `scoring`. The loader
rejects a pose whose `frame` is not `map_frame`, and a row whose
`clock` or `pixel_space` disagrees. Changing the name does not
reproject. Poses and ground truth must already be in that frame.

3D survivor recall reuses `surmap.mission.metrics.score_survivors`.

## Metrics

Per frame, on the rectified left image:

- mean IoU of predicted instances against ground-truth instances
  (Hungarian matching, a pair counts only at IoU ≥ 0.5; an unmatched
  instance counts as 0)
- boundary F1, with a 2 px tolerance
- pixel precision and recall on the union of the instances
- survivor instance recall (ground-truth instances whose class name
  contains `person` or `survivor`)
- false positives per frame (predicted instances that did not match)

3D, in the scoring map frame:

- survivor recall at 3 m, mean position error, and time to first
  detection, from `score_survivors`
- false-positive landmarks: survivor-labelled landmarks that did not
  match a person

Ops, from the detections JSONL:

- latency p50 and p95 (linear rank of the sorted samples)
- input tokens, output tokens, and GPU seconds
- cost per frame from a price table (below). An unset price is zero.

## Projection

`surmap.survey.mask_cloud.points_in_mask` keeps every camera point
whose pixel lies inside the polygon and whose depth is past 5 cm. It
has no z-buffer. A farther point on the same pixel is claimed as well,
so the mask also takes background behind the subject. That function is
unchanged; the live mission still calls it.

`surmap.segbench.project.project_mask` keeps one point per pixel, the
nearest, and only then tests the polygon. Fusion uses that z-buffer.
Points at or nearer than 5 cm are still dropped.

## Fusion

`surmap.segbench.fusion` builds a voxel log-odds grid.

- Voxel size 0.2 m.
- Evidence is written only for voxels that are visible after the
  z-buffer.
- A masked voxel gets `w * logit(clip(sam_score * label_conf, 0.05, 0.95))`.
  A detection flagged `score_missing` uses the clip floor, because a
  Meta score of 1.0 can mean the response had no confidence.
- `w` is visibility (1 for a z-buffer winner) times distance decay
  `exp(-depth / 20 m)` times an edge weight. On the mask boundary the
  edge weight is 0.25; it rises to 1 across 3 px.
- A visible unmasked voxel gets negative evidence of the same weight.
- Voxels with log-odds above 0 are clustered (DBSCAN-style, 0.6 m,
  minimum one voxel) into landmarks.

A landmark carries the architecture fields: centroid in the map frame,
contributing `frame_ids`, `mask_ids`, and `track_ids`, label,
confidence, observation count, and first/last `t_ns`. `model_id` is
the labeller, filled when `label` runs. `sam_model_id` and `sam_source`
keep the segmenter, which is a different string. Latitude, longitude,
and altitude stay empty until a GPS anchor is applied.

`label_requests` yields one crop per landmark, the view with the
highest `weight * score`. Muse is called on that crop, not once per
detection. `seg_bench label` is live-gated. `fuse` is offline.

## Dataset layout

```text
bench/
  bench.json                 scoring frame, clock, intrinsics
  classes.json               "1" person, "2" car, "3" debris, "4" water
  frames.jsonl               one record per keyframe
  images/0000.png            rectified left image
  masks/0000_instance.png    instance ids
  masks/0000_class.png       class ids
  clouds/0000.json           optional {"space": "camera"|"map", "points": [...]}
```

A frame record follows the protocol where the code already has the
fields: `frame_id`, `t_ns`, `clock`, `pixel_space`, `left_ref`, and

```json
"pose": {
  "position_m": {"x": 0.0, "y": 0.0, "z": 8.0},
  "orientation_xyzw": [0.0, 0.0, 0.0, 1.0],
  "frame": "gazebo_enu"
}
```

The quaternion is `(x, y, z, w)`. Intrinsics are the pinhole of that
image (`fx`, `fy`, `cx`, `cy`, `baseline_m`). Distortion is
`radial-tangential` `[k1, k2, p1, p2]`, default zeros. The Gazebo
camera is a pinhole, so raw and rectified pixels match on this sim.
Masks for a real RTAB-Map flight must still say which of the two they
were drawn on.

Class ids written into the world:

| Id | Name | Models |
|---|---|---|
| 1 | person | `survivor_*` |
| 2 | car | `car_*` (including `car_in_flood`) |
| 3 | debris | rubble, planks, tires, burial mounds, `*debris*` |
| 4 | water | `*flood*` that is not a survivor or a car |

## Building a set from SITL

Gazebo is not started by these commands. The operator launches the
existing disaster world (see
[docs/simulation/gazebo-disaster-world.md](simulation/gazebo-disaster-world.md)
and [docs/simulation/px4-sitl.md](simulation/px4-sitl.md)). The stereo
model now has two segmentation cameras on the left eye:
`left_segmentation_instance` and `left_segmentation_semantic`.

Label the world once (idempotent):

```bash
uv run python scripts/gz_label_models.py
```

Dump, from a ROS-sourced shell. Topics are the bridged image and pose
topics for that run:

```bash
source /opt/ros/jazzy/setup.bash
python3 scripts/ros2/dump_sitl_capture.py \
  --left /cam_left/image_raw \
  --right /cam_right/image_raw \
  --seg /cam_left/segmentation_instance \
  --seg-class /cam_left/segmentation_semantic \
  --pose /cam_left/pose \
  --output "$HOME/sitl-runs/disaster-01" \
  --seconds 180
```

`--pose` expects `geometry_msgs/PoseStamped` (translation plus
quaternion). The stamp is stored as `t_ns` with `clock: sim_time`.
That integer is the ROS header stamp; on this SITL world the header
clock is simulation time.

Full-flight set, 1 Hz keyframes, no network:

```bash
uv run python scripts/export_seg_bench.py \
  --capture "$HOME/sitl-runs/disaster-01" \
  --out "$HOME/sitl-runs/bench"
```

Dev set: 20 frames whose class mask contains a person, then 10 hard
negatives (clutter, no person). A short flight raises instead of
padding with empty frames.

```bash
uv run python scripts/export_seg_bench.py \
  --capture "$HOME/sitl-runs/disaster-01" \
  --out "$HOME/sitl-runs/bench" \
  --dev-set --survivors 20 --negatives 10
```

The command prints the chosen `frame_id`s. The bench directory stays
the full 1 Hz set; those ids are the dev subset
(`surmap.segbench.dataset.select_dev_set`).

## Commands

Offline, from recorded files:

```bash
uv run python scripts/seg_bench.py fuse \
  --bench "$HOME/sitl-runs/bench" \
  --detections "$HOME/sitl-runs/replay.jsonl" \
  --out "$HOME/sitl-runs/landmarks.json"

uv run python scripts/seg_bench.py score \
  --bench "$HOME/sitl-runs/bench" \
  --detections "$HOME/sitl-runs/replay.jsonl" \
  --landmarks "$HOME/sitl-runs/landmarks.json" \
  --route replay \
  --out "$HOME/sitl-runs/replay-report.json" \
  --markdown "$HOME/sitl-runs/replay-report.md"

uv run python scripts/seg_bench.py compare \
  --reports "$HOME/sitl-runs/meta-report.json" "$HOME/sitl-runs/modal-report.json" \
  --out "$HOME/sitl-runs/compare.md"
```

`run --route replay` copies a detections JSONL and writes an empty
usage file. It does not need a live flag.

Prices are optional. Keys are `meta`, `modal`, `station-onnx`,
`replay`, or whatever `source` the JSONL records. Missing keys cost
zero, so a report does not invent a bill.

```json
{
  "meta": {
    "usd_per_million_input_tokens": 0.0,
    "usd_per_million_output_tokens": 0.0,
    "usd_per_gpu_second": 0.0
  }
}
```

Pass the file with `--prices`.

## Live runs

Keys stay in the environment. Use single quotes so `$` in a key is not
expanded. Do not commit a key, a `.env`, or a usage log copied from a
machine that has one.

Caps are `SURMAP_BUDGET_<PROVIDER>_CALLS` and
`SURMAP_BUDGET_<PROVIDER>_TOKENS` (provider upper-cased: `META`,
`MODAL`, `BASETEN`). An unset variable means no cap. The ledger is
`SURMAP_USAGE_LOG`.

Meta SAM, from WSL, after the bench exists:

```bash
export SURMAP_LIVE_META=1
export MODEL_API_KEY='paste-key-here'
export SURMAP_BUDGET_META_CALLS=40
export SURMAP_BUDGET_META_TOKENS=200000
export SURMAP_USAGE_LOG="$HOME/sitl-runs/segbench-meta-usage.jsonl"

uv run python scripts/seg_bench.py run \
  --route meta \
  --bench "$HOME/sitl-runs/bench" \
  --out "$HOME/sitl-runs/meta-detections.jsonl" \
  --usage "$SURMAP_USAGE_LOG"
```

The meta route decodes each bench image to `raw_rgb` before `detect`.
Meta's adapter rejects `png`.

Modal SAM. The scene-note flag is not required for this command:

```bash
export SURMAP_LIVE_MODAL=1
export MODAL_SAM_URL='https://your-modal-endpoint'
export SURMAP_BUDGET_MODAL_CALLS=40
export SURMAP_USAGE_LOG="$HOME/sitl-runs/segbench-modal-usage.jsonl"

uv run python scripts/seg_bench.py run \
  --route modal \
  --bench "$HOME/sitl-runs/bench" \
  --out "$HOME/sitl-runs/modal-detections.jsonl" \
  --usage "$SURMAP_USAGE_LOG"
```

Station ONNX is local. It has no `SURMAP_LIVE_*` flag and does not
open a socket:

```bash
uv run python scripts/seg_bench.py run \
  --route station-onnx \
  --model /path/to/sam3.onnx \
  --bench "$HOME/sitl-runs/bench" \
  --out "$HOME/sitl-runs/station-detections.jsonl" \
  --usage "$HOME/sitl-runs/station-usage.jsonl"
```

One Muse call per landmark:

```bash
export SURMAP_LIVE_BASETEN=1
export BASETEN_API_KEY='paste-key-here'
export SURMAP_BUDGET_BASETEN_CALLS=30
export SURMAP_BUDGET_BASETEN_TOKENS=200000
export SURMAP_USAGE_LOG="$HOME/sitl-runs/segbench-baseten-usage.jsonl"

uv run python scripts/seg_bench.py label \
  --bench "$HOME/sitl-runs/bench" \
  --landmarks "$HOME/sitl-runs/landmarks.json" \
  --out "$HOME/sitl-runs/labelled.json"
```

`--provider modal` uses `SURMAP_LIVE_MODAL` instead. Meta's client in
this tree writes a scene note, not a per-landmark label, so
`--provider meta` refuses.

The mission command can keep SAM on Modal while Meta writes the scene
note. The default SAM route is Modal when `SURMAP_LIVE_MODAL=1`, and
Meta otherwise. `--sam-route meta` or `--sam-route modal` overrides it.
The live SAM prompt defaults to `person` (`SURMAP_SAM_PROMPT` overrides
it). Muse is given a JPEG crop of the detection box plus 16 px, not
the whole frame.

```bash
export SURMAP_LIVE_META=1
export SURMAP_LIVE_MODAL=1
export SURMAP_LIVE_BASETEN=1
export MODEL_API_KEY='paste-key-here'
export BASETEN_API_KEY='paste-key-here'
export MODAL_SAM_URL='https://your-modal-endpoint'
export SURMAP_BUDGET_META_CALLS=5
export SURMAP_BUDGET_MODAL_CALLS=40
export SURMAP_BUDGET_BASETEN_CALLS=30

uv run python scripts/mission_demo.py --live \
  --sam-route modal \
  --capture "$HOME/sitl-runs/disaster-01" \
  --no-viewer
```

## Where this disagrees with PR #48

PR #48 is guidance. It does not pick a side. This bench does, for scoring only.

- The report's map frame is `gazebo_enu` (origin at the PX4 home). The
  protocol example uses `rtabmap_map`. `surmap.types.Pose` still has no
  `frame` field; the bench stores the string beside the pose.
- The report clock is `sim_time`. The protocol's suggested clock names
  are `cm5_monotonic`, `ros_header_stamp`, and `dataset`. The SITL
  integer is still the ROS header stamp. On this world that stamp is
  simulation time, so the bench labels it `sim_time`.
- `points_in_mask` still has no z-buffer. The bench projection does.
  Callers of `points_in_mask` are unchanged.
- A Meta response with no confidence is stored as score `1.0`. The
  protocol says that `1.0` means missing. Fusion treats `1.0` as a
  probability unless the detection is marked `score_missing`.
- A landmark's `model_id` is the labeller, as in the architecture.
  `sam_model_id` is the segmenter. The protocol warns against copying
  one into the other.
- Several coordinate frames remain in the tree (camera optical, local
  ENU, the demo floor, EuRoC body). This bench does not decide which
  one RTAB-Map's map pose is. Odometry versus the graph pose is left
  for Mantas.
- The image the demo shows can be raw. The image RTAB-Map tracks is
  rectified. Bench 2D metrics are rectified left pixels. On the Gazebo
  pinhole those two spaces match.

## What this does not do

No Gazebo process is launched here, so there is no recorded 30-frame
flight in the tree. The synthetic report covered by
`tests/test_segbench_cli.py` is the offline render. Live providers are
not called from the test suite.
