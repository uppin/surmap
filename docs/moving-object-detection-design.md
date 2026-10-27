# Moving-object detection on-board — design

Status: design (not yet implemented). This document states the
problem, then gives a step-by-step solution sized for the CM5 edge
device that is *also* running RTAB-Map: compute, memory, and the
Coral Edge TPU are all shared, and nothing in this design may starve
the static-mapping pipeline that is the product's primary output.

Related: [architecture.md](architecture.md) §3.3 (on-board detection
and tracking), §6 (data contracts); the implemented seams this design
builds on are `surmap.detection` (Coral detector + IoU tracker),
`surmap.survey.stereo` (stereo reconstruction), `surmap.slam`
(RTAB-Map sidecar), and `surmap.motion` (static/moving
classification).

## 1. Problem statement

RTAB-Map gives us the static world: a camera trajectory and a
point cloud of the scene that does not move. A survey product also
needs the opposite layer — the things that *did* move while the
drone flew over: vehicles driving through, people walking, a hand
reaching into frame. Those moving objects must be detected,
bounded, tracked over time, and represented in 3D, *without* their
points ever contaminating the static map (a moving car accumulated
into the static layer smears a streak of points across it) and
without degrading RTAB-Map's pose estimate, which everything else
is registered against.

Three properties make this hard on our hardware specifically:

1. **The compute is already spent.** The CM5 (quad Cortex-A76)
   concurrently runs capture, RTAB-Map, the uplink/storage, and the
   survey server. Detection must live in the margins: the Coral
   Edge TPU for neural work, and small, bounded CPU slices for
   geometry. Any stage whose cost scales with total scene points or
   runs per-pixel dense algorithms on CPU is disqualified on-board.
2. **Poses arrive late.** Our RTAB-Map integration is a batch
   sidecar: optimized poses and the static cloud exist only after a
   segment finishes, and only at keyframes. Map-frame placement of
   a moving object at *its* timestamp therefore cannot happen in
   the moment; it must be reconstructed afterwards from buffered,
   timestamped camera-frame evidence.
3. **"Moving" is not a visual category.** A COCO detector finds
   cars and people whether or not they move, and misses the
   sliding crate entirely. Conversely the most common outdoor
   motion — wind-blown vegetation — is motion with no mover:
   high local movement, zero net displacement, nothing that should
   become an object in the map. The design must separate *where
   change happens* from *what it means*, and must not let the
   second question contaminate the first.

### Goals

- Detect moving *areas* on-board, bounded by a 2D polygon, with a
  depth range and a dynamic point count, in near-real time (same
  order of latency as the detection stream: seconds, not minutes).
- Track areas across frames and classify each area track:
  rigid mover / oscillating or deformable background / static
  false alarm — using motion statistics, not labels.
- For areas classified as rigid movers, emit a sparse set of 3D
  keypoints per observation (not a dense cloud: a moving object's
  dense points are stale immediately, cost bandwidth and storage,
  and add nothing over identifiable, re-findable points), lifted
  into the map frame once poses exist, under the object's existing
  wire designation (`100 + track_id`).
- Keep the static pipeline pristine: moving-area evidence is
  produced *alongside* RTAB-Map, never fed back into its internal
  map; and if resources saturate, this feature degrades first
  (see §5), never RTAB-Map.

### Non-goals

- Real-time map-frame moving clouds on-board (impossible with
  batch poses; see §4 step 6 for the retrospective mechanism).
- Dense per-pixel scene flow or learned motion segmentation
  on-board (station-class compute; §7 covers the station's role).
- New wire types in the first implementation: moving areas are an
  internal representation; only graduated objects cross the wire,
  as today's `ObjectPoints`.

## 2. Constraints and resource budget

Target device: Raspberry Pi CM5, quad Cortex-A76 @ 2.4 GHz, Coral
Edge TPU (M.2), RTAB-Map sidecar container running concurrently.
Working resolutions and rates are the demo-proven ones: frames at
376×240 for analysis (native 752×480 retained in recordings),
detector input 320×320 on the TPU.

| Resource | Budget for this feature | Rationale |
|---|---|---|
| CPU | ≤ 1 core sustained, ≤ 25% of the SoC | RTAB-Map + capture + server own the rest |
| RAM | ≤ 256 MB working set | Point buffers are ring-bounded (§4) |
| Edge TPU | Shared with the survey detector; area stage adds no TPU work | Detector already runs there |
| Latency | Area verdict within ≤ 2 s of segment end | Retrospective by design (§1) |
| Frame budget | Analysis at 5 Hz max, decimated from the 20 Hz stream | Motion statistics need ~1–3 s windows |

Hard rules that follow from the budget:

- **No dense CPU geometry.** No per-pixel flow, no full-cloud
  clustering at native resolution. All geometry works on the
  half-resolution stereo points (≤ ~20 k/frame worst case,
  stride-sampled to ≤ 4 k before any spatial index is built).
- **Everything is windowed.** Tracks, buffers, and statistics live
  in sliding windows (default 3 s); nothing accumulates for a
  whole flight on-board.
- **Every stage is droppable.** Each stage consumes the previous
  stage's output only if the pipeline is keeping up; the survey's
  own `BEST_EFFORT_DROP` discipline applies internally too.

## 3. Solution overview

Motion first, semantics second — three stages, each bounded by the
previous one:

```text
stereo pairs ──► [1 static differencing] ──► dynamic candidate points
                        │                            │
RTAB static cloud ──────┘                            ▼
                                  [2 moving areas]  polygons + area tracks
                                                     │  (only compact,
                                                     │   coherent, travelling
                                                     │   areas graduate)
                                                     ▼
                                  [3 per-area analysis]  label? landmarks?
                                                     │   keypoints, verdict
                                                     ▼
                                  moving-object keypoint snapshots
                                  (map frame, after poses land)
```

Stage 1 knows only *where change is*. Stage 2 knows *how it
behaves over time*. Stage 3 spends real compute — inside a few
polygons only — to say *what it is* and to extract its keypoints.
A failure in an early stage produces ragged areas, not phantom
objects: nothing reaches the map product without passing all three.

## 4. Step by step

### Step 0 — Inputs already on the device (no new work)

Per stereo pair, the running system already produces: the Coral
detector's boxes with track IDs (survey detections stream), the
half-resolution stereo scene points (`StereoReconstructor`), and —
at segment end — RTAB-Map's keyframe poses and static cloud. This
design consumes those; it adds no new sensor or model.

### Step 1 — Static-map differencing → dynamic candidate points

Maintain an **accumulated static layer** on-board: a voxel-hash set
(voxel 0.05 m) of map-frame points that have been observed as
static. It is seeded from RTAB-Map's exported cloud at each flush
and extended between flushes by stereo points that agree with it
(a point landing in an occupied voxel, observed in ≥ 3 distinct
frames, joins the layer). RTAB's sparse keyframe cloud alone is
*not* a sufficient reference — it never mapped most surfaces, and
"absent from RTAB's cloud" would flag the whole world as moving.

For each analyzed frame (5 Hz):

1. Transform the frame's stride-sampled stereo points (≤ 4 k) into
   the map frame using the best pose available at runtime
   (last keyframe pose held, or frame-to-frame visual odometry
   increment; refined retrospectively in step 6).
2. A point is a **dynamic candidate** if its nearest static-layer
   voxel distance exceeds a noise-scaled threshold
   `τ(Z) = τ₀ + k·Z²/(f·B)` — stereo depth error grows
   quadratically with range, so the threshold must too.
3. Candidates must persist: a voxel receiving candidates in ≥ 2 of
   the last 3 analyzed frames is *hot*. Persistence kills depth
   noise and single-frame stereo artifacts at almost no cost.

Cost: one voxel-hash lookup per sampled point — O(1), ~4 k lookups
per analyzed frame. Memory: the static layer is capped (LRU voxel
eviction outside a radius around the current pose).

### Step 2 — Moving areas: mask → polygon → area tracks

1. Project hot voxels back into the current image; rasterize a
   binary motion mask at analysis resolution (376×240).
2. Clean the mask: drop connected components smaller than
   `min_area_px` (default 150 px), fill holes by keeping each
   component's filled contour.
3. Trace each component's contour and simplify with
   Douglas–Peucker (ε ≈ 2 px) → the area's **polygon**
   (≤ 64 vertices). The polygon lives in 2D image space — where
   contours are natural — with a depth range `[Z_min, Z_max]` and
   dynamic point count carried alongside, not a 3D hull.
4. Emit `MovingArea { frame_id, t_ns, polygon, depth_range,
   point_count }` internally, and associate areas across frames
   into **area tracks** by mask IoU (≥ 0.2) or centroid distance,
   reusing the IoU association discipline of the existing box
   tracker. Area IDs are internal and never reused within a
   segment.

Per area track, accumulate the motion statistics that stage 3
decides on (all cheap, all per-area, updated incrementally):

- **net / path ratio**: net centroid displacement in map frame
  divided by the total path length travelled. ≈ 1 → travelling;
  ≈ 0 with long path → oscillation (windy vegetation, flags).
- **velocity coherence**: fraction of the area's dynamic points
  whose implied velocity agrees (within tolerance) with the area's
  median velocity. Rigid movers are coherent; foliage is not.
- **area stability**: polygon area variance; rigid movers change
  slowly, deformables and vegetation flicker.

### Step 3 — Area classification (the verdict)

An area track is classified once it has ≥ 5 observations spanning
≥ 1 s, and re-evaluated as evidence accrues:

| Evidence | Verdict |
|---|---|
| net/path ≥ 0.6, coherence ≥ 0.6, net displacement ≥ 0.5 m | **rigid mover** → stage 4 |
| net/path ≤ 0.25 with path ≥ 0.5 m, or coherence ≤ 0.35 | **oscillating background** → mark region low-confidence, stop |
| too few observations, contradictory evidence | **unknown** → keep tracking, emit nothing |

Thresholds are starting values to be tuned on recorded data (§6),
not constants of nature; they live in one config object next to
`classify_motion`'s existing threshold, and the track-level verdict
feeds `surmap.motion.classify_motion` (extended, not replaced: its
centroid-displacement test becomes one input among these).

### Step 4 — Per-area analysis (only for rigid movers)

Compute follows attention: this stage runs on at most a handful of
polygons, cropped regions only.

1. **Label (optional, cheap):** overlap the polygon with the Coral
   detector's tracked boxes for the same frame. IoU ≥ 0.4 adopts
   the box's label and — importantly — its existing `track_id`, so
   the moving object keeps the identity the survey stream already
   publishes. No overlap → label stays `unknown`; the object is
   still real (the sliding-crate case).
2. **Keypoints.** Two kinds, in priority order:
   - *Detector-supported:* the stereo points inside the polygon
     whose depth belongs to the polygon's near depth cluster
     (histogram peak within the area's depth range) — this removes
     the background wall behind the object that a raw box includes.
   - *Geometric selection:* from those points, farthest-point
     sampling to ≤ 16 keypoints plus the PCA principal-axis
     endpoints, giving even coverage and the object's extent.
     Human-specific landmark models (hand/body pose) are
     station-class compute and are *not* run on-board; the station
     refines person tracks to skeletal keypoints downstream (§7).
3. **Smoothing:** keypoint positions pass a One Euro filter in
   image space before lifting (heavy smoothing at rest, minimal
   during fast motion — the standard cure for landmark jitter on
   volatile movers like hands), then a light constant-velocity
   Kalman filter per keypoint in camera frame. When depth at a
   keypoint is missing, sample the median disparity in a 5×5
   window around its pixel; if still missing, the keypoint is
   held from prediction for ≤ 3 frames, then dropped.

### Step 5 — Buffering (the edge-device discipline)

Per graduated area track, buffer a ring of observations:
`{ t_ns, camera-frame keypoints (≤ 18 × Vec3), centroid,
velocity }` — a few hundred bytes per observation, 3 s window,
hard cap per track and globally. This buffer is the *only* state
stage 6 needs; raw frames and dense points are never retained for
this feature. The buffer is also the degradation valve: under CPU
or memory pressure it shrinks first (§5).

### Step 6 — Retrospective map-frame placement

When the RTAB-Map sidecar flushes at segment end (the only moment
optimized poses exist):

1. Interpolate the pose at each buffered observation's `t_ns`
   between the bracketing keyframe poses (linear translation,
   slerp rotation).
2. Transform the buffered camera-frame keypoints into the map
   frame; recompute the track verdict with these refined positions
   (the runtime verdict used held poses; the published verdict
   must not).
3. Emit one `ObjectPoints` snapshot per observation — sparse
   keypoints, existing type, existing designation
   (`100 + track_id` from step 4.1 when a detector identity was
   adopted; otherwise a track ID allocated in the same space).
   Moving objects are emitted as timestamped snapshots, never
   accumulated, exactly as the architecture already requires.
4. Seed/refresh the accumulated static layer from the new RTAB
   cloud (step 1), and drop buffered evidence older than the
   segment.

### Step 7 — Publication

Snapshots join the survey stream's object batches at flush time,
through the same emitter and dedup as today's object points. The
station receives nothing new to understand; its SAM 3.1 refinement
(person landmarks, mask-exact boundaries) layers onto these tracks
downstream.

## 5. Resource governance (living next to RTAB-Map)

RTAB-Map is the primary product; this feature is a tenant. The
sidecar runs as a separate container invoked at segment boundaries,
so the contention points are CPU during its run, and memory
throughout.

- **Scheduling.** Stages 1–4 run in one worker thread at nice
  priority below capture and the survey server, pinned away from
  the core RTAB-Map prefers during a flush when core affinity is
  configurable. Analysis cadence is 5 Hz by decimating the frame
  stream, not by processing bursts late: a frame that misses its
  slot is dropped, never queued (the `AnalysisGate` discipline).
- **Flush blackout.** While the sidecar container runs (seconds),
  stages 1–4 pause; buffering (step 5) is the only activity, and
  it is bounded. The retrospective step 6 runs *after* the flush
  returns, inside the existing flush handling.
- **Budgets enforced, not hoped for.** Per-stage counters (points
  sampled, areas live, buffered observations, ms per stage per
  second) are the same metrics the demo already surfaces; the
  global caps in §2 are hard: exceeding the area cap keeps the
  largest areas; exceeding the buffer cap drops the oldest
  observations of the least-coherent tracks first.
- **Degradation order.** Under sustained over-budget: (1) analysis
  cadence 5 Hz → 2 Hz; (2) keypoint count 16 → 8; (3) stage 4
  restricted to detector-labelled areas; (4) feature off,
  areas still logged for offline analysis. The static pipeline is
  never in the list.

## 6. Evaluation plan

Thresholds in step 3 are hypotheses until measured on recorded
data with known answers:

- **Negative control — EuRoC V1_01 (already cached):** static
  room, moving camera. Every graduated area is a false positive.
  Target: zero rigid-mover verdicts over the full sequence; total
  dynamic-area coverage < 1% of frames.
- **Oscillation control — windy vegetation footage** (to add to
  the dataset registry): target: areas found, none graduated;
  net/path and coherence shown to be the deciding statistics.
- **Positive control — a stereo sequence with real vehicles /
  pedestrians** (KITTI tracking subset is the natural registry
  addition): target: ≥ 90% of annotated mover-seconds graduated
  with the correct detector track identity where one exists;
  keypoint snapshots within the object's true extent (checked
  against box/mask annotations).
- **Resource gate:** the CM5-profile run (4-core container limits
  approximating the CM5, RTAB sidecar active) stays within §2
  budgets for a full EuRoC replay.

Each control becomes an E2E in the established pattern (recorded
data in, semantic assertions out, everything torn down).

## 7. What the station adds later (out of scope here)

The base station (RTX GPU) can afford what the CM5 cannot: SAM 3.1
mask-exact area boundaries, human pose landmarks (21-joint hands,
body pose) for person tracks, learned keypoint descriptors
(XFeat/SuperPoint class) for occlusion-proof identity, and dense
scene-flow validation of on-board verdicts. All of it consumes
this design's area tracks and snapshots unchanged; none of it is
required for the on-board layer to be correct, only richer.

## 8. Open questions

1. **Runtime pose quality.** Step 1 transforms with a held
   keyframe pose between flushes; if segment length grows, drift
   in that held pose inflates dynamic candidates. Is a lightweight
   frame-to-frame odometry increment needed on-board, or are
   segment lengths short enough? Measured by the EuRoC control.
2. **Masking RTAB-Map's input.** Excluding dynamic areas from the
   imagery RTAB-Map consumes would improve its poses in busy
   scenes, but the dataset-tool sidecar cannot accept masks
   (architecture §3.3 already records this). Revisit only if a
   future RTAB integration exposes it; never silently assumed.
3. **First-segment cold start.** Before the first flush there is
   no RTAB seed; the static layer must bootstrap from stereo
   self-agreement alone (≥ 3-frame persistence). Acceptable, but
   the first segment's areas carry lower confidence by
   construction and are labelled as such internally.
4. **Threshold ownership.** The step-3 thresholds and §2 budgets
   need one config home (`surmap.motion` alongside
   `classify_motion`'s) and one tuning record from §6's controls
   before they are treated as settled.

## 9. Implementation phasing (for the changeset plan)

1. **Differencing + areas (steps 1–2)** with unit tests on
   synthetic clouds and the EuRoC negative control E2E. No wire
   change, nothing published yet — areas observable in tests/logs.
2. **Classification + keypoints + buffering (steps 3–5)** with
   tracker-statistic unit tests and the oscillation control.
3. **Retrospective placement + publication (steps 6–7)** wired
   into the sidecar flush and the survey stream, proven by the
   positive-control E2E asserting real moving-object keypoint
   snapshots under existing designations.
4. **Resource governance (§5)** counters, caps, and the CM5-profile
   resource gate, before this is enabled by default on-board.
