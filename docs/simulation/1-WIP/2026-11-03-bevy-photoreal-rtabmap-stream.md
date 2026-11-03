# Changeset: photo-real Bevy simulation with runtime assets, streamed live to RTAB-Map

**Date**: 2026-11-03
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 5 — two languages (Rust/WASM + Python), GPU readback and a browser→Python wire
format, a real-container acceptance test, external CC0 assets, rendering work only judged visually

PRD: `PRD-2026-11-03-bevy-photoreal-rtabmap-stream.md` · Discovery:
`2026-11-03-bevy-photoreal-rtabmap-stream-initial-discovery.md`

## Workflow

- [wf 1] ✅ 2026-11-03 `/plan-red #muse` Plan — PRD, changeset, initial discovery · PRD + this file + discovery (exploration by Muse Code)
  - [x] Record initial discovery
  - [x] Cross-check `src/surmap/docs/todo/` and `src/surmap/docs/code-issues/`
  - [x] Create/update PRD documentation
  - [x] Create changeset
  - [x] Build and baseline healthy (Step 7)
- [wf 2] ✅ 2026-11-03 `/plan-red #muse` Red — acceptance and failing lower-tier tests, committed · 22 Rust + 38 Python failing @ de8cab0 (cargo: 4 passed, 22 failed on `todo!()` stubs / missing `assets/scene.json`; pytest: 7 collection errors, `ModuleNotFoundError` for the six missing `surmap.simulation` modules — no Python stubs written; ruff/format clean, mypy only the 12 expected missing-module errors)
  - [x] Acceptance tests written and failing for the right reason
  - [x] Unit/integration tests written and failing
  - [x] Tests committed with the changeset
- [wf 3] ⏳ `/green #muse` Green — implement until every red test passes ·
  - [x] Red verified, failing tests reviewed (green step 1)
  - [ ] Every red test this row owns passes with production-quality code (green step 2)
  - [ ] Planner's milestones and wiring TODOs done or deferred with a record (green step 3)
  - [ ] Prerequisites Outcomes and deferred-work records reconciled (green step 3.5)
  - [ ] Committed and pushed with the row (green step 4)
  - [x] M1 Rust contracts: `scene_manifest.rs`, `wire.rs`, `flight.rs` stubs implemented; `cargo test --locked` green — 25 passed, only the shipped-manifest test red (waits for M3, expected). Survey loop: rounded rectangle ENU corners (-14, 8), (14, 8), (14, 78), (-14, 78), radius 8 m, CCW from (0, 8) east at 1.5 m/s, altitude 7 ± 1.5 m (period = loop period); corner yaw rate 1.5/8 = 0.1875 rad/s = 10.7 deg/s, within the 30 deg/s limit
  - [x] M2 Python contracts: `bevy_wire`, `bevy_capture`, `bevy_ground_truth`, `trajectory_eval`, `sim_assets`, `bevy_bridge` green — 35 passed; only the shipped-scene pin test red (waits for M3, expected)
  - [ ] M3 Runtime content per the visual spec (`2026-11-03-bevy-photoreal-rtabmap-stream-visual-spec.md` §2–§4, §6): asset shortlist → planner picks → `assets/scene.json` + `assets/assets.lock.json` (CC0 only, pinned sha256, ≤ 150 MB), `scripts/fetch_sim_assets.py`, `.gitignore` for fetched binaries; world spawned from the manifest at runtime (`AssetServer`, `AssetMetaCheck::Never`); models `.glb` or `.gltf` (planner contract change: the manifest test refuses other extensions, e.g. `.obj`); Rapier colliders per instance
  - [ ] M4 Photo-realism exactly per the visual spec §3, §5, §7, §8 — checkpoints V1–V5 reviewed by the planner (`--screenshot <dir> --at <t>`); the implementer makes no visual choice the spec does not state
  - [ ] M5 Capture: eye targets get `COPY_SRC`, `Readback` at `rate_hz` (10), grey8 conversion, ground-truth rig pose; scripted `survey-loop` flight (`?flight=` / `--flight`)
  - [ ] M6 Streaming: wasm WebSocket client (`?bridge=ws://127.0.0.1:8773`), hello + pairs, status overlay from the bridge's replies; `scripts/serve_bevy_sim.py` (static `dist/` + `assets/` on 8772, bridge on 8773, `--record <dir>`)
  - [ ] M7 Native recorder `--record <dir> --flight survey-loop --frames N`; record `tests/fixtures/bevy_sim_capture/` (≤ 6 MB, JPEG q90 frames ok) and its README (command, commit, asset lock hash)
  - [x] Planner fixes to the red acceptance test: no `# type: ignore` (filter posed results with a typed comprehension); the queried object is the ground-truth object whose `project_box` polygon lies fully inside the recent frame's image and is largest — the test asserts one exists; `survey-loop` and the capture window are planned so a car is framed near the end — done; the test stays red (capture fixture missing, M7, expected). Asset shortlist built per visual spec §2 (29 previews + index.md in the scratchpad shortlist directory); no realistic CC0 vehicle found on Poly Haven (only `covered_car`, a car under a cover) — planner picks next turn
  - [ ] M8 Acceptance `tests/test_bevy_sim_rtabmap_e2e.py` green against the real sidecar; CI `rtabmap-stream-e2e` runs it
  - [ ] All four gates green (`ruff check`, `ruff format --check`, `mypy`, `pytest`) and `cargo test --locked` + `trunk build index.html --release` in the PoC
- [wf 4] ⬜ `/pr-wrap #muse` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded (e2e numbers; live run log + screenshots)
  - [ ] `examples/bevy-sitl-poc/README.md` — runtime assets, fetch, serve + bridge, record, flight, screenshots
  - [ ] `docs/simulation/bevy-simulation.md` — new feature doc (State B), linked from `docs/simulation/disaster-world.md`
  - [ ] `docs/simulation/changelog/2026-11-03-bevy-photoreal-rtabmap-stream.md` — changelog entry
  - [ ] Validate tests (`/validate-tests`)
  - [ ] Production readiness (`/validate-prod-ready`) — (optional) when the bridge grows beyond the planned surface
  - [ ] Lint, type-check and tests green
  - [ ] Every TODO row decided
  - [ ] Deferred answers carried into the history entries
  - [ ] Docs wrapped, 1-WIP deleted, rows carried into the wrap commit and PR body; `gh pr ready`

## Red tests

Rust (`examples/bevy-sitl-poc/src/`, planner-written, reviewed — no genuine mistakes found;
declared in `src/main.rs` by the Red row): `wire.rs` (hello/pair goldens, wrong-size panic,
BT.601 grey, row padding, north/west rig poses), `scene_manifest.rs` (defaults, asset list,
future version, duplicate id, escaping path, non-GLB, ENU→Bevy placement, shipped manifest),
`flight.rs` (determinism, closed loop, speed/yaw/altitude limits, coverage).

Python (Muse, this row):

- [tests/test_bevy_wire.py](../../../tests/test_bevy_wire.py) — `test_the_hello_golden_decodes_into_the_calibration_and_its_objects`, `test_the_pair_golden_decodes_into_a_frame_with_its_rig_pose`, `test_a_message_shorter_than_its_header_length_is_refused`, `test_a_header_that_is_not_json_is_refused`, `test_a_message_of_an_unknown_type_is_refused`, `test_a_pair_whose_payload_is_shorter_than_its_frame_is_refused`, `test_the_status_reply_is_one_compact_json_text_message`
- [tests/test_bevy_capture.py](../../../tests/test_bevy_capture.py) — `test_a_recorded_session_loads_back_with_its_poses_and_ground_truth`
- [tests/test_bevy_ground_truth.py](../../../tests/test_bevy_ground_truth.py) — `test_the_left_eye_sits_half_a_baseline_along_rig_left_from_the_rig_centre`, `test_the_left_eye_optical_axes_point_right_down_and_forward`, `test_a_box_straight_ahead_projects_to_a_polygon_around_the_image_centre`, `test_a_box_behind_the_camera_projects_to_no_polygon` (behind-camera API pinned: empty tuple)
- [tests/test_trajectory_eval.py](../../../tests/test_trajectory_eval.py) — `test_alignment_recovers_a_known_rotation_and_translation`, `test_ate_of_a_noisy_copy_is_the_noise_scale`, `test_alignment_refuses_fewer_than_three_points`, `test_alignment_refuses_mismatched_shapes`, `test_ate_refuses_mismatched_shapes`, `test_alignment_never_scales_a_doubled_trajectory_to_fit`
- [tests/test_sim_assets.py](../../../tests/test_sim_assets.py) — `test_the_lock_file_loads_into_typed_pins`, `test_a_pin_escaping_the_assets_directory_is_refused`, `test_an_absolute_pin_path_is_refused`, `test_fetch_downloads_a_pinned_file_and_verifies_its_hash`, `test_fetch_skips_a_file_already_present_with_the_right_hash`, `test_a_hash_mismatch_leaves_no_file_behind`, `test_fetch_extracts_the_named_member_of_a_downloaded_zip`, `test_a_manifest_names_its_hdri_textures_and_models`, `test_every_asset_of_the_shipped_scene_is_pinned`, `test_the_page_never_copies_the_assets_directory_into_the_bundle`, `test_no_rust_source_embeds_the_assets_directory_outside_tests`
- [tests/test_bevy_bridge.py](../../../tests/test_bevy_bridge.py) — `test_the_hello_builds_the_backend_from_the_hello_calibration`, `test_the_hello_sensor_yamls_are_the_rendered_calibration`, `test_a_pair_before_any_hello_is_refused`, `test_a_pair_becomes_a_stereo_frame_with_png_payloads`, `test_the_status_counts_frames_posed_keyframes_and_dropped`, `test_closing_the_session_closes_the_backend_and_finishes_the_recorder`, `test_a_real_websocket_client_gets_a_status_for_its_pair`
- [tests/test_bevy_sim_rtabmap_e2e.py](../../../tests/test_bevy_sim_rtabmap_e2e.py) — acceptance (PRD 1–2): `test_the_sidecar_tracks_the_capture_and_builds_a_sparse_map`, `test_a_polygon_around_a_ground_truth_object_returns_its_dense_points`; a missing capture fixture fails, never skips.

## Background

`examples/bevy-sitl-poc` is a browser-only PoC (Bevy 0.18, WebGPU, Rapier, Feronia) with flat-colour
cuboids and a stereo rig whose frames never leave the page. The developer wants it photo-real, its
content loaded at runtime (a new GLB must not recompile the WASM — scenic-engine's content-directory
pattern), and its stereo streamed to RTAB-Map with proof that RTAB-Map can use it.

## State A (before)

- World hard-coded in `setup_world`; no textures, no shadows, no sky, no post-processing.
- Eye render targets have no `COPY_SRC`; nothing reads them; no network code.
- No ground-truth object boxes anywhere; no recorded Bevy capture.

## State B (after)

### Runtime content (`examples/bevy-sitl-poc/assets/`)

- `scene.json` — fetched at runtime (Bevy's HTTP asset reader on wasm, the file reader natively):

  ```json
  {"version": 1,
   "environment": {"hdri": "hdri/<name>.hdr|.ktx2", "sun_illuminance_lux": 100000.0,
                   "sun_elevation_deg": 38.0, "sun_azimuth_deg": 135.0, "fog_visibility_m": 450.0},
   "materials": {"asphalt": {"base_color": "textures/…", "normal": "textures/…",
                             "roughness": "textures/…", "uv_scale": 0.25}},
   "models": [{"id": "car-1", "glb": "models/<name>.glb", "position_enu": [3.0, 12.0, 0.0],
               "yaw_deg": 90.0, "scale": 1.0, "collider": "box", "ground_truth": true}]}
  ```

  Paths are relative to `assets/` (no absolute path, no `..`, models end `.glb`); ids are unique;
  `version` must be 1. ENU (x east, y north, z up) → Bevy `(x, z, -y)`.
- `assets.lock.json` — `{"assets": [{"path", "url", "sha256", "license": "CC0-1.0", "source",
  "member"?}]}`; `member` names the file inside a downloaded zip; `sha256` is the final file's.
  Every path `scene.json` references is pinned here. Fetched binaries are git-ignored.
- The page is served with `assets/` beside `dist/` (never copied into it, never `include_bytes!`d).

### Wire format (browser → bridge), little-endian

`u32 header_len · header (UTF-8 compact JSON, keys in this order) · payloads`

- hello: `{"type":"hello","calibration_id":"bevy-sitl-poc-v1","rate_hz":10.0,"calibration":{<StereoCalibration fields>},"objects":[{"id","kind","min_enu":[x,y,z],"max_enu":[x,y,z]}]}`, no payload.
- pair: `{"type":"pair","frame_id":n,"t_ns":n,"width":w,"height":h,"encoding":"gray8","pose_enu":[x,y,z,qx,qy,qz,qw]}`, then left then right, `w·h` bytes each.
- `pose_enu`: the rig centre; orientation takes the rig's forward-left-up body frame to ENU.
- Bridge → browser: JSON text `{"type":"status","frames":n,"posed":n,"lost":bool,"keyframes":n,"dropped":n}`.
- Goldens shared by both languages: `tests/fixtures/bevy_sim_wire/{hello,pair}.bin`.

### Rust modules (PoC)

- `scene_manifest.rs` — `SceneManifest::from_json`, `ModelInstance::bevy_transform`, `ManifestError`.
- `wire.rs` — `encode_hello`, `encode_pair`, `bgra_to_gray8` (row stride aware, BT.601 luma on the
  stored sRGB bytes), `rig_pose_enu`.
- `flight.rs` — `SurveyLoop::pose_at(t_s) -> FlightPose` (Bevy position + yaw): deterministic,
  ≤ 2 m/s, ≤ 30 °/s yaw, altitude 4–12 m, closed loop.

### Python (`src/surmap/simulation/`)

- `bevy_wire.py` — `decode_bevy_message`, `BevyHello`, `BevyPair`, `GroundTruthBox`, `BevyWireError`,
  `BridgeStatus`, `encode_status`.
- `bevy_capture.py` — `CaptureRecorder` (capture dir + `euroc/` export) and `load_bevy_capture`
  (`calibration.json`, `frames.jsonl` with `pose_enu`, `ground_truth.json`).
- `bevy_ground_truth.py` — `left_eye_optical_pose`, `project_box` (convex polygon in pixels).
- `trajectory_eval.py` — `align_rigid` (Umeyama, no scale), `RigidAlignment.apply`, `ate_rmse`.
- `sim_assets.py` — `AssetPin`, `load_asset_pins`, `fetch_assets`, `AssetHashMismatch`,
  `manifest_asset_paths`.
- `bevy_bridge.py` — `BevyStreamSession(backend_factory, recorder=None)` (`handle`, `close`) and
  `serve_bevy_bridge(host, port, session_factory)` on `websockets`.
- Scripts: `fetch_sim_assets.py`, `serve_bevy_sim.py`.

## Verification

- **V1** — acceptance `tests/test_bevy_sim_rtabmap_e2e.py` (real sidecar over the committed capture:
  posed ≥ 90 %, ATE RMSE ≤ 0.5 m, ≥ 3 keyframes, final graph, ≥ 2 000 points; polygon query around a
  ground-truth object → `ok`, ≥ 200 points, ≥ 80 % inside the box grown 0.5 m) and the lower-tier
  tests below. Re-run: `uv run python scripts/build_rtabmap_stream.py && SURMAP_REQUIRE_RTABMAP_STREAM_E2E=1 uv run pytest tests/test_bevy_sim_rtabmap_e2e.py -q`;
  `cd examples/bevy-sitl-poc && cargo test --locked`.
- **V4** (developer consented in the interview: "recorded live run in Chrome") — `scripts/serve_bevy_sim.py --record <dir>`,
  open `http://127.0.0.1:8772/?flight=survey-loop`, let one loop fly; record the bridge log's final
  status line and screenshots of the chase view and the eye feeds.
- Before: none of the modules exist; the PoC sends nothing. After: the above holds.

## Prerequisites

- Deferred-work scan (`src/surmap/docs/todo/`, `src/surmap/docs/code-issues/`): nothing in this
  path. `oversized-file-demo-server.md` / `oversized-file-demo-page.md` — unrelated (the bridge is a
  new module, not added to the demo server). No `deferred-answers/` records exist.
- Pre-existing: `tests/test_demo_controls.py::test_control_pauses_and_resumes_the_running_stream`
  is timing-flaky under full-suite load (passes alone) — not this change's.

## Decisions & Trade-offs

- **Bevy's own HTTP asset reader** over scenic-engine's RPC + `memory://` source: one crate, no TS
  host, same "content edit + reload" property (discovery companion).
- **Grey8 on the wire**: the sidecar works on grey; 4× less traffic than RGBA; colour stays on screen.
- **No SSAO** (unsupported on WebGPU in Bevy 0.18). **No TAA on the eyes**: per-frame jitter would
  shift features between left and right and between frames.
- **Committed capture ≤ 6 MB** instead of a release asset: CI needs no publish step.
- **Planned dependencies** (not a halt): `web-sys`/`js-sys` in the PoC crate for the WebSocket;
  Bevy features the realism needs (`tonemapping_luts`, `ktx2`, `zstd_rust`, `hdr` as required).
- The `survey-loop` flight drives the **simulated** drone kinematically inside the simulation; SurMap
  gains no flight-control path (architecture §1).

## Deferred Answers

Interview answers (2026-11-03): one PR via `/yolo #muse`; Muse also for exploration; screenshots of
improvements opened as work lands; live WebSocket + recorded session; CC0 assets fetched at build;
acceptance = recorded capture through the real sidecar + a recorded live run; GLBs added at runtime.

Developer instruction (2026-11-03): "code should be written by #muse too" — the Red row's test code
is written by Muse Code from the contracts in State B (an override of `muse-subagent`'s "red commits
stay with the main agent"); the planner wrote only the planning documents, the wire goldens and the
first Rust test modules (`wire.rs`, `scene_manifest.rs`, `flight.rs`), which Muse reviews and completes.
