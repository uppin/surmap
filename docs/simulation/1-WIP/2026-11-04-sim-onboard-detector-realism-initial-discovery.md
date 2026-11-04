# Initial Discovery: on-board detectors on the Bevy simulation

## Combined Conclusions

- The recorded capture `tests/fixtures/bevy_sim_capture/` (PR #89; 90 grey 640×480 frames at
  t = 15.5 s, ground truth 3 `car` + 8 `collapsed_building`, no people) gives the three Coral COCO
  profiles nothing to find: at score 0.3 no frame carries a `car`, and every detection is a false
  positive (re-run 2026-11-04 with the probe below: efficientdet-lite0 `airplane` 21 frames,
  `remote` 13, `cell phone` 4; ssd-mobilenet-v2 `bottle` 9, `person` 1; ssdlite-mobiledet 13
  labels in up to 75 frames, `person` in 51).
- Root causes, each checked in the source:
  1. The cars are Poly Haven `covered_car` — a car under a tarp (`assets/scene.json`
     `car-covered-*`). Poly Haven's 521 models hold no uncovered car and no human (API listing,
     2026-11-04).
  2. Survivors are a capsule body and a sphere head (`src/world.rs` `Builder::person`) with a
     box visor (`assets/behaviour/person.figure.json`); people are not in `ground_truth.json`.
  3. The recorder writes grey8 only (`src/record.rs`, `wire::bgra_to_gray8`, `GrayImage`). The
     ELP module is MJPEG, a colour stream, with an OG02B10 colour sensor
     (`docs/camera-elp-stereo.md`), so on board the detector sees colour. The grey consumers
     (`euroc_export` converts to `L` itself; `slam/sidecar.py` and `slam/streaming.py` hand the
     refs to RTAB-Map) must keep reading grey files.
  4. The rig flies the scripted survey loop at 8 m, pitched 35° down (camera profile mount),
     80° HFOV pinhole. At t = 15.5–24.5 s it climbs the east side (x = 14) heading north; the
     survivors stand in the street centre (x ≈ −5…−1) 15–19 m to its left, so they are beyond
     the left image edge or 25 m+ away (≈ 25 px tall) for most of the pass. Flight is the sim's
     own drone (passive survey: SurMap does not steer it), and its altitude is realistic for a
     low search pass.
  5. `building`, `collapsed_building`, `debris`, `box` and `fire` are not COCO classes; on-board
     detection cannot name them (SAM does, `docs/meta-sam.md`).
- Licensed replacements with pinnable URLs: the Khronos glTF-Sample-Assets repository at commit
  `8f492390ddc7a2ae221a1369ef560589cf8c70fb` — `CarConcept` (CC-BY-4.0, Eric Chadwick /
  Darmstadt Graphics Group, 11.8 MB GLB, 4.3 m, real scale, extensions all optional) and
  `CesiumMan` (CC-BY-4.0, Cesium, 0.44 MB GLB, rigged, textured, one 2 s walk clip, 1.51 m tall,
  Z-up root node). Sketchfab downloads need a token (`SKETCHFAB_API_TOKEN` not set) and signed,
  expiring URLs that cannot be pinned in `assets.lock.json`.
- `surmap.simulation.bevy_ground_truth.project_box` already projects an ENU box onto the left
  image from a frame's `pose_enu`; there is no occlusion test.

## Exploration 1: capture, detectors and assets — 2026-11-04

### Sequence

1. Re-ran the probe over the fixture at 0.3 (numbers above).
2. Read the recorder, the person builder, the model loader and the manifest types.
3. Listed Poly Haven models; read Khronos sample metadata (`legal`) and GLB headers.

### Grep / glob

- `grep -rn bevy_sim_capture tests src` → `tests/test_bevy_sim_rtabmap_e2e.py` only.
- `grep -rn left_ref src` → `euroc_export.py` (converts to `L`), `slam/sidecar.py`,
  `slam/streaming.py`, `mission/*`, `segbench/dataset.py`.
- `grep -rn SURMAP_REQUIRE_CORAL_E2E` → `tests/test_survey_cm5_coral_e2e.py`,
  `tests/test_verify_cm5.py`, `.github/workflows/ci.yml` job `coral-e2e`.

### Inspected files

- `examples/bevy-sitl-poc/src/record.rs` — `RecordPlan`, `on_eye_read`, `save`, frames.jsonl.
- `examples/bevy-sitl-poc/src/world.rs`, `world/models.rs` — `Builder::person`, model GT boxes.
- `examples/bevy-sitl-poc/src/actors.rs` — `FigureDef`, `attach_visors`, `animate_figures`.
- `examples/bevy-sitl-poc/src/flight.rs` — survey loop geometry.
- `src/surmap/simulation/{bevy_capture,bevy_ground_truth,sim_assets,asset_sources,licences}.py`.
- `src/surmap/detection/{detector,profiles}.py`.

### Findings

As in *Combined Conclusions*.
