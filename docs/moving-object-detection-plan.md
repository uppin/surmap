# Moving-object detection — development plan

Status: planning (on PR #17, with the design). This plan turns
[moving-object-detection-design.md](moving-object-detection-design.md)
into a stack of implementable PRs. The design doc is the PRD for
every feature node below — no node writes a second PRD; each
node's changeset references the design section it implements.
When the stack is cut, each node's changeset is created with its
branch (per the pr-stack model) from the row in this plan; this
document is then superseded by those changesets and is removed
at the first node's wrap.

## Stack shape

- **Stack slug:** `moving-objects` · 5 nodes · trunk `main`.
- **Precondition:** PR #17 (design + this plan) merges first.
  No stack branch is cut from the design branch.
- **Registration:** `gh stack` v0.3.0 is installed and verified
  on this host. Pass 1 creates branches + changesets and runs
  `gh stack submit --auto`; pass 2 adds each node's red commit
  bottom-up; the completion gate is a cascade rebase with every
  layer current.
- **Branch / title convention:** branch `pr-<k>-<node-slug>`,
  title `feat(surmap): <delivered capability> (#moving-objects
  <k>/5)` (type follows node kind; subject ≤ 100 chars including
  the stack group).

| Node | Branch | Title (delivered state) | Kind (Type · Behaviour) | Complexity |
|---|---|---|---|---|
| n1 | `pr-1-moving-snippets` | `chore(surmap): real-video snippet fixtures and candidate seam (#moving-objects 1/5)` | Infra · preserves | 3 — fetch/conversion adapters, integration tests, no behaviour change |
| n2 | `pr-2-moving-differencing` | `feat(surmap): static-layer differencing and moving areas stream (#moving-objects 2/5)` | Feature · adds | 4 — proto/contract change, concurrency (5 Hz worker), one package |
| n3 | `pr-3-moving-classification` | `feat(surmap): area verdicts, tracked keypoints and observation buffer (#moving-objects 3/5)` | Feature · adds | 4 — tracking/filter semantics, several owned symbols |
| n4 | `pr-4-moving-placement` | `feat(surmap): map-frame moving-object snapshots at RTAB flush (#moving-objects 4/5)` | Feature · adds | 4 — sidecar integration, real-RTAB E2E |
| n5 | `pr-5-moving-governance` | `chore(surmap): moving-area resource budgets and CM5 profile gate (#moving-objects 5/5)` | Infra · preserves | 3 — counters/caps around existing stages, recorded measurement |

Green waves: **wave 1 = {n1, n2}** with the caveat recorded in
n2's changeset (below), **wave 2 = {n3}**, **wave 3 = {n4, n5}**.
Branch line is the waves concatenated: n1 → n2 → n3 → n4 → n5.

## Shared ground rules (all nodes)

- TDD per repo `AGENTS.md`: red first, green minimum, refactor
  green. Fluent tests per the fluent-tests skill.
- Gates per node before push: `uv run ruff check src tests`,
  `uv run ruff format --check src tests`, `uv run mypy`,
  `uv run pytest -q`; E2Es additionally under their env flags
  (`SURMAP_REQUIRE_RTABMAP_E2E=1` where RTAB is involved).
- No zombie processes/containers: every E2E tears down what it
  started; a shared RTAB container is only ever borrowed via
  `SURMAP_RTABMAP_SHARED_CONTAINER`, never stopped.
- Designations and wire rules come from the design (§4 wire
  contract): areas and snapshots are separate messages under a
  `oneof`; verdicts are terminal + versioned; detector vs
  area-allocated IDs are disjoint (`AREA_TRACK_ID_BASE`).
- Thresholds/config live in one home next to
  `surmap.motion.classify_motion` (design OQ4).

## n1 — Snippet fixtures and the candidate seam (infra)

**Delivers:** the evaluation ground every later node stands on,
and no production behaviour.

Owned surface:

- `scripts/fetch_moving_snippets.py` — pinned fetch (URL, size,
  SHA-256) + frame extraction to the snippet cache; KITTI
  range-extraction (zip central directory over HTTP ranges) for
  the §6.2 stereo snippet; COLMAP calibration cross-check
  command (host RTX + COLMAP 4.2.1, design §6.2 gates).
- `src/surmap/moving/__init__.py`, `src/surmap/moving/candidates.py`
  — the seam types only: `CandidateCluster` (points, depth
  range, frame_id, t_ns) as the stage-1 output / stage-2 input
  port. No differencing logic here.
- `src/surmap/moving/snippets.py` — snippet registry (traffic,
  fire, swarm, KITTI stereo), oracle loaders/converters
  (VisDrone MOT, Purdue `refined_gt`, mask→polygon, KITTI
  labels), and the EuRoC-layout staging converter for KITTI
  (calib `P2/P3` → `sensor.yaml`).
- `tests/test_moving_snippets.py` — fetch/convert/oracle tests
  (hermetic: tiny synthetic archives, no network in CI unit
  tier); snippet E2Es are env-flagged like the RTAB/Coral ones.

Spike TODOs (first work in the node, outcomes recorded in its
changeset): Boreal fetch verified or Wennington fallback
adopted; VisDrone sequence + Purdue `Clip_50`/`Clip_28` window
chosen by annotation density; Byrne camera motion checked after
full download; KITTI sequence/window chosen by verified world
motion; COLMAP-vs-KITTI fx comparison within 2%.

Red step (V3): recorded before/after output of the fetch and
conversion commands; harness smoke test asserting the seam type
round-trips. **Greenable independently: yes.**

## n2 — Differencing + moving areas (feature, design steps 1–2)

Owned surface:

- `proto/surmap/survey/v1/survey.proto` — `StreamMovingAreas`
  on `Cm5SurveyService`, `MovingArea`, `MovingObjectSnapshot`,
  `MovingAreasResponse` oneof (design wire contract); bindings
  regenerated with pinned `grpcio-tools==1.73.1`.
- `src/surmap/moving/differencing.py` — `StaticLayer` (voxel
  hash, log-odds + decay, dwell test, 2 M-voxel cap, 40 m
  eviction radius, layer-memory counter), `tau(Z, theta_hat)`,
  candidate clustering (cluster-level persistence only — the
  peer-review issue-1 fix).
- `src/surmap/moving/areas.py` — mask→polygon (Douglas–Peucker
  ≤64 vertices), `min_area_px(Z)`, area tracks with
  velocity/depth-scaled association gates.
- `src/surmap/survey/cm5_server.py` — `stream_moving_areas`
  handler (config-first, channel-0 only, own 5 Hz worker,
  droppable under load); wiring in `cm5_service_module`.
- `src/surmap/moving/config.py` — thresholds next to
  `surmap.motion` (OQ4).

Inherited dependencies — do not implement here:

| Symbol | Owned by | State here | This node does |
|---|---|---|---|
| `CandidateCluster` seam | n1 | real if n1 landed; stub type otherwise | consumes it; never redefines it |
| Verdict/keypoint/snapshot logic | n3, n4 | absent | publishes areas with `UNKNOWN` verdict only; snapshot arm of the oneof stays unpopulated |

**Greenable independently: partly** — stage 1 + EuRoC negative
control green alone; snippet stage-2 assertions need n1's
fixtures, so those tests are written against n1's seam and are
blocked-on-n1 until it lands (recorded, not hidden).

Red tests first: static-layer dwell/absorption unit tests
(fast-car voxel case from issue 1 as a named test), τ pose-term
tests, polygon/association tests, proto contract tests
(`tests/test_survey_proto.py` pattern), EuRoC negative-control
replay asserting zero rigid graduations (all areas `UNKNOWN`
in this node), traffic-snippet stage-2 assertions.

## n3 — Classification, keypoints, buffering (feature, steps 3–5)

Owned surface:

- `src/surmap/moving/classify.py` — verdict state machine
  (terminal + versioned transitions), net/path, velocity
  coherence, area stability; feeds extended
  `surmap.motion.classify_motion` (extended, not replaced).
- `src/surmap/moving/keypoints.py` — FPS seeding from dynamic
  candidate points, bounded LK tracking (≤21×21 px, ≤18
  tracks), one ego-motion-compensated constant-velocity Kalman
  per keypoint in camera frame.
- `src/surmap/moving/buffer.py` — per-track observation ring
  (≤3 s, VO increments stored, hard caps).
- Detector identity adoption (polygon↔box IoU ≥ 0.4) in
  `areas.py`/`classify.py` using existing
  `surmap.detection` tracker IDs.

Inherited: areas + `UNKNOWN` verdicts from n2 (real behaviour —
n3's tests drive them, so **greenable independently: no, needs
n2 green**; that sequencing is the wave-2 placement).

Red tests first: verdict-transition tests including the
decelerating-car no-flap case; LK identity/re-seed tests;
single-filter lag test; snippet acceptance — fire (zero
graduations, deciding statistic recorded), swarm (area cap,
envelope misses counted), traffic (graduated | annotated,
identity-correct | graduated).

## n4 — Retrospective placement + publication (feature, steps 6–7)

Owned surface:

- `src/surmap/moving/placement.py` — VO-increment correction
  distribution (pose-graph-lite), map-frame transform,
  snapshot construction, verdict confirmation at flush.
- Flush wiring: `stream_moving_areas` + sidecar flush path in
  `cm5_server.py` / `SidecarRtabmapBackend` results; snapshot
  publication under `100 + track_id` with `identity_source`.
- Static-layer re-seeding from each flush's RTAB cloud
  (n2's `StaticLayer.refresh`).

Inherited: buffer + verdicts from n3 (real behaviour needed —
**greenable independently: no, needs n3 green**).

Red tests first: correction-distribution unit tests (known
trajectory, bracketing keyframes); the §6.2 KITTI stereo E2E
through the real `SidecarRtabmapBackend` (`tests/` E2E in the
RTAB pattern, env-flagged, full teardown): flush yields real
poses/cloud, annotated movers graduate, snapshots within
annotated extent, streak measurement recorded. EuRoC negative
control re-run end-to-end (still zero graduations, now with
snapshots asserted absent).

## n5 — Resource governance (infra, design §5)

Owned surface:

- `src/surmap/moving/governance.py` — per-stage counters
  (points sampled, areas live, buffered observations, ms/stage,
  layer-memory), hard caps enforcement, degradation ladder
  (5 Hz→2 Hz, keypoints 16→8, detector-labelled only, off).
- CM5-profile replay harness (4-core container limits, RTAB
  sidecar active) as an env-flagged E2E + recorded budget table.

Inherited: counters' producers in n2–n4 (signatures pinned in
those nodes' changesets; n5 aggregates, never re-instruments).

Verification (V3): before/after budget tables from a full
EuRoC + KITTI replay in the CM5 profile; budgets in design §2
are the pass line. **Greenable independently: no, needs n4** —
it measures the assembled pipeline.

## Landing, risks, and deferred follow-ups

- **Landing:** bottom-up only, through the registered-stack
  path (`merge-async` per node, restack verified after each
  merge — successor shows only its own files). Each node merges
  alone safely: n1 adds fixtures only; n2's stream is additive
  and publishes `UNKNOWN` areas; n3/n4 complete the feature
  behind the same stream; n5 only enforces budgets.
- **Trunk-merge safety:** every node leaves
  `uv run pytest -q`, the demo, and deploy smoke paths working
  with the node alone merged. No production data involved.
- **Risks carried openly:**
  - VisDrone fetch instability may keep the traffic snippet
    nightly-only; the Commons fallback is the CI gate (n1 spike).
  - KITTI range-extraction depends on `avg-kitti` S3 honouring
    range requests; fallback is a one-time full-zip fetch in the
    local cache, never in CI (n1 spike).
  - RTAB pose quality on KITTI city driving (design OQ1, θ̂
    estimate) is measured in n4, not assumed.
  - Thresholds (design §4 step 3) are hypotheses until the n3
    snippet tuning record exists; they are not tuned on the
    same snippets that assert them — tuning uses the first half
    of each snippet, assertions the second.
- **Deferred, recorded in the design, not in this stack:**
  depth-zeroing masked replay into RTAB-Map (design OQ2,
  follow-up changeset after n4 proves placement); station-side
  SAM 3.1 refinement of person tracks (§7); segment-boundary
  re-identification of movers (accepted identity split, §4).
