# Bevy disaster simulation

A photo-real disaster block rendered by Bevy 0.18 (WebGPU in the browser, Metal/Vulkan
natively) with a stereo rig whose frames RTAB-Map consumes. Code:
`examples/bevy-sitl-poc`. Companion to the Gazebo/PX4 world ([disaster-world.md](disaster-world.md)):
no PX4, no ROS — a capture comes straight out of the renderer.

## Everything is data, loaded at runtime

Composing or changing a simulation never rebuilds the WASM. The page (or the native binary)
fetches, at runtime, from `examples/bevy-sitl-poc/assets/`:

| File | What it declares |
|---|---|
| `scene.json` | `camera` (profile path), `environment` (HDRI, sun, haze, `sky_brightness`, `exposure_ev100`), `materials` (textured: `base_color`/`normal`/`arm` maps + `uv_scale`, or solid: `color`, roughness, metallic, reflectance, clearcoat), `elements` and `models` |
| `cameras/<id>.camera.json` | the stereo camera profile — the single source of truth for the renderer **and** RTAB-Map |
| `assets.lock.json` | every fetched file: URL, SHA-256, licence (CC0-1.0), source page |

Element kinds the engine knows (positions are ENU metres at the element's base, yaw in
degrees): `box` (ground, roads, water, pads; optional `scatter` of debris and a
`ground_truth` kind), `collapsed_building` (slabs, tilt and a rubble fan laid out by `seed`),
`building` (with a window grid), `person`. `models` are glTF/GLB instances with a collider
(`none` / `box` / `trimesh`) and an optional ground-truth kind. The manifest is validated at
load: version 1, unique ids across elements and models, known materials, relative asset paths.

Fetch the pinned assets (≈ 66 MB, git-ignored) with `uv run python scripts/fetch_sim_assets.py`.
All are CC0 from Poly Haven: textures `aerial_asphalt_01`, `rocks_ground_02`,
`brown_mud_03`, `concrete_floor_worn_001`, `white_plaster_02`; models
`concrete_road_barrier`, `old_tyre`, `Barrel_01`, `covered_car`; HDRI
`kloofendal_28d_misty_puresky`.

## Look

Target: a real-looking block the morning after an earthquake — low sun through dust haze,
matte and desaturated, survivors' high-vis coats the only saturated colour.

- Tiled PBR with Poly Haven ARM maps (occlusion, roughness, metalness), tiled by world size;
  mip chains are built on the CPU when a JPG loads (Bevy builds none), so distant ground does
  not shimmer — on screen or in stereo matching.
- Sky and image-based light from the manifest's HDRI, baked to a cubemap at load and given to
  every camera as `Skybox` + `GeneratedEnvironmentMapLight`; the sun is aimed at the HDRI's
  brightest texel. Bevy 0.18's procedural `Atmosphere` is not used: it serves one camera only
  (its buffer is written from `Query::single`), and the chase view, both eyes and the review
  still must share one sky.
- Cascaded shadows, distance haze, AgX tonemapping, one fixed exposure on every camera (the
  eyes must match). TAA and bloom on the chase view only; the eyes use MSAA (no TAA jitter
  between left and right). No SSAO — unsupported on WebGPU in Bevy 0.18.

## Scenarios built by the agent, served by the station

The survey agent composes scenarios with its simulation tools ([docs/agent.md](../agent.md),
*Simulation tools*): it searches Poly Haven, ambientCG and Sketchfab, downloads CC0 / CC BY assets
into the station's library (SHA-256 recorded), and edits versioned scenarios — each one a
`scene.json` manifest — in the station's SQLite store. The agent server serves them on one
origin: `/sim/assets/scenarios/<id>.json`, the library under `/sim/assets/library/`, the PoC's
own assets under `/sim/assets/`, and the built page at `/sim/` (`--sim-dist`). The page opens a
scenario with `?scenario=<id>`; natively, `--scenario <id>` loads `scenarios/<id>.json` from
the asset root (ids are letters, digits and dashes).

## The stereo rig: one camera profile

`cameras/elp-stereo-pinhole.camera.json` (the SurMap ELP rig): 640×480, fx = fy = 381.36,
principal point (320, 240), baseline 0.07 m, 10 Hz, mounted 0.30 m forward, 0.10 m up,
pitched 35° down — at that pitch ground and objects sit 9–15 m away, where a 7 cm baseline
still has disparity to measure (at 30 m one pixel of disparity is ~36 m of depth).

- The eyes render through a projection built from the profile's exact intrinsics
  (off-centre principal point and fx ≠ fy are honoured, reverse-Z like Bevy's own).
- RTAB-Map's EuRoC `sensor.yaml` is derived from the same file
  (`surmap.simulation.camera_profile.profile_sensor_yaml`); for a pinhole profile it is
  exactly `render_cam_sensor_yaml`'s calibration.
- Models: `pinhole` and `fisheye_equidistant` (Kannala–Brandt k1–k4) are defined and their
  projections tested; fisheye rendering is not built yet and such a profile is refused at load.
- `cameras/wide-baseline-pinhole.camera.json` is the same rig at 0.30 m, for experiments.

## Running

```bash
export PATH="$HOME/.rustup/toolchains/stable-aarch64-apple-darwin/bin:$HOME/.cargo/bin:$PATH"
uv run python scripts/fetch_sim_assets.py
cd examples/bevy-sitl-poc
# browser (WebGPU): the page fetches assets/ from its own origin, so serve both together
trunk build index.html --release && ln -sfn ../assets dist/assets && python3 -m http.server 8772 -d dist
cargo run --release                          # native window
# review stills of the scripted survey loop (chase, left eye, overview):
BEVY_ASSET_ROOT=$PWD cargo run --release -- --screenshot shots --at 20
# a stereo capture RTAB-Map can replay (hidden window, GPU readback, progress logged):
BEVY_ASSET_ROOT=$PWD cargo run --release -- --record cap --frames 90 --start 15.5 --jpeg \
  [--rate-hz 10] [--camera cameras/wide-baseline-pinhole.camera.json]
```

`--flight survey-loop` flies the deterministic rounded-rectangle loop over the block
(1.5 m/s, 7 ± 1.5 m up, ≤ 10.7 °/s yaw, 182 m, 121 s); stills and recordings imply it. A
capture holds `camera.json`, `calibration.json`, `ground_truth.json` (ENU boxes of every
ground-truth element and model), `frames.jsonl` (each frame's rig pose in ENU) and grey8
frames; `surmap.simulation.bevy_capture.load_bevy_capture` reads it.

Verified natively (Metal) throughout; the browser build compiles for `wasm32` but the
runtime-scene version has not been checked in Chrome yet (visual checkpoint V5,
`src/surmap/docs/todo/2026-11-03-bevy-visual-checkpoints-v3-v5.md`).

Browser → RTAB-Map: the wire format (`src/wire.rs`, goldens in
`tests/fixtures/bevy_sim_wire/`) and the Python bridge (`surmap.simulation.bevy_bridge`)
exist and are tested; the wasm WebSocket client is not built yet
(`src/surmap/docs/todo/2026-11-03-bevy-live-websocket-stream.md`).

## What RTAB-Map makes of it (measured)

`tests/test_bevy_sim_rtabmap_e2e.py` streams the committed 90-frame block leg
(`tests/fixtures/bevy_sim_capture`) through the real sidecar in lockstep, anchors RTAB-Map's
map to ENU once from the first frame's camera pose (never re-fitted), and judges against
the truth:

| Check | Bound | Measured |
|---|---|---|
| Frames tracked | all, none dropped | 90/90 |
| Odometry drift over the 13.4 m leg | ≤ 4 % | 2.7 % |
| Dense points on the nearest framed object (camera frame) | median ≤ ¼ px of disparity at their depth | 0.33 m at 8.7 m (¼ px ≈ 0.71 m) |

Full 182 m loop (4 Hz, not yet a committed test): odometry closes to **1.48 m (0.81 %)**;
the map-corrected pose does not — see
`src/surmap/docs/todo/2026-11-03-sidecar-odometry-covariance.md` (the sidecar passes
RTAB-Map identity odometry covariance) and `2026-11-03-bevy-loop-closure-acceptance.md`.

Open work: `src/surmap/docs/todo/2026-11-03-*` (`bevy-*`, `camera-profile-*`, `sidecar-*`).
