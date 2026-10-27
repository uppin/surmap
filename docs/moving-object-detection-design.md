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
bounded, tracked over time, and represented in 3D — and they must
not smear into the static product (a moving car accumulated into
a static layer is a streak of points across it) nor degrade
RTAB-Map's pose estimate, which everything else is registered
against.

**Scope honesty.** This design's own outputs are clean by
construction: the on-board static layer (§4 step 1) is built
under the dwell test, and moving objects are emitted only as
separate keypoint snapshots, never accumulated into it. What this
design does *not* by itself guarantee is RTAB-Map's exported
cloud: RTAB-Map has no dynamic-object filtering of its dense
output (its occupancy grid can ray-trace movers away, but the
exported `cloud_map` does not), and this design feeds nothing
back into RTAB-Map — so a mover's streak can still appear in
RTAB's cloud, which is the primary product. Closing that gap is
recorded as a concrete follow-up, not assumed away: the sidecar
replays recorded segments at flush time, by which point the
whole segment's stage-2 polygons exist; persisting per-frame
polygons (a few hundred bytes each) lets the replay pre-zero
depth at dynamic pixels before RTAB-Map sees the frames — with
the default `Vis/DepthAsMask=true`, features and dense points
are simply not extracted there, which is exactly how DOTMask
cleans RTAB-Map output with detector masks (and it improves
RTAB's poses in busy scenes as a side effect). The "sidecar
cannot accept masks" limitation is a property of our wrapper,
not of RTAB-Map; wiring polygon-masked replay is a follow-up
changeset, and until it lands, static-cloud cleanup of mover
streaks stays with the station.

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
  and add nothing over tracked samples of the object's extent —
  on-board keypoints have short-horizon LK identity, not semantic
  re-identifiability; §4 step 4 is precise about this), lifted
  into the map frame once poses exist, under the object's existing
  wire designation (`100 + track_id`).
- Keep this feature's own outputs pristine and the static
  pipeline untouched: moving-area evidence is produced
  *alongside* RTAB-Map, never fed back into its internal map
  (the depth-zeroing replay above is the deliberate, separately
  reviewed exception); and if resources saturate, this feature
  degrades first (see §5), never RTAB-Map.

### Non-goals

- Real-time map-frame moving clouds on-board (impossible with
  batch poses; see §4 step 6 for the retrospective mechanism).
- Dense per-pixel scene flow or learned motion segmentation
  on-board (station-class compute; §7 covers the station's role).
- Attaching moving areas to survey or detection output frames.
  The area pipeline runs at its own, slower cadence and may lag
  arbitrarily behind both; areas travel on their **own stream**
  (§4, wire contract), keyed by `frame_id`, never embedded in
  another stream's messages.

## 2. Constraints and resource budget

Target device: Raspberry Pi CM5, quad Cortex-A76 @ 2.4 GHz, Coral
Edge TPU (M.2), RTAB-Map sidecar container running concurrently.
Working resolutions and rates are the demo-proven ones: frames at
376×240 for analysis (native 752×480 retained in recordings),
detector input 320×320 on the TPU.

| Resource | Budget for this feature | Rationale |
|---|---|---|
| CPU | ≤ 1 core sustained, ≤ 25% of the SoC | RTAB-Map + capture + server own the rest |
| RAM | ≤ 256 MB working set | Static layer capped at 2 M voxels + eviction radius (§4); buffers ring-bounded; a layer-memory counter enforces it (§5) |
| Edge TPU | Shared with the survey detector; area stage adds no TPU work | Detector already runs there |
| Latency | Live areas ≤ 1 s after their frame; snapshots ≤ 2 s **after the flush returns** | The 2 s bounds post-flush placement + publication only — it cannot include the multi-second flush itself |
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
previous one. The whole pipeline feeds one dedicated wire stream,
`Cm5SurveyService.StreamMovingAreas`, separate from both
`StreamSurvey` (RTAB-Map's cadence) and `StreamDetections` (the
detector's cadence): the area pipeline is slower than either and
must never back-pressure them. Every message on it carries the
`frame_id` (and `t_ns`) of the frame it was computed from, so a
client joins areas to frames, detections, and poses after the
fact — lag is expected and visible, never hidden.

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

One property worth stating plainly: stage 1 differences *depth
geometry* against a 3D reference, so it is inherently immune to
the illumination and shadow failures that plague
appearance-based background subtraction on aerial footage — a
moving shadow changes pixels, not point-to-layer distance, and
never becomes a candidate.

## 4. Step by step

### Step 0 — Inputs already on the device (no new work)

Per stereo pair, the running system already produces: the Coral
detector's boxes with track IDs (survey detections stream), the
half-resolution stereo scene points (`StereoReconstructor`), and —
at segment end — RTAB-Map's keyframe poses and static cloud. This
design consumes those; it adds no new sensor or model.

### Step 1 — Static-map differencing → dynamic candidate points

Maintain an **accumulated static layer** on-board: a voxel-hash
of map-frame points that have been observed as static, with
log-odds occupancy (OctoMap-style, with decay) rather than a
binary "joined forever" set (§8 references). The layer is seeded
from RTAB-Map's exported cloud at each flush; between flushes, a
stereo point updates its voxel's log-odds only under the
**dwell test** below. RTAB's sparse keyframe cloud alone is *not*
a sufficient reference — it never mapped most surfaces, and
"absent from RTAB's cloud" would flag the whole world as moving.

For each analyzed frame (5 Hz):

1. Transform the frame's stride-sampled stereo points (≤ 4 k) into
   the map frame using the best pose available at runtime
   (last keyframe pose held, or frame-to-frame visual odometry
   increment; refined retrospectively in step 6).
2. A point is a **dynamic candidate** if its nearest static-layer
   voxel distance exceeds a noise-scaled threshold
   `τ(Z, θ̂) = τ₀ + k·Z²/(f·B) + k_r·θ̂·Z` — stereo depth error
   grows quadratically with range, *and* a held-pose rotation
   error `θ̂` maps to lateral world error `θ̂·Z` on the orthogonal
   axis. `θ̂` is a runtime drift estimate (visual-odometry
   correction magnitude at the last flush, decaying between
   flushes; open question 1 owns measuring it). A threshold that
   models only stereo error will flag depth edges wholesale
   during drift bursts.
3. Form **candidate clusters** by connected components over the
   candidates (image-space connectivity on their projections).
   Noise is filtered at the *cluster* level — a cluster needs
   ≥ `min_cluster_points` (default 30) points — **never by
   per-voxel recurrence**. A per-voxel "seen in ≥ 2 of last 3
   frames" test is a speed filter that inverts the intended
   semantics: at 5 Hz a car at 15 m/s moves 3 m per analyzed
   frame (60× the 0.05 m voxel; a 4.5 m car occupies a voxel for
   ~1.5 frames), so fast movers produce zero recurrent voxels
   while slow drift artifacts recur happily. Persistence lives
   in stage 2 instead: area-track association (IoU/centroid) is
   motion-tolerant in a way voxel recurrence is not.
   The mirror rule guards static-layer absorption: a stereo point
   raises its voxel's static log-odds **only if it is slow** —
   its image-space displacement since the previous analyzed frame
   is below the velocity gate (i.e., it plausibly dwells). A
   slow walker otherwise overlaps each voxel for ~2–3 frames and
   is absorbed into the static layer, after which their mask
   flickers as voxels alternately absorb and release them. With
   log-odds decay, absorbed ghosts also expire instead of
   haunting the layer for the segment.

Cost: one voxel-hash lookup per sampled point — O(1), ~4 k lookups
per analyzed frame. Memory: the static layer is hard-capped at
**2 M voxels** (≈ 64–128 MB at realistic voxel-hash cost, counted
by a layer-memory counter in §5), with **LRU eviction outside a
40 m radius** around the current pose; the cap and radius are
config, and hitting the cap evicts farthest-first, never silently
grows.

**As built (2026-10-27, n3).** `surmap.moving.differencing`
implements the log-odds layer (dwell increment 0.6/frame, three
frames to join; candidate penalty −0.5; lazy decay 0.03/frame,
so absorbed ghosts expire in ~80 unobserved frames) and the
τ(Z, θ̂) test as an own/neighbour-voxel fast path plus a
coarse-gated chunked-numpy exact stage: ~0.018 s per 4 k-point
frame on the dense-surface workload (the first implementation
took 15.2 s); the adversarial sparse-layer worst case measures
~0.15 s and is carried as a known bound for the CM5 profile.
Clustering is grid-hash connected components in map space (the
design's image-space connectivity is equivalent at this
sampling). Areas are convex hulls in the points' frame with
centroid association gated at max(25, 2.5 × extent); the
handler publishes live `MovingArea` messages on
`StreamMovingAreas`. Two recorded deviations: the velocity gate
on absorption is realized as cluster-level candidate penalty
rather than per-point image displacement, and τ's depth is the
map-frame range until runtime VO supplies camera-frame depth
(OQ1).

### Step 2 — Moving areas: mask → polygon → area tracks

1. Project candidate clusters back into the current image;
   rasterize a binary motion mask at analysis resolution (376×240).
2. Clean the mask: drop connected components smaller than
   `min_area_px(Z)` — the minimum scales with the component's
   median depth, it is not a constant. A fixed 150 px minimum is a
   hard detection cliff: at half resolution (fx ≈ 230 px) a person
   subtends ~150–250 px at 15 m and is invisible by 25 m. The
   minimum is set from the intended detection envelope instead:
   `min_area_px(Z) = A_min(Z_ref)·(Z_ref/Z)²` with the envelope
   stated as **persons to 20 m, vehicles to 40 m** (at 20 m a
   person is ~110 px, so the floor there is ≤ 60 px; below that,
   cluster-point count from step 1.3 is the real gate). The
   envelope, not the pixel count, is the design commitment.
   Fill holes by keeping each component's filled contour.
3. Trace each component's contour and simplify with
   Douglas–Peucker (ε ≈ 2 px) → the area's **polygon**
   (≤ 64 vertices). The polygon lives in 2D image space — where
   contours are natural — with a depth range `[Z_min, Z_max]` and
   dynamic point count carried alongside, not a 3D hull.
4. Publish `MovingArea { frame_id, t_ns, polygon, depth_range,
   point_count, area_track_id }` on the moving-areas stream (wire
   contract below) as soon as it is computed — which may be
   several frames after the frame it describes; the `frame_id` is
   the join key, and consumers must tolerate areas arriving late
   and out of step with every other stream. Associate areas
   across frames into **area tracks**: gate on centroid distance
   scaled by depth and implied velocity —
   `gate(Z, v) = max(1.5 m, 1.25·|v|·Δt)` in map frame, with mask
   IoU as a tie-breaker only. A fixed IoU ≥ 0.2 gate breaks for
   fast movers for the same reason per-voxel recurrence did (a
   15 m/s car at 5 Hz barely overlaps itself frame to frame).
   Accepted failures, stated rather than silent: crossing movers
   of similar size may **swap identities**, and a merged blob
   (car + trailer, two people holding hands) is tracked as one
   area until it splits, at which point the children start new
   area tracks. Area IDs are never reused within a segment; a
   mover crossing a segment (flush) boundary becomes a new area
   track — and, if graduated, a new object track — in the next
   segment, unless a future re-identification stage links them.

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

**As built (2026-10-27, n4).** `surmap.moving.classify` computes
the deciding statistics per area track (`TrackMotionStats`:
net/path, velocity coherence as mean-velocity over mean-speed,
Welford area variance) and applies the table above with ≥5
observations over ≥1 s; RIGID_MOVER and OSCILLATING are terminal
and verdicts are versioned, so a decelerating car cannot flap
the published verdict. Keypoints are FPS seeds from the dynamic
candidates with PCA endpoints, given identity by the bounded LK
tracker (`surmap.moving.keypoints`, 21×21 window, residual
failure re-seeds), filtered by one ego-compensated
constant-velocity Kalman filter; observations buffer in a 3 s
ring (`surmap.moving.buffer`). The shipped thresholds are the
untuned starting values: tuning on the §6.1 snippets is deferred
(`src/surmap/docs/todo/2026-10-27-moving-snippet-acceptance-tuning.md`),
and detector-track identity adoption in the handler is deferred
(`src/surmap/docs/todo/2026-10-27-moving-detector-identity-adoption.md`)
— snapshots carry area-allocated identities until then.

### Step 4 — Per-area analysis (only for rigid movers)

Compute follows attention: this stage runs on at most a handful of
polygons, cropped regions only.

1. **Label (optional, cheap):** overlap the polygon with the Coral
   detector's tracked boxes for the same frame. IoU ≥ 0.4 adopts
   the box's label and — importantly — its existing `track_id`, so
   the moving object keeps the identity the survey stream already
   publishes. No overlap → label stays `unknown`; the object is
   still real (the sliding-crate case).
2. **Keypoints, with temporal identity.** The keypoint pool is
   the area's **dynamic candidate points themselves** (step 1) —
   not "stereo points inside the polygon" re-clustered by depth:
   the area's depth range already came from its dynamic points,
   and re-clustering polygon points picks the wrong cluster
   whenever the mover is partly behind foreground geometry. From
   the candidates, farthest-point sampling selects ≤ 16 seeds
   plus the PCA principal-axis endpoints (even coverage, object
   extent). Seeds then acquire identity through a **bounded
   Lucas–Kanade tracker**: each seed is tracked in a small window
   (≤ 21×21 px, inside the polygon only, ≤ 18 tracks) across
   analyzed frames; a seed whose LK residual fails is
   re-seeded by FPS from the current candidates. Without this,
   per-keypoint temporal filtering is meaningless — FPS re-sampled
   from scratch each frame gives point #5 no relation to last
   frame's point #5, and "held from prediction" has nothing to
   hold. With LK identity, the same seed is the same surface point
   until it demonstrably isn't.
   Human-specific landmark models (hand/body pose) are
   station-class compute and are *not* run on-board; the station
   refines person tracks to skeletal keypoints downstream (§7).
   Honest scope note: without descriptors (station work), on-board
   keypoints are *tracked samples of the object's extent*, not
   semantically re-identifiable correspondences; LK gives
   short-horizon identity, not re-acquisition after occlusion.
3. **One filter, in the right frame.** A single constant-velocity
   Kalman filter per keypoint, run **ego-motion-compensated in
   camera frame** (the held/VO pose increment is removed before
   the update, so the filter sees object motion, not drone
   motion). Not One Euro in image space followed by Kalman in
   camera frame: two serial low-pass filters double the lag and
   couple their tuning, and image-space smoothing mostly smooths
   the drone's own translation. When depth at a keypoint is
   missing, sample the median disparity in a 5×5 window around
   its pixel; if still missing, the keypoint is held from the
   filter's prediction for ≤ 3 frames, then dropped and
   re-seeded.

### Step 5 — Buffering (the edge-device discipline)

Per graduated area track, buffer a ring of observations:
`{ t_ns, camera-frame keypoints (≤ 18 × Vec3), centroid,
velocity, VO pose increment since the previous observation }` —
a few hundred bytes per observation, 3 s window,
hard cap per track and globally. The VO increments are what step
6 distributes the keyframe correction over. This buffer is the *only* state
stage 6 needs; raw frames and dense points are never retained for
this feature. The buffer is also the degradation valve: under CPU
or memory pressure it shrinks first (§5).

### Step 6 — Retrospective map-frame placement

When the RTAB-Map sidecar flushes at segment end (the only moment
optimized poses exist):

1. Place each buffered observation by **distributing the
   keyframe correction over the stored VO increments**, not by
   linear/slerp interpolation between keyframes. The step-5
   buffer therefore also stores the frame-to-frame visual
   odometry increments used at runtime. At flush, the correction
   between the VO chain and the optimized keyframe poses at the
   bracketing keyframes is distributed proportionally along the
   chain (pose-graph-lite). Naive interpolation between ~1 s
   keyframes under mid-segment acceleration `a` errs by up to
   `a·Δt²/8` ≈ 25 cm — the same order as a person's extent, and
   enough to fail the "within true extent" acceptance;
   correction distribution over VO increments is an order of
   magnitude better for the same buffer.
2. Transform the buffered camera-frame keypoints into the map
   frame; recompute the track verdict with these refined
   positions (the runtime verdict used held poses; the published
   verdict must not — see the verdict lifecycle rules in the
   wire contract: recomputation may only *confirm* a published
   terminal verdict, never retract it).
3. Emit one snapshot per observation — sparse keypoints, existing
   designation (`100 + track_id` from step 4.1 when a detector
   identity was adopted; otherwise a track ID allocated in the
   same space). **Designation allocation is disjoint by
   construction:** detector track IDs come from the detector's
   tracker (monotonic from 1); area-allocated IDs come from a
   separate allocator starting at a reserved offset
   (`AREA_TRACK_ID_BASE = 1_000_000`), monotonic and never reused
   within a deployment. The two spaces cannot collide, and the
   `object_track_id` field in the snapshot message says which
   space it came from via the `identity_source` field. Moving
   objects are emitted as timestamped snapshots, never
   accumulated, exactly as the architecture already requires.
4. Seed/refresh the accumulated static layer from the new RTAB
   cloud (step 1), and drop buffered evidence older than the
   segment.

### Step 7 — Publication

Keypoint snapshots are published on the moving-areas stream at
flush time (same emitter/dedup discipline as the survey stream's
object batches) as a **different message type** from the live
areas — `MovingObjectSnapshot`, not a second serving of
`MovingArea` for the same `frame_id` with "keypoints present" as
an implicit phase flag. One snapshot per buffered observation,
carrying that observation's original `frame_id`, its verdict,
and its map-frame keypoints under the object's designation
(`100 + track_id`). They arrive later than the live area messages
for the same frames — that lag is inherent to batch poses and is
why the stream is separate and frame-ID-keyed rather than merged
into `StreamSurvey`. The station consumes area tracks and
snapshots from this stream and layers its SAM 3.1 refinement
(person landmarks, mask-exact boundaries) onto them downstream.

### Wire contract — `StreamMovingAreas`

A third BIDI method on `Cm5SurveyService`, added when this is
implemented (one proto change, bindings regenerated):

```proto
rpc StreamMovingAreas(stream Cm5Request) returns (stream MovingAreasResponse);

// Live observation, published as soon as stage 2 computes it.
// One lifecycle: an area on one frame, keypoints never present.
message MovingArea {
  int64 frame_id = 1;        // the frame this area was computed FROM
  int64 t_ns = 2;            // that frame's timestamp
  repeated Point2 polygon = 3;
  double depth_min_m = 4;
  double depth_max_m = 5;
  int32 dynamic_point_count = 6;
  int64 area_track_id = 7;
  MovingVerdict verdict = 8; // UNKNOWN | RIGID_MOVER | OSCILLATING
  int64 verdict_version = 9; // increments on every verdict change
}

// Flush-time snapshot, published by step 6 for graduated tracks.
// One lifecycle: map-frame keypoints for one buffered observation.
message MovingObjectSnapshot {
  int64 frame_id = 1;        // the buffered observation's frame
  int64 t_ns = 2;
  int64 area_track_id = 3;
  int64 object_track_id = 4;         // designation 100 + object_track_id
  IdentitySource identity_source = 5; // DETECTOR | AREA_ALLOCATED
  MovingVerdict verdict = 6;          // final, confirmed at flush
  repeated Point3 keypoints = 7;      // map frame
  Point3 centroid = 8;
  Point3 velocity = 9;                // map frame, m/s
}

message MovingAreasResponse {
  oneof payload {
    MovingArea area = 1;
    MovingObjectSnapshot snapshot = 2;
  }
}
```

**Verdict lifecycle (no flapping).** Verdicts are states with
legal transitions, not a recomputed label: `UNKNOWN →
RIGID_MOVER` and `UNKNOWN → OSCILLATING` are the only live
transitions, and **both are terminal** once published — a track
published as `RIGID_MOVER` is never later published as
`OSCILLATING` (a vehicle decelerating at a stop line traverses
exactly that evidence band). Each change increments
`verdict_version`; consumers apply last-write-wins per
`area_track_id` + highest version. The flush-time recomputation
(step 6.2) may *confirm* the live verdict into the snapshot; if
refined positions contradict a published terminal verdict, the
snapshot is suppressed and the contradiction is logged as a
tuning signal (§6) — a published verdict is never retracted.
Tracks that never leave `UNKNOWN` publish areas only, never
snapshots.

Contract rules, mirroring the detections stream's: config first,
only channel-0 frame pairs are analyzed, one message per computed
area observation (frames may be skipped entirely under load —
absence is reconcilable by `frame_id`), and no message is ever
attached to a survey or detection response.

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
  observations of the least-coherent tracks first. A dedicated
  **layer-memory counter** tracks voxel count × per-voxel cost
  against the 2 M-voxel cap from step 1 — at 0.05 m voxels, an
  uncapped 100×100 m survey's ground plane alone is ~4 M voxels
  (128–256 MB), the entire budget; the counter is what makes
  "capped" a mechanism instead of an adjective.
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
  Targets, stated as rates rather than one zero: **false-
  graduation rate** (rigid-mover verdicts per minute, and per
  class — vegetation/drift/shadow) ≈ 0 over the full sequence;
  total dynamic-area coverage < 1% of frames; and **static-layer
  purity**: the fraction of annotated mover points (where
  annotations exist) that entered the static layer stays < 1% —
  the metric for §1's core property, not just verdict counts.
  Fidelity caveat: EuRoC is global-shutter, hardware-synced
  stereo; it will *not* stress rolling-shutter or VO-drift
  failure modes. If the production camera differs, a drift-burst
  control (synthetic θ̂ injection) is required before the τ
  pose term is trusted.
- **Oscillation control — windy vegetation footage** (to add to
  the dataset registry): target: areas found, none graduated;
  net/path and coherence shown to be the deciding statistics.
- **Positive control — a stereo sequence with real vehicles /
  pedestrians** (KITTI tracking subset is the natural registry
  addition). Two separate rates, because one number would
  conflate detector recall with pipeline graduation: **graduated
  | annotated** ≥ 90% of annotated mover-seconds become rigid
  movers, and **identity-correct | graduated-with-detector-track**
  ≥ 95% of those carry the correct adopted `track_id` (adoption
  needs an IoU ≥ 0.4 detector hit, so identity correctness is
  conditioned on the detector having fired). Keypoint snapshots
  within the object's true extent (checked against box/mask
  annotations). **Metrics are gated by range**: at 30 m KITTI
  disparities are 1–2 px, so τ(Z) balloons and candidates
  explode — report graduation and purity in range bands
  (0–10 / 10–20 / 20–40 m), and note KITTI is ground-level:
  it does not exercise aerial/oblique projection sizes, so the
  §4 detection envelope (persons to 20 m) needs an aerial control
  before it is claimed, not just KITTI.
- **Resource gate:** the CM5-profile run (4-core container limits
  approximating the CM5, RTAB sidecar active) stays within §2
  budgets for a full EuRoC replay.

Each control becomes an E2E in the established pattern (recorded
data in, semantic assertions out, everything torn down).

### 6.1 Real-video snippet controls (short clips, known answers)

The controls above are dataset-scale. For fast iteration and for
failure modes no stereo dataset covers, the evaluation also uses
**short real-video snippets**: 8–15 s of frames (decimated to the
5 Hz analysis cadence, 376×240), each with a hand-verified oracle
and a written expected outcome. Snippets are fetched, never
committed as binaries — a fetch script in the established pattern
(URL + size + SHA-256 pinned, cached, torn down) extracts the
frame range; what is committed is the snippet manifest (source,
license, frame range, hash) and the oracle annotations (small
JSON), so CI replays byte-identical frames.

**Stereo honesty — what a snippet can and cannot prove.** All
three scenes below are *monocular*. They therefore cannot
exercise stage 1 (stereo differencing against the static layer)
or stage 6 (RTAB pose placement), and no snippet result may be
quoted as evidence for those stages. What they *do* exercise is
production stages 2–5, entered at their real seam: the stage-1
output type (candidate clusters with depth ranges) is
synthesized from the oracle's boxes/masks by a test adapter —
the same hexagonal-port discipline as the in-memory SLAM
backend — and stages 2–5, the wire messages, verdict lifecycle,
and resource counters run unmodified. A snippet failure is a
stage 2–5 failure; a snippet pass says nothing about stereo.
The full chain (stages 1–7 *with* RTAB-Map) is evidenced by the
dedicated **stereo snippet in §6.2**, which is a hard
requirement, not an optional extra: without it, nothing in the
evaluation ever runs the design against the real sidecar
except EuRoC, which has no movers.

Candidate evaluation (checked 2026-10-27; HEAD requests and, for
the Commons clips, extracted frames inspected):

| Scene | Candidate | License | URL stability | Fit | Verdict |
|---|---|---|---|---|---|
| Traffic | VisDrone2019-MOT (Tianjin Univ.) | research-use terms, no redistribution | poor — official links are Google Drive / Baidu; the Ultralytics GitHub-release mirror carries only DET stills, not video | monocular, drone moving over streets, per-frame box + track-ID annotations, cars/pedestrians | **primary, local/nightly** — sequence picked by spike (below); fetch risk accepted outside CI gate |
| Traffic | "Jane M. Byrne Interchange Traffic" (Wikimedia Commons) | CC BY-SA 4.0 | excellent — direct `upload.wikimedia.org` file, 31 s, 1080p | monocular aerial interchange; camera motion **unverified** (VP9 original resists seek-based frame checks; check after full download) | **CI fallback** — hand-annotated oracle; if the camera proves static, it still tests graduation, downgraded as an ego-motion control |
| Traffic | UAVDT / Stanford Drone | various | poor — Drive links / request form | UAVDT fits; Stanford is a hovering camera | rejected (fetch friction; Stanford fails the moving-drone requirement) |
| Forest fire | Boreal Forest Fire (Pesonen et al., *Sci. Data* 2025) | CC BY 4.0 | unverified — Fairdata DOI `10.23729/fd-72c6cf74-b8eb-3687-860dbf93a1ab94c9`; spike must confirm an unauthenticated fetch before adoption | monocular UAV over real prescribed boreal burns, 292 clips, human boxes + SAM smoke masks | **primary if fetch verifies** — only candidate that is actually an overhead forest fire with masks |
| Forest fire | "Aerial video of Wennington wildfire, 2022" (Commons) | CC BY 3.0 | excellent — direct Commons file; original is 139 s / 418 MB, so the fetch pins a transcoded derivative, not the original | monocular drone aerial; frames at 12 s / 40 s inspected: active smoke/fire edge, burned ground, drifting plume, moving camera | **verified fallback** — hand-annotated smoke/fire polygons; grass/village fire, not forest canopy |
| Forest fire | FLAME 2 (IEEE Dataport) / Hürtgenwald clip (Commons) | Dataport login / CC BY-SA 4.0 | poor / excellent | pile burns, not a big forest fire / distant smoke from ground level (frame inspected) | rejected on fit |
| Drone swarm | Purdue UAV_Dataset (Li et al.) | BSD 3-Clause (stated on dataset page) | excellent — direct `engineering.purdue.edu` zips, unchanged since 2017 (`Videos.zip` 2.04 GB, annotations 0.95 MB; both HEAD-checked) | monocular GoPro on a *moving* UAV, up to 8 target UAVs against sky/ground, VATIC track annotations (v2) | **primary** — annotation ranking run for this plan: `Clip_50` (1,521 frames, 11 IDs, ≤5 simultaneous) and `Clip_28` (1,685 frames, 14 IDs, ≤5 simultaneous) are the densest; spike picks the 10 s window with most simultaneous targets |
| Drone swarm | UAVSwarm (Wang et al. 2022) | paper-stated public | unverified — no stable direct link found from the paper | 72 sequences, 3–23 UAVs, annotated | backup if Purdue sky backgrounds prove too easy |

Per-snippet oracle and expected outcome (asserted on the
`StreamMovingAreas` messages, not on pixels):

- **Traffic (rigid movers, fast).** Oracle: per-frame boxes +
  track IDs (VisDrone MOT format converted once, or hand boxes
  for the fallback). Expected: cars crossing the frame graduate
  `RIGID_MOVER` (this is the issue-1 regression test — a snippet
  car at frame-to-frame displacement ≫ voxel size must still
  graduate, via cluster-level persistence); graduated |
  annotated and identity-correct | graduated reported per §6;
  identity swaps counted, not hidden. Pedestrians below the
  §4 envelope at range are expected misses and are recorded as
  envelope evidence.
- **Forest fire (deformable, huge).** Oracle: smoke/fire
  polygons per frame (Boreal masks rasterized to polygons, or
  hand polygons for the fallback). Expected: areas *are*
  published (change is real), **zero** `RIGID_MOVER`
  graduations and zero keypoint snapshots over the whole clip;
  verdicts terminate at `OSCILLATING` or stay `UNKNOWN`. The
  plume's net drift is the trap for net/path — velocity
  coherence and area stability must be the deciding statistics,
  and the tuning record must say so. The fire polygon also
  stress-tests the ≤64-vertex Douglas–Peucker cap and the area
  caps in §5.
- **Drone swarm (many, tiny, fast).** Oracle: Purdue `refined_gt`
  tracks converted to boxes. Expected: simultaneous area tracks
  never exceed the §2 area cap; targets meeting the detection
  envelope graduate `RIGID_MOVER` with LK-held keypoints; the
  many sub-envelope targets (a UAV at 100 m is a few pixels) are
  *expected* misses — the assertion is that they produce no
  phantom areas, no verdict flapping, and no static-layer
  candidates, and the miss count is reported against the
  envelope so the envelope claim stays honest.

Snippet harness (one implementation, three fixtures): fetch →
extract/decimate frames → build oracle candidate clusters at
5 Hz → replay through stages 2–5 → assert stream messages,
verdict lifecycle, and counters. Each snippet's expected-outcome
block above is its acceptance test; a change to an expectation
requires the same review as a change to the design.

**Fetch outcomes (recorded 2026-10-27, stack `#moving-objects`
n2).** The fetch tooling and the `CandidateCluster` seam are
implemented (`scripts/fetch_moving_snippets.py`,
`surmap.moving.snippets`); the KITTI stereo snippet of §6.2 is
fully wired and live-verified (below). The three monocular
datasets are not yet pinned: Boreal's Fairdata fetch is
unverified (Wennington CC BY 3.0 is the fallback), VisDrone-MOT
is distributed via Drive/Baidu only, and the Purdue window pick
is unmade. Those spikes are recorded as deferred scope in
`src/surmap/docs/todo/2026-10-27-moving-snippet-dataset-spikes.md`;
they gate the snippet acceptance tests, not the seam.

### 6.2 Stereo snippet — the RTAB-Map chain (required)

At least one snippet must carry **real stereo pairs and camera
calibration**, converted into the EuRoC layout the sidecar
consumes (`mav0/cam{0,1}` PNGs + `sensor.yaml` + IMU csv, the
sidecar's existing stationary-IMU fallback covering snippets
without IMU), and run through the **real
`SidecarRtabmapBackend`** — Docker sidecar, own/shared-container
rules, full teardown — not a mock. This is the only snippet
that exercises stages 1–7 together: stereo reconstruction,
differencing against an RTAB-seeded static layer, and map-frame
keypoint snapshots after a real flush.

**Pick: KITTI tracking (training split).** Stereo left/right
colour pairs (`image_02`/`image_03`, rectified), per-sequence
calibration (`P0`–`P3`; fx ≈ 721.5, baseline ≈ 0.54 m derived
from `P3`−`P2`), and per-frame track labels with IDs for cars,
pedestrians, cyclists — the mover oracle and the stereo input
are the same snippet. License CC BY-NC-SA 3.0. Downloads are
direct `s3.eu-central-1.amazonaws.com/avg-kitti` files, stable
since 2018 (HEAD-checked 2026-10-27): calib 90 KB, labels
2.3 MB, but images are two ~15 GB zips — so the fetch script
must **range-extract only the chosen sequence's members** (zip
central directory over HTTP range requests), never download
30 GB for 15 s of video. Sequence pre-ranking from the label
files (run for this plan): `0020` (837 frames, 70 long car
tracks), `0009` (784 frames, 68), `0001` (426 frames, 65); the
spike picks sequence + a 10–15 s window by verified *world*
motion (parked rows inflate raw counts), decimates to 5 Hz,
and derives `sensor.yaml` from that sequence's calib file
(rectified input ⇒ zero distortion; resolution read from the
PNGs, calibration scaled to the analysis resolution by the
existing demo scaling helpers). Expected outcome: RTAB flush
returns real poses and a non-empty cloud; annotated movers
graduate and their flush-time snapshots land within the
annotated extent (the §6 range-gated metrics apply); the static
cloud is asserted streak-checked against mover tracks as a
recorded observation (the known §1 limitation until masked
replay lands — measured, not hidden).

**Fetch outcome (recorded 2026-10-27, n2).** Sequence 0020
frames 0–119 are range-extracted from both 15 GB zips (zip64
central directory + one contiguous span per sequence; `testing/`
members share basenames and are filtered out), with calib and
labels alongside and a SHA-256 manifest in the cache. The full
chain outcome is recorded with the placement node (n5) and in
`tests/test_moving_kitti_e2e.py`.

Rejected stereo alternatives: EuRoC (already in-repo, but
static — negative only); ETH3D (calibrated stereo, but the
earlier cables_2 attempt had ~95% of correspondences rejected
by RTAB-Map — an RTAB-compatibility risk, not a data risk);
TartanAir (synthetic; the snippet programme exists to escape
synthetic-only evidence); DrivingStereo (real and calibrated,
but no mover track labels — backup if KITTI labels prove
unusable); Oxford RobotCar (application-gated download).

**Calibration fallback — COLMAP on this host.** If a future
stereo snippet arrives *without* usable calibration, calibrate
it here before it is adopted: this host has an RTX 5060 Ti
(16 GB, CUDA 13.2) and COLMAP 4.2.1 built with CUDA (both
verified 2026-10-27). Procedure: extract left/right frames →
COLMAP feature extraction (OPENCV model, one camera per
channel, both channels in one database) → sequential matching →
sparse reconstruction → per-channel intrinsics and the rig
extrinsic from the joint reconstruction. Two gates before the
calibration is written into `sensor.yaml`: (1) reprojection
error < 1 px and, when a reference calibration exists,
recovered fx within 2% of it — proven first on the KITTI
snippet against its shipped calib, so the fallback is validated
before it is ever needed; (2) **baseline scale**: COLMAP is
up-to-scale and cannot observe the stereo baseline in metres,
so scale must be fixed from a known reference (rig
specification, a measured target in view, or a calibrated
sibling sequence). A snippet with no scale reference is
calibration-rejected — it is never run at a guessed baseline,
because every depth, τ(Z), and extent assertion downstream
would inherit the error. COLMAP calibrates; it does not
synthesize a second camera — the monocular snippets in §6.1
remain monocular and stage-2-seam-only no matter how well
COLMAP reconstructs them.

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
   Its resolution feeds τ directly: the measured drift becomes
   the `θ̂` term in step 1.2, and the VO increments it produces
   are what step 6 distributes corrections over — this question
   owns both.
2. **Masking RTAB-Map's input (depth-zeroing replay).** RTAB-Map
   *can* exclude dynamic pixels — zeroing depth there means, with
   the default `Vis/DepthAsMask=true`, no features and no dense
   points are extracted (the DOTMask precedent). Our sidecar
   replays recorded segments at flush time, when the whole
   segment's stage-2 polygons already exist, so persisting
   per-frame polygons and pre-zeroing depth before replay is a
   cheap follow-up changeset that kills mover streaks in RTAB's
   exported cloud at the source and improves its poses in busy
   scenes. It is *not* in this design's scope (this design feeds
   nothing into RTAB-Map); it is recorded here so the limitation
   is not mistaken for an RTAB-Map property — it is a property of
   our wrapper. Until it lands, streak cleanup is station work.
3. **First-segment cold start — a poison window, not just low
   confidence.** Before the first flush there is no RTAB seed.
   Bootstrapping the static layer from stereo self-agreement
   absorbs anything slow enough to dwell — including walkers —
   into the reference layer for the whole first segment: the
   *layer itself* is wrong, not merely the verdicts' confidence.
   Two options, to decide at implementation: (a) do not seed
   until the first flush — no on-board moving-area detection in
   segment 1, honest and simple; or (b) bootstrap with the dwell
   test only and stamp every first-segment area `low_confidence`.
   Option (a) is the default unless segment-1 coverage turns out
   to matter.
4. **Threshold ownership.** The step-3 thresholds and §2 budgets
   need one config home (`surmap.motion` alongside
   `classify_motion`'s) and one tuning record from §6's controls
   before they are treated as settled.

### References (prior art this design stands on)

- **ERASOR** (Lim et al., IEEE RA-L 2021,
  [arXiv:2103.04316](https://arxiv.org/abs/2103.04316)) —
  pseudo-occupancy ratio tests for building static maps from
  dynamic scenes. Step 1 is a lighter-weight, streaming cousin;
  ERASOR's documented failure modes (occlusion, incidence angle,
  semi-static objects) are the same ones §4's dwell test, τ pose
  term, and terminal verdicts are shaped by.
- **OctoMap log-odds occupancy with decay** (Hornung et al.,
  2013) — the standard answer to "joined the static layer,
  never leaves": occupancy as evidence that accumulates *and*
  expires. Step 1's layer uses it instead of a binary set, at
  voxel-hash cost, without ray tracing (excluded by §2).
- **RTAB-Map dynamic-object behaviour** — maintainer-confirmed:
  the supported masking mechanism is zeroing depth at dynamic
  pixels (`Vis/DepthAsMask`); `Grid/RayTracing` clears movers
  from the occupancy grid but the exported `cloud_map` never
  filters them. DOTMask demonstrates the depth-zeroing pattern
  with detector masks. This is the basis for open question 2.

## 9. Implementation phasing (for the changeset plan)

As a PR stack (node numbers are planning identity; each node
carries its own changeset with kind, green wave, and
verification rung):

| Node | Delivers | Kind | Verification |
|---|---|---|---|
| n1 | **This design + development plan** — PR #17 itself (`docs/moving-object-design`), the stack's bottom node; reviewed and merged first, successors restack onto `main` | docs, behaviour-preserving | review + CI on #17 |
| n2 | **Snippet fixtures + harness skeleton**: fetch script (pinned URL/size/SHA-256 per snippet), oracle converters (VisDrone MOT, Purdue `refined_gt`, mask→polygon), the stage-2-seam test adapter, snippet manifests for traffic / fire / swarm per §6.1, **plus the KITTI stereo snippet per §6.2** (range-extraction fetch, calib→`sensor.yaml` converter, EuRoC-layout staging) and the **COLMAP calibration cross-check** on KITTI (host RTX/COLMAP, §6.2 gates); spike outcomes recorded (Boreal fetch verified or fallback adopted; VisDrone sequence and Purdue clip window chosen by annotation density; Byrne camera motion checked; KITTI sequence/window chosen by verified world motion) | infra, behaviour-preserving | V3 — fetch + conversion commands with recorded before/after output; harness runs on a synthetic cluster and asserts the seam type; COLMAP-vs-KITTI calibration comparison recorded |
| n3 | **Differencing + areas (steps 1–2)** + `StreamMovingAreas` proto and handler from the start — the stream is the only publication surface this feature has | feature | V1 — synthetic-cloud unit tests, EuRoC negative-control E2E, traffic-snippet stage-2 assertions |
| n4 | **Classification + keypoints + buffering (steps 3–5)**: verdict lifecycle, LK keypoints, one ego-compensated filter | feature | V1 — tracker-statistic unit tests; fire snippet (zero graduations), swarm snippet (caps, envelope misses), traffic snippet (graduation + identity rates) |
| n5 | **Retrospective placement + publication (steps 6–7)** wired into the sidecar flush and the moving-areas stream | feature | V1 — the §6.2 KITTI stereo snippet run through the real `SidecarRtabmapBackend`: flush returns real poses/cloud, annotated movers graduate, snapshots land within annotated extent under existing designations (the only full-chain proof; §6.1 monocular snippets cannot provide it) |
| n6 | **Resource governance (§5)** counters, caps, CM5-profile resource gate, before this is enabled by default on-board | infra | V3 — CM5-profile replay with recorded budget counters |

Green waves: wave 1 = n1 (#17), n2 — n3's stage 1 needs only
EuRoC, its stage 2 is specified against the seam type n2 pins,
and n3 is not greenable on snippet assertions until n2 lands
(stated in its changeset, not discovered). Wave 2 = n4.
Wave 3 = n5, n6. Branch line is the waves concatenated:
n1 → n2 → n3 → n4 → n5 → n6.

The full development plan — per-node owned surfaces, inherited
dependencies, red tests, landing and risks — is in
[moving-object-detection-plan.md](moving-object-detection-plan.md).
