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
| `scene.json` | `camera` (profile path), `environment` (HDRI, sun, haze, `sky_brightness`, `exposure_ev100`), `materials` (textured: `base_color`/`normal`/`arm` maps + `uv_scale`, or solid: `color`, roughness, metallic, reflectance, clearcoat), `elements`, `models`, and optionally `weather` and `fires` |
| `cameras/<id>.camera.json` | the stereo camera profile — the single source of truth for the renderer **and** RTAB-Map |
| `fx/<name>.fx.json` | one particle effect (flames, embers, smoke, rain) — see *Weather, wind and fire* |
| `species/<name>.species.json` | one vegetation species (pine, dry grass) — see *Weather, wind and fire* |
| `assets.lock.json` | every fetched file: URL, SHA-256, licence (CC0-1.0), source page |

Element kinds the engine knows (positions are ENU metres at the element's base, yaw in
degrees): `box` (ground, roads, water, pads; optional `scatter` of debris and a
`ground_truth` kind), `collapsed_building` (slabs, tilt and a rubble fan laid out by `seed`),
`building` (with a window grid), `person`, `vegetation` (a stand of one species). `models` are
glTF/GLB instances with a collider (`none` / `box` / `trimesh`) and an optional ground-truth
kind. The manifest is validated at load, by the renderer (`scene_manifest.rs`) and by the
station (`surmap.simulation.scenario_manifest`) with the same rules: version 1, unique ids
across elements, models and fires, known materials, relative asset paths, each referenced file
of the right kind (`.fx.json`, `.species.json`), and the ranges below.

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

## Weather, wind and fire

A scenario may carry weather, stands of pines and grass that sway in its wind, and wildfires
whose front spreads downwind as an animated fire. Rust implements only the *kinds* — a
particle emitter, the procedural pine and grass generators, the spread model; every number of
the look is runtime JSON, so tuning is a file edit, never a rebuild.

### In the manifest

```json
"weather": {"rain_mm_h": 0.0, "fog_visibility_m": 450.0,
            "wind": {"from_deg": 270.0, "speed_m_s": 6.0, "gust_m_s": 2.0}},
"fires": [{"id": "front-1", "ignition_enu": [-58.0, 60.0, 0.0], "start_s": 2.0,
           "spread_m_s": 0.15, "max_radius_m": 35.0, "smoke": true}],
"elements": [{"kind": "vegetation", "id": "pines-west", "species": "species/pine.species.json",
              "position_enu": [-40.0, 60.0, 0.0], "size_m": [40.0, 60.0],
              "density_per_100m2": 3.0, "seed": 11}]
```

| Field | Meaning (default) |
|---|---|
| `weather.rain_mm_h` | rain, ≥ 0 (0) |
| `weather.fog_visibility_m` | > 0; overrides `environment.fog_visibility_m` |
| `weather.wind` | `from_deg` — meteorological, where it blows **from**, clockwise from north (270 is a westerly, blowing toward +east); `speed_m_s` ≥ 0; `gust_m_s` ≥ 0 (0) |
| `weather.rain_fx` | the rain effect (`fx/rain.fx.json`) |
| `weather.wet_materials` | material keys that look wet while it rains (`["ground", "asphalt"]`) |
| `weather.wet_roughness`, `wet_darkening` | wet look: roughness × 0.6, colour × 0.85 (defaults) |
| `fires[].id` | shares the id namespace with elements and models |
| `fires[].ignition_enu`, `start_s` | where and when it ignites (`start_s` ≥ 0, default 0); nothing burns before |
| `fires[].spread_m_s`, `max_radius_m` | spread rate in still air (> 0); no point of the front is farther than `max_radius_m` (> 0) from the ignition |
| `fires[].smoke` | draw the plume (true) |
| `fires[].head_wind_gain`, `lb_wind_gain` | spread-model coefficients (0.5, 0.25) |
| `fires[].effects` | `{"flames", "embers", "smoke"}` — fx paths (the shipped `fx/*.fx.json`) |
| `vegetation` element | `species` (a `.species.json` path), `position_enu` (stand centre), `size_m` (east, north) > 0, `density_per_100m2` in (0, 50], `seed` |

### One wind (`wind.rs`)

The air moves toward `from_deg + 180°` at `speed_m_s + gust_m_s · sin(2π t / 7 s)`. That one
vector drives Feronia's `GlobalWind` (direction in Bevy xz, `strength = clamp(speed / 15, 0, 1)`,
each species damping it), the fire's spread, flame lean, and the drift of smoke, embers and rain.

### The fire model (`fire.rs`)

A Huygens ellipse with its rear focus at the ignition. With burning time τ = t − `start_s` and
wind speed U toward unit `d`: head rate `R = spread_m_s · (1 + head_wind_gain · U)`,
length-to-breadth `LB = 1 + lb_wind_gain · U`, back rate
`R_b = R (LB − √(LB² − 1)) / (LB + √(LB² − 1))`; semi-major `a = (R + R_b) τ / 2`, semi-minor
`b = a / LB`, centre `ignition + d (a − R_b τ)`, every axis capped at `max_radius_m` from the
ignition. Zero wind gives a circle of radius `spread_m_s · τ`. The front is sampled at 48 points
(ENU, counter-clockwise); a point is burnt once it is inside it.

### Effects (`fx/<name>.fx.json`, GPU particles with `bevy_hanabi`)

| Field | Meaning (default) |
|---|---|
| `colour_gradient` | `[[t, [r, g, b], intensity, alpha], …]` over the lifetime: ≥ 2 stops, `t` ascending in 0..1, sRGB with an HDR intensity |
| `size_m`, `lifetime_s` | `[start, end]` size; `[min, max]` lifetime |
| `motion` | `{"up": m/s, "wind_coupling": fraction of the wind added, "gravity": m/s²}` |
| `blend` | `additive` (flames, embers) or `alpha` (smoke, rain) |
| `spawn` | `{"per_metre": n}` of fire front, `{"per_second": n}`, or `{"per_mm_h": n}` per second per mm/h of rain |
| `max_particles` | the effect's particle budget |
| `shape`, `softness` | `quad` (default) or `soft_disc`: a radial-alpha disc generated at startup, `softness` 0 (hard edge) to 1 (0.5) |
| `round` | 0..1, rounds a quad toward an ellipse (0) |
| `stretch` | length over width along the velocity (1, a camera-facing quad); rain uses it for streaks |
| `box_m` | rain: the side of the box of air it fills around each viewing camera (60) |
| `emitter_spacing_m`, `refresh_s` | fire effects: one emitter per this many metres of front (2), re-placed every this many seconds (0.5) |
| `ground` | flames only — the burnt area: `height_m` above the terrain, `colour`, `roughness`, and the front's glowing rim `glow_width_m`, `glow_colour`, `glow_intensity` |
| `light` | flames only — one unshadowed point light per fire at the front's centroid: `colour`, `height_m`, `lumens_per_m` of perimeter, `range_m` |

Shipped: `flames` (additive soft discs stretched 1.8×, 1.0→2.6 m, 0.5–0.9 s, rising 2.5 m/s and
leaning with 0.6 × wind, 16 per metre of front; burnt ground near-black with a 1.5 m orange rim;
the glow light), `embers` (0.06 m sparks, 2–4 s, rising 3 m/s, falling back at 1 m/s², drifting
with the wind), `smoke` (alpha soft discs 3→16 m, 12–18 s, rising 1.8 m/s and drifting with the
wind, so plumes bend downwind), `rain` (streaks 0.015 m wide and 0.7 m long, falling 7 m/s plus
the wind, 141 per second per mm/h in a 60 m box). Rain, smoke, flames and embers render in the
eye cameras too — they are what a real stereo rig sees; bloom stays on the chase view.

### Vegetation (`species/<name>.species.json`, Feronia wind)

| Field | Meaning |
|---|---|
| `generator` | `pine` or `grass` — procedural meshes, no external models |
| `palette`, `burnt_palette` | sRGB stops (pines: bark first, then needles); a charred pine takes the burnt palette |
| `height_m` | `[min, max]`, drawn per plant from the stand's `seed` |
| `wind_damping` | multipliers on Feronia's `strength`, `micro_strength`, `s_curve_strength`, `bop_strength`, `twist_strength` |
| `lod_distance_m` | pines: the detailed mesh up to here, the far one beyond; grass: drawn up to here |
| `plants_per_unit` | plants per unit of `density_per_100m2` (1; grass clumps are small, so 30) |

Pines are entities on Feronia's wind material with a near and a far mesh. Grass is Feronia's
GPU-instanced scatter (`bevy_eidolon`): a stand of `n` clumps is scattered over a √n grid by
Feronia's one global `WorldSeed`, set from the stand's seed. Inside a fire's burnt area, checked
every 0.5 s, pines turn to bare charred trunks and grass instances are dropped. Shipped species:
`pine` (late-summer dry, 9–15 m, stiff) and `dry_grass` (0.45–0.85 m, full sway).

### Presets and ground truth

The station's presets (*Scenarios built by the agent*) add `wildfire-edge` — the empty lot
with dry grass, two pine stands, a 6 m/s westerly gusting 2 m/s, and a fire lit at the west
stand's upwind edge at t = 2 s — and `flood-street` — the earthquake block in 8 mm/h rain, 250 m
fog and a calm 2 m/s wind. A capture of a scene with fires adds `fire_perimeter.jsonl`, one
line per frame, `{"t_ns": n, "fires": [{"id": "front-1", "polygon_enu": [[x, y], …]}]}`;
`load_bevy_capture(dir).fire_perimeters` reads it by `t_ns` (empty without the file).

### Verified

Unit tests pin the wind and spread models, the fx and species loaders, the manifest rules in
Rust and Python, and the perimeter line on both sides; a golden `wildfire-edge` scenario written
by the station is parsed by the renderer's tests. The look was reviewed by the planner against
a visual spec in two rounds of native stills: wind-swept pines and grass, rain with fog and wet
surfaces, the smoke plume's drift and the burnt area with charred trunks pass; the flame front
reads as a saturated glow under the smoke, without resolvable tongues at survey distance
(`src/surmap/docs/todo/2026-11-03-flame-tongue-flipbook-sprites.md`). Open work:
`src/surmap/docs/todo/2026-11-03-{flame-tongue-flipbook-sprites,per-stand-grass-seed,fire-light-visibility,fire-perimeter-capture-end-to-end,fire-eye-mount-pitch}.md`.

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
# ...of a stored scenario; with fires, the overview looks at the first ignition and a
# fourth still, fire-eye.png, shows the fire through the rig's intrinsics from 40 m south, 15 m up:
BEVY_ASSET_ROOT=$PWD cargo run --release -- --screenshot shots --at 40 --scenario wildfire-edge
# a stereo capture RTAB-Map can replay (hidden window, GPU readback, progress logged):
BEVY_ASSET_ROOT=$PWD cargo run --release -- --record cap --frames 90 --start 15.5 --jpeg \
  [--rate-hz 10] [--camera cameras/wide-baseline-pinhole.camera.json]
```

`--flight survey-loop` flies the deterministic rounded-rectangle loop over the block
(1.5 m/s, 7 ± 1.5 m up, ≤ 10.7 °/s yaw, 182 m, 121 s); stills and recordings imply it. A
capture holds `camera.json`, `calibration.json`, `ground_truth.json` (ENU boxes of every
ground-truth element and model), `frames.jsonl` (each frame's rig pose in ENU), grey8
frames and, with fires, `fire_perimeter.jsonl`; `surmap.simulation.bevy_capture.load_bevy_capture`
reads it.

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
