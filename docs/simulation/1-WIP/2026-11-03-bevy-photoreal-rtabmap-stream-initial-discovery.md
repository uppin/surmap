# Initial discovery — photo-real Bevy sim streamed to RTAB-Map

**Changeset:** `2026-11-03-bevy-photoreal-rtabmap-stream.md`
**Explored by:** Muse Code (`muse-wonder-1.0`, read-only sessions
`explore-bevy-rtabmap-202611031500`, `explore-scenic-engine-202611031510`), reviewed by the planner.

## Bevy PoC (`examples/bevy-sitl-poc`)

- Bevy 0.18.1 (`webgpu` + default features), bevy_rapier3d 0.33, bevy_feronia 0.8.4; trunk build
  from `index.html`; no `Trunk.toml`, no `assets/` directory.
- World is hard-coded cuboids in `setup_world` (`src/main.rs:146-293`): flat `StandardMaterial`
  colours, one `DirectionalLight` with **shadows off**, `AmbientLight` on the chase camera only,
  `ClearColor` sky, no post-processing, no textures.
- Stereo rig: two `Camera3d` rendering to 640×480 `Bgra8UnormSrgb` images
  (`render_target`, `src/main.rs:295-310`) without `COPY_SRC`; eyes follow the drone in
  `follow_drone_rig`. Nothing reads them back; `StereoCalibration::to_json()` is the declared
  "seam for the frame-export phase" (`src/calibration.rs:50-55`).
- Tests: 4 native cargo tests in `calibration.rs`. CI: `bevy-wasm-test.yml` (`cargo test --locked`),
  `bevy-wasm-build.yml` (`trunk build index.html --release`, asserts a >1 MB `*_bg.wasm`).
- Bevy 0.18.1 has `TemporalAntiAliasing`, `Bloom`, `DistanceFog`, `Atmosphere`,
  `EnvironmentMapLight`, `GeneratedEnvironmentMapLight`, `CascadeShadowConfigBuilder`,
  `Exposure`/`AutoExposure`, `Tonemapping::AgX`. **SSAO is documented as unsupported on WebGPU**
  (`bevy_pbr-0.18.1/src/ssao/mod.rs:119`) — excluded. No sensor-noise component exists.
- GPU→CPU: `bevy::render::gpu_readback::{Readback, ReadbackComplete}` (repeats each frame while
  the component stays) and `Screenshot` / `ScreenshotCaptured` (one-shot).
- Ground truth: `docs/simulation/gz/worlds/disaster_block_ground_truth.json` has people and roads
  only — **no object boxes**.

## Runtime asset reference (`~/Code/scenic-engine`)

Bevy 0.17 + wasm-pack. A content directory is served apart from the app bundle; a scene file lists
models by relative path; the host fetches bytes and Bevy spawns `SceneRoot(load("<src>://x.glb#Scene0"))`.
Adding a model is a content edit and a page reload — the WASM never changes. No physics, no HDRI,
minimal lighting. Pitfalls carried over: register custom asset sources before `AssetPlugin`; an SPA
fallback can answer a missing GLB with `index.html` (sniff it); same-path replacement does not
reload a loaded handle; use self-contained `.glb`.

Bevy's own WASM asset reader already fetches `assets/<path>` over HTTP, so in a single-crate trunk
app the scenic RPC + `memory://` layer is unnecessary: a JSON scene manifest fetched at runtime and
`AssetServer::load` with `meta_check: AssetMetaCheck::Never` gives the same property.

## RTAB-Map side

- `StreamingRtabmapBackend(cam0_yaml=…, cam1_yaml=…, width, height, max_depth_m, …)`
  (`src/surmap/slam/streaming.py:192`) drives the `surmap/rtabmap-stream:<hash>` sidecar
  (protocol v5). `process_frame(StereoFramePair)` takes `left_data`/`right_data` bytes or file refs;
  `poll_updates()`, `trajectory()`, `map_snapshot()`, `keyframe_count`, `frame_odometry()`,
  `region_points(RegionQuery)`, `flush()`.
- Calibration → EuRoC yaml: `StereoCalibrationSpec` + `render_cam_sensor_yaml`
  (`src/surmap/simulation/calibration.py`); capture dir loader `load_sitl_capture`
  (`sitl_capture.py`, `calibration.json` + `frames.jsonl` + images); `export_euroc_session`.
- Real-sidecar tests skip unless the image (`stream_image_tag()`) and fixture exist; CI job
  `rtabmap-stream-e2e` builds the image and sets `SURMAP_REQUIRE_RTABMAP_STREAM_E2E=1`.
  Local image `surmap/rtabmap-stream:61d6cc8249a6` matches the current tag.
- `websockets` 17.3 is already a runtime dependency; the demo server is stdlib `http.server`.

## Baseline (de8cab0)

ruff ✅ · format ✅ · mypy ✅ (369 files) · pytest: `1 failed, 719 passed, 2 skipped` at `-x` —
`tests/test_demo_controls.py::test_control_pauses_and_resumes_the_running_stream`, timing-flaky
under full-suite load, passes in isolation. Pre-existing, not this change's.
