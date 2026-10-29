# SurMap architecture — passive survey

Status: design, plus a Python scaffold in `src/surmap/` implementing
the §6 contracts, geometry, motion classification, and the SLAM
backend interface (RTAB-Map adapter + in-memory backend for tests).
Stack: Python (uv-managed). Three machines, defined in §2.

## 1. Scope boundary

SurMap is a passive payload.

```text
IN SCOPE                          OUT OF SCOPE (deferred)
────────────────────────────────  ────────────────────────────────
stereo + GPS capture              flight control of any kind
on-board detection and tracking   autonomous navigation
3D points of detected objects,
  layered on RTAB-Map's static
  output; moving-object tracks
3D reconstruction                 path planning / obstacle avoidance
SAM segmentation                  mission orchestration / tasking
landmark detection                route replanning
semantic map building             V-JEPA
map export to base station        Raspberry Pi AI Camera (§2.4)
```

The drone is flown manually or by a separate, existing autopilot.
SurMap has no write path to any flight controller: no actuator, waypoint,
or velocity commands exist in any interface below.
RTAB-Map runs passively on-board: it estimates the camera trajectory so
point clouds can be registered into one map.
Its output is never fed back as a control signal.

## 2. Hardware

### 2.1 Machine 1 — on-board (on the drone)

- Raspberry Pi Compute Module 5 (CM5).
- Google Coral Edge TPU accelerator (user wording "TFU" = Edge TPU):
  runs the object detector. The CM5 CPU runs capture, tracking
  association, GPS logging, RTAB-Map, storage, and the uplink.
- Stereo camera: candidate is the ELP dual-lens USB module
  (global shutter, side-by-side UVC stream, MJPEG) — evaluated in
  [camera-elp-stereo.md](camera-elp-stereo.md), not yet committed.
  Its lens baseline is unpublished and must be measured before depth
  output is trusted.
- GPS receiver (model undecided), sharing the CM5 clock domain.

### 2.2 Machine 2 — base station

- ROS2 workstation with an NVIDIA RTX 5060 Ti.
- Runs SAM 3.1, stereo depth / point-cloud reconstruction, fusion, the
  semantic map builder, and the client that calls the LLM Models API.
- Consumes survey data only; issues no commands to the drone.

### 2.3 Machine 3 — simulation

- Purpose: develop and test the pipeline without flying — synthetic
  stereo pairs with known ground-truth geometry and GPS, plus replay of
  sessions recorded by machine 1.
- Contract: whatever this machine produces must be indistinguishable in
  format from a recorded real session (§5), so base-station code cannot
  tell simulation from flight data.
- **Local / WSL path (chosen):** Gazebo Harmonic + ROS 2 Jazzy + PX4
  SITL. Operators dump stereo + GPS into a SurMap capture directory;
  `surmap.simulation` exports a EuRoC-style session the demo and
  RTAB-Map sidecar already consume. SurMap stays passive — PX4 (or a
  human) flies; no package publishes flight commands. Runbook:
  [simulation/px4-sitl.md](simulation/px4-sitl.md). The demo world is a
  fictional civilian earthquake-and-flood block with scoring ground
  truth (map ENU and WGS84): [simulation/disaster-world.md](simulation/disaster-world.md).
- Other simulator options (Isaac Sim, a custom renderer, pure
  rosbag/session replay) and dedicated Machine 3 hardware remain open
  if a different path is needed later.

### 2.4 Optional hardware: Raspberry Pi AI Camera

Not in the baseline.
Rationale: the stereo rig already provides imagery, the Coral already
provides on-sensor-rate detection, and the AI Camera is monocular — it
would add no depth, is not calibrated to the stereo rig, and its
on-sensor inference would duplicate the Coral's job.
Reconsider only for a named need, e.g. an ultra-low-power wake/trigger
source or an independent nadir experiment camera.
No interface below may depend on it.

## 3. Model policy: Meta first

Rule: if Meta publishes a model that fits the job and the hardware,
use it. A non-Meta choice must name the gap it fills, here.

| Job | Model | Meta? | Notes |
|---|---|---|---|
| Segmentation + video tracking (base) | SAM 3.1 | Yes | §3.1 |
| Semantic labelling (API) | Meta Llama, newest available via the chosen Models API | Yes, preferred | §3.2 |
| Object detection (Edge TPU) | SSD MobileNet V2 or EfficientDet-Lite, Edge TPU-compiled `.tflite` | No | Meta publishes no Edge TPU detector; Coral requires Edge TPU-compiled TFLite. Final choice by CM5 benchmark |
| Object tracking (on-board) | Lightweight box tracker (Kalman / IoU association) over detector output | No | Classical algorithm, not a learned model. SAM 3.1 also tracks, but on the base station, after the fact / downstream |
| Pose and mapping | RTAB-Map | No | SLAM system, not a learned model; no Meta equivalent |
| Video representation | V-JEPA | Yes | Deferred entirely |

### 3.1 SAM 3.1 (base station, RTX 5060 Ti)

- SAM 3 (Meta, 2025-11-19) introduced Promptable Concept Segmentation:
  given a short noun phrase, an image exemplar, or both, it detects,
  segments, and tracks every matching instance in image or video, with
  stable identities, alongside the point/box/mask prompts of earlier SAMs.
- SAM 3.1 (Meta, 2026-03-27) is a drop-in replacement that adds object
  multiplexing — up to 16 objects tracked in one forward pass — roughly
  doubling video throughput.
- Sources: [Meta SAM 3 / 3.1 announcement](https://ai.meta.com/blog/segment-anything-model-3/),
  [SAM 3 paper page](https://ai.meta.com/research/publications/sam-3-segment-anything-with-concepts/),
  [facebook/sam3.1 checkpoint](https://huggingface.co/facebook/sam3.1).
- Fit to this project: concept prompts can come from the on-board
  detector's coarse labels (e.g. "car", "roof"), so the Coral's cheap
  detections steer SAM 3.1's expensive, precise segmentation, and SAM
  3.1's video identities give landmarks temporal consistency.
- RTX 5060 Ti sizing is unverified: Meta's throughput figures (32 fps
  video with multiplexing) are measured on an H100.
  Before committing, measure on the actual card: peak VRAM at the
  chosen resolution, images/second in per-image mode, frames/second in
  video mode, and the effect of keyframing (segment every Nth frame,
  track in between). The 8 GB vs 16 GB variant of the card changes this
  answer — record which one is installed.
- Fallback if 3.1 does not fit or run acceptably: SAM 3, then SAM 2,
  in that order; the fusion contract (§5) does not change.

### 3.2 LLM via Models API (semantic labelling)

- Called from the base station, once per candidate landmark (and again
  when a landmark gains substantial new observations).
- Input: object crop(s), SAM mask statistics, on-board coarse label,
  map position and GPS, neighbouring landmark labels.
- Output: canonical semantic label, short description, confidence,
  and optionally concept phrases to re-prompt SAM 3.1 with.
- Model choice: the newest Meta Llama model the chosen Models API
  offers at integration time. The API provider and exact model ID are
  open decisions; the exact model ID, provider, and prompt version are
  recorded on every `Landmark` (§5) so labels stay reproducible.
- Non-Meta fallback is permitted only if no Llama model on the API can
  consume the needed input (e.g. image crops) at acceptable cost/latency;
  that reason must be recorded here before use.
- The LLM labels what was observed. It makes no mission or flight
  decisions in this phase.

### 3.3 On-board detection and tracking (CM5 + Coral Edge TPU)

The TPU pipeline's job, end to end: **camera input in, labeled tracked
objects out — including moving ones.** It has three stages:

1. **Detect (Coral Edge TPU).** An Edge TPU-compiled detector from the
   Coral model zoo class (SSD MobileNet V2, EfficientDet-Lite family)
   runs on one camera channel (the left eye) and returns labeled boxes
   per frame. These are small, quantized, COCO-style detectors —
   coarse labels are expected and fine: precision comes later from
   SAM 3.1 and the LLM.
2. **Track (CM5 CPU).** Frame-to-frame association of detector boxes
   into stable track IDs. Output is `Track` records (§6). Tracks also
   select keyframes, name SAM 3.1 concept prompts, and suppress
   duplicate observations to the base station.
3. **Reconstruct object points (CM5 CPU, §4.1).** For each track, the
   Pi computes stereo depth only inside the tracked box (ROI stereo
   matching on the full stereo pair), producing that object's 3D
   points in camera frame, transformed into map frame with the
   RTAB-Map pose at the frame's timestamp.

**Static vs. moving.** RTAB-Map maps the static scene and assumes it
does not move. The TPU pipeline is therefore also the dynamic-object
source, with the opposite assumption:

- Each reconstructed object is classified per track: if its map-frame
  centroid stays consistent across observations (within depth/GPS
  noise) it is **static**; if it displaces in map frame after camera
  ego-motion is compensated by the RTAB-Map pose, it is **moving**.
- Static objects' points may accumulate into the object layer of the
  map (§6, `SemanticMap`).
- Moving objects' points are kept as timestamped per-observation
  snapshots along the track — never accumulated — so a moving car
  cannot smear a streak of points across the static map.
- Detected moving regions should also be masked out of the imagery
  fed to RTAB-Map where the integration allows it, so dynamic objects
  do not corrupt the static map or the pose estimate in the first
  place. If the RTAB-Map integration cannot accept masks, this is
  recorded as a known limitation, not silently skipped.

Everything on-board must keep running if the base station is absent:
detection, tracking, object reconstruction, RTAB-Map, and recording
are fully local.

## 4. Components

### 4.1 Machine 1 — on-board (Pi CM5)

| Component | Runs on | Responsibility |
|---|---|---|
| `capture` | CM5 CPU | Grab synchronized left/right frames; monotonic timestamp per pair |
| `gps` | CM5 CPU | GPS checkpoints on the same clock as frames |
| `detect` | Coral Edge TPU | Per-frame labeled object boxes from the left channel |
| `track` | CM5 CPU | Associate boxes into stable track IDs, static and moving objects alike |
| `reconstruct_object` | CM5 CPU | Stereo depth inside each tracked box → the object's 3D points, camera frame → map frame via the RTAB-Map pose at that timestamp |
| `classify_motion` | CM5 CPU | Per track: static vs moving, from map-frame displacement after ego-motion compensation (§3.3) |
| `rtabmap` | CM5 CPU | Passive trajectory + local pose graph + static-scene points. Provides pose and the static layer; never receives object points back into its internal map |
| `augment_map` | CM5 CPU | RTAB-Map output + object layers = the on-board map product: static objects accumulated, moving objects as timestamped track snapshots (§6) |
| `store` | CM5 CPU | Persist frames, calibration, GPS, tracks, object points, trajectory (survives link loss) |
| `uplink` | CM5 CPU | Stream when the link allows; otherwise store-and-forward |

### 4.2 Machine 2 — base station (ROS2, RTX 5060 Ti)

ROS2 nodes. Topic/service names are design intent, to be fixed at
implementation. Raw survey data enters either live or as an uploaded
session through the same messages.

| ROS2 node | Responsibility |
|---|---|
| `surmap_ingest` | Accept live stream or recorded session; persist raw data unchanged; publish frame pairs, GPS, tracks, trajectory |
| `surmap_depth` | Stereo matching → depth → point cloud, each point carrying source pixel `(u, v)` and `frame_id` |
| `surmap_sam` | SAM 3.1 (RTX 5060 Ti): segment/track one video channel; concept prompts from on-board coarse labels |
| `surmap_fuse` | Project SAM masks onto the point cloud using RTAB-Map poses → 3D object regions with full provenance |
| `surmap_landmarks` | Cluster fused regions into landmarks; call the LLM Models API for semantic labels |
| `surmap_map` | Merge landmarks + geometry into the semantic map; anchor to GPS; version and export snapshots |

One drone's footage at a time in this phase.
Multi-drone map merging is a later design problem.

### 4.3 Machine 3 — simulation

Produces synthetic `StereoFramePair` + `GpsCheckpoint` + ground-truth
sessions in exactly the §5 formats, and replays real sessions.
No other component may have a simulation-only code path.

On the Gazebo/PX4 SITL path, the offline bridge is
`surmap.simulation` (capture directory → EuRoC `mav0/` + GPS CSV) plus
operator-side dump tooling under `scripts/ros2/` — not a live ROS 2
dependency inside SurMap packages. The disaster-block world adds
scoring ground truth (people and roads, map frame and WGS84) that a
demo can compare with detections. Loading that file does not command
the vehicle.

## 5. Data flow

```text
Machine 1 (CM5 + Coral):
  stereo pair ──┬──► rtabmap ─► pose + static-scene points
                ├──► detect (Edge TPU, left channel) ─► track
                │      ─► reconstruct_object (stereo depth in box,
                │         posed by RTAB-Map) ─► classify_motion
                │      ─► augment_map: RTAB-Map output + object points
                │         (static accumulated, moving as snapshots)
                ├──► store (always)
  GPS fix ──────┘
                └──► uplink ──► Machine 2: surmap_ingest
                     (live if link allows, else after landing)

Machine 2 (ROS2):
  ingest ─► depth ─► full point cloud (point ↔ pixel ↔ frame_id)
         ─► surmap_sam (SAM 3.1, concept prompts from on-board labels)
         ─► fuse (masks × cloud × RTAB-Map pose; refines the on-board
            box-based object points with true mask boundaries)
         ─► landmarks ─► LLM via Models API (semantic labels)
         ─► semantic map (GPS-anchored, incrementally updated)
```

SAM 3.1 runs on one channel only.
The second channel exists for depth; segmentation does not need it.

## 6. Data contracts

Language-neutral shapes; Python dataclasses / JSON / ROS2 messages at
implementation time.
All timestamps are monotonic-clock nanoseconds on the CM5, plus a UTC
wall-clock anchor recorded once per session.

### `StereoFramePair`

- `frame_id`, `t_ns`
- `left`, `right`: image references (not embedded blobs in metadata)
- `calibration_id`: which stereo calibration produced this pair

### `GpsCheckpoint`

- `t_ns`, `lat`, `lon`, `alt`, `accuracy_m`
- Recorded at a fixed rate and on demand; frames interpolate between fixes

### `Detection` / `Track` (on-board)

- `Detection`: `frame_id`, box, coarse label, score, detector model ID
- `Track`: `track_id`, list of `Detection` references, first/last seen
- Track IDs are on-board-local; SAM 3.1 video identities are base-local.
  `surmap_fuse` records the mapping between them, never assumes equality

### `ObjectPoints` (on-board, per track per observation)

- `track_id`, `frame_id`, `t_ns`
- Points in map frame (camera-frame stereo points transformed by the
  RTAB-Map pose at `t_ns`), each point retaining its source pixel
- Centroid in map frame, point count, mean depth uncertainty
- Box-based points are coarse: the box includes background at the
  object's edges. Base-station SAM masks refine this (§5); on-board
  consumers must treat edge points as suspect

### `ObjectTrack3D` (on-board, per track)

- `track_id`, coarse label, list of `ObjectPoints` observations
- `motion`: `static` | `moving` | `unknown` (too few observations),
  with the displacement and threshold that decided it
- Moving tracks also carry centroid velocity in map frame, if the
  observation rate supports estimating it

### `PointCloud`

- `frame_id`, `t_ns`
- Per point: `xyz` in camera frame, `u`, `v`, source `frame_id`
- The point ↔ pixel link is mandatory: it is what lets a 2D SAM mask
  claim a set of 3D points

### `Segment`

- `frame_id`, `mask_id`, mask reference, SAM score
- Prompt that produced it (concept phrase / exemplar / box) and whether
  that prompt came from an on-board coarse label

### `Landmark`

- `landmark_id`, centroid `xyz` in map frame, `lat`/`lon`/`alt`
- Contributing `mask_id`s, `frame_id`s, and `track_id`s (full provenance)
- `label`, `description`, `confidence` — plus LLM provider, exact model
  ID, and prompt version that produced them
- `first_seen_ns`, `last_seen_ns`, `observation_count`

### `SemanticMap`

Layered — the layers are never merged into one undifferentiated cloud:

1. **Static layer**: RTAB-Map's static-scene points.
2. **Static object layer**: accumulated `ObjectPoints` of tracks
   classified static, refined by SAM masks on the base station,
   promoted to `Landmark`s.
3. **Dynamic layer**: `ObjectTrack3D`s classified moving, as
   timestamped snapshots with track IDs — queryable history,
   excluded from layers 1–2 by construction.

- "Adding object points to RTAB-Map's output" means layers 2–3 are
  added to the output product (`augment_map` on-board, `surmap_map`
  on the base). Object points are never written back into RTAB-Map's
  internal map or pose graph.
- Versioned snapshot: layer references + list of `Landmark`s.
- Anchored to GPS; internal coordinates in a local ENU frame with a
  recorded WGS84 origin.
- Exportable as a file; consumers never mutate it in place.

## 7. Coordinate frames and sync

- `camera`: per-frame stereo reconstruction.
- `map`: local ENU frame built from the on-board RTAB-Map trajectory.
- `world`: WGS84, reached via GPS checkpoints and the map origin.
- Frame ↔ GPS association is by timestamp interpolation only.
  No GPS reading is ever snapped to a frame without recording the offset.
- Stereo calibration is per-camera-rig, versioned as `calibration_id`,
  and stored with every session.

Known accuracy limit: consumer GPS (metres) is far coarser than stereo
geometry (centimetres at short range).
The map keeps both: precise relative geometry, approximate absolute anchor.
Landmarks therefore store map-frame position and GPS position separately.

## 8. Live vs. store-and-forward

Decided by measured link bandwidth, which is still unknown.

- Default assumption: record everything on-board, stream a reduced
  keyframe feed live if possible, process the full session on the base
  station after landing.
- Live semantic mapping is a stretch goal, not a requirement of this phase.
- No component may assume a live link: `surmap_ingest` accepts a live
  stream and an uploaded session through the same contract.
- On-board detection/tracking runs regardless of link state; only
  SAM 3.1, fusion, and LLM labelling wait for the base station.

## 9. Failure modes

| Failure | Behaviour |
|---|---|
| Link lost mid-flight | Keep recording on-board; forward when link returns |
| Coral Edge TPU unavailable | Keep capturing + RTAB-Map + recording; detection resumes when the TPU is back — never block capture on inference |
| GPS lost / degraded | Keep building relative geometry; flag landmarks as unanchored until a fix resumes |
| Stereo calibration invalid | Reject the session at `surmap_ingest` with the `calibration_id` named |
| SAM 3.1 / LLM API unavailable | Map still builds geometrically; segmentation and semantics are backfilled later — raw data is never discarded |
| RTAB-Map pose lost / not yet initialised | Keep detecting and recording; object points stay in camera frame and are marked unposed — never placed in the map with a guessed pose |
| Track fragmented (ID switch) after occlusion | Base-station SAM 3.1 identities and LLM labels may re-link fragments; on-board never merges two tracks on a guess |
| CM5 storage full | Drop live streaming first, keep recording at reduced keyframe rate, never corrupt already-written sessions |
| RTX 5060 Ti out of memory in SAM 3.1 | Reduce input resolution / keyframe rate, then fall back per §3.1; log the configuration that failed |

## 10. Interfaces to expose

- **Board API** (machine 1): session start/stop, capture/detection/RTAB-Map
  status, storage and link status, session download.
  Payload control only — nothing flight-related.
- **GPU API** (machine 2): submit a session or stream for processing,
  query job status, fetch the resulting `SemanticMap`.
  Internally this fronts the ROS2 graph in §4.2.
  Mantas owns exposing both APIs.

Both APIs are payload/data APIs.
Adding any flight-command endpoint would be a scope change, not an extension.

The wire contract for both is `surmap.survey.v1`
(`proto/surmap/survey/v1/survey.proto`): two bidirectional ConnectRPC
streams with the same input — a config message (stereo calibration,
plus what the requester wants) followed by raw per-channel video frames.
`Cm5SurveyService` (Board API) answers with designated point batches
and requested video channels; `StationSamService` (GPU API) answers
with SAM detection vectors keyed by the requester-assigned `frame_id`.
Outputs are told apart by an int32 designation: `1` is the RTAB-Map
static scene, `2`/`3` are video channels 0/1, and `100 + track_id`
groups one tracked object's points. The Board API is served by
`Cm5SurveyService.StreamSurvey` (`surmap.survey.cm5_server`): completed
stereo pairs drive the `SlamBackend` port and an object-point source,
and their points are streamed incrementally — spawned only, never
resent at a position already sent. Scene points are reconstructed
from the pair's own frames by `surmap.survey.stereo` (decode,
principal-point alignment, block matching, back-projection —
numpy/Pillow, no native dependency), then placed in the map frame
with the SLAM pose — alongside the video channels the
requester asked to see. The GPU API is served by
`StationSamService.StreamAnalysis` (`surmap.survey.station_server`):
the same frames in, SAM detection vectors out, each repeating the
requester-assigned `frame_id`; the stream's analysis mode decides
whether frames queue (lag) or drop while the detector is busy. Both
servers run as processes (`python -m surmap.survey.cm5_main`,
`python -m surmap.survey.station_main`) and deploy over SSH as systemd
services — see `docs/deployment.md`. They serve their in-memory
adapters until the hardware adapters (RTAB-Map, Coral, SAM 3.1) land
behind the existing ports.

## 11. Deferred, explicitly

Revisit only after the passive pipeline works end to end on real footage:

1. Autonomous navigation and SLAM-based steering (RTAB-Map in the loop).
2. Flight-controller integration of any kind.
3. Base-station orchestration: tasking drones, replanning routes from
   the semantic map, closing the observe → decide → fly loop.
4. Multi-drone concurrent survey and map merging.
5. V-JEPA or other learned video representations for landmark detection.
6. LLM mission-level decision-making (the LLM here only labels what
   was observed).
7. Raspberry Pi AI Camera integration (§2.4).

## 12. Open decisions

- Stereo camera: ELP candidate — bench-test gate and calibration
  procedure in [camera-elp-stereo.md](camera-elp-stereo.md).
  Includes the unpublished-baseline problem; survey altitude envelope
  follows from its measured depth range.
- Edge TPU detector choice (SSD MobileNet V2 vs. EfficientDet-Lite)
  and tracker algorithm — by CM5 + Coral benchmark on real footage.
- SAM 3.1 on the RTX 5060 Ti: installed VRAM variant (8 vs 16 GB),
  measured throughput/VRAM, input resolution, keyframe rate,
  video-mode vs per-image mode.
- Models API provider; exact Meta Llama model ID; whether image crops
  are sent; labelling cost/latency budget per session.
- Link drone ↔ base station (Wi-Fi / LTE / other) and its bandwidth.
- Simulation machine: Gazebo Harmonic + PX4 SITL is the local/WSL
  Machine 3 path (§2.3); dedicated hardware and alternate simulators
  (Isaac Sim, custom renderer, pure replay) still open if needed.
- GPS receiver model; GPS checkpoint rate and sync procedure.
- Depth: object-ROI depth is on-board by design (§3.3); whether full-frame
  depth is also computed on the CM5 or only on the base station depends
  on link and CM5 load (§8).
- Motion classification: displacement threshold and minimum observation
  count for `static` vs `moving`, by bench test on recorded footage.
  Misclassifying a parked car as moving (or a slow vehicle as static)
  is the expected early failure mode.
- Whether RTAB-Map integration can consume dynamic-object masks (§3.3).
- Map export format (GeoJSON-flavoured JSON is the current leaning,
  unconfirmed).
