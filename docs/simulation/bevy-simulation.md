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

## Behaviour trees

People in a scenario act by behaviour trees, and the wind has a tree of its own, so a scenario's
wind can veer and strengthen over time — and n3's vegetation, fire spread, flame lean and smoke
follow it through the one `WindModel`. A tree is inline JSON in the manifest: declaring or
changing one is a data edit, never a rebuild. Moving people are layered ground truth for the
survey; they are never written into the static scene or RTAB-Map's map
([architecture.md](../architecture.md) §1), and nothing here moves the drone.

Why this shape: a tree is inline JSON, not a node file, so one manifest stays the whole scenario
the station versions (reuse is the agent copying a tree). The runtime is hand-rolled (a few
hundred lines, pure) rather than a crate: the node set is small, determinism and `wasm32` are
required, and the tree must be the manifest's JSON. The wind is a target like a person, so a
wind driven by a tree needs no second mechanism.

### In the manifest

A `person` element takes `"behaviour": <node>`; the wind takes `weather.wind.behaviour` and
starts from the weather's `from_deg`, `speed_m_s` and `gust_m_s`. Every node is an object whose
`"node"` names its kind, with an optional `"id"` — unique within its tree, the address
`update_behaviour_node` edits by.

```json
{"kind": "person", "id": "evacuee-1", "position_enu": [-16.0, 52.0, 0.0],
 "coat": "coat_orange", "skin": "skin",
 "behaviour": {"node": "repeat", "child": {"node": "selector", "id": "root", "children": [
   {"node": "sequence", "id": "escape", "children": [
     {"node": "near_fire", "id": "smell-fire", "within_m": 20.0},
     {"node": "flee_from_fire", "id": "run", "speed_m_s": 3.0, "clearance_m": 30.0}]},
   {"node": "wander", "id": "mill-about", "radius_m": 6.0, "speed_m_s": 0.8, "seed": 7}]}}}
```

| Node | Fields | Ticks to |
|---|---|---|
| `sequence` | `children` | the first child that does not succeed; a running child holds the sequence on it; success when all succeed |
| `selector` | `children` | the first child that does not fail; children after it start afresh, so a higher choice that becomes possible again takes over |
| `parallel` | `children`, `succeed_on` `all` \| `one` | ticks every unfinished child each tick; `all`: failure on the first loss, success when all win; `one`: success on the first win, failure when all lose |
| `repeat` | `child`, `times` (omitted = forever) | restarts the child on success; fails when it fails |
| `invert` | `child` | swaps success and failure |
| `time_after` | `s` | success once simulation time ≥ `s`, else failure |
| `near_fire` | `within_m` | success when any burning front is within `within_m`, or the body stands in burning ground |
| `near_object` | `object`, `within_m` | success when the body named `object` is within `within_m` |
| `wind_above` | `speed_m_s` | success when the current wind speed exceeds it |
| `idle` | `s` | running for `s` seconds, then success |
| `move_to` | `enu` `[e, n]`, `speed_m_s` | running until within 0.25 m, then success |
| `follow_path` | `enu` `[[e, n], …]`, `speed_m_s` | `move_to` each point in turn |
| `wander` | `radius_m`, `speed_m_s`, `seed` | never ends: walks to seeded points (splitmix64) in the disc around where it started |
| `flee_from_fire` | `speed_m_s`, `clearance_m` | walks away from the nearest front point (out of burning ground first); success once `clearance_m` clear |
| `set_wind` | `from_deg`, `speed_m_s`, `gust_m_s`, `over_s` | ramps the wind linearly to these over `over_s`, the short way round the compass; success when reached |

- **Targets.** A person's tree may not use `set_wind`. The wind's tree may use only the
  composites, the decorators, `time_after`, `idle` and `set_wind`.
- **Ranges.** Composites non-empty; `times` ≥ 1; `within_m`, `idle.s`, every walking speed,
  `radius_m` and `over_s` > 0; `time_after.s`, `wind_above.speed_m_s`, `clearance_m` and the
  wind's `speed_m_s`/`gust_m_s` ≥ 0; every point finite; `seed` a whole number ≥ 0. Unknown kinds
  and fields are refused by name. The renderer (`behaviour/validate.rs`) and the station
  (`surmap.simulation.behaviour_tree`) apply the same rules.

### The tick (`behaviour.rs`, pure)

A fixed 10 Hz in simulation time, on the renderer's `SimTime`, so a recording replays
identically: same seeds, same tracks. Bodies move on the ground plane at their `speed_m_s`.
A root that finishes is not restarted — wrap it in `repeat`.

- `Tree` deserializes from the manifest's JSON (it is its root `Node`);
  `tree.validate(Target::Object | Target::Wind)` checks it.
- `Runner::new(tree, position: Vec2, wind: WindModel)`; `runner.tick(&World, dt)` →
  `Status::{Running, Success, Failure}`; `runner.position` (ENU m), `runner.wind`, and
  `runner.action()` — the running leaf's kind (`"flee_from_fire"`, …), `None` once finished.
- `World { t_s, fires: &[FireSpec], burning_areas: &[Vec<Vec2>], wind: &WindModel, objects:
  &[(String, Vec2)] }`. A wildfire's front is its perimeter sampled at 48 points; a point is
  burning when inside it (`FireSpec::burnt`).
- **`World.burning_areas` is a public seam.** It is other burning ground — ENU polygons such
  as burning buildings' footprints — that `near_fire` and `flee_from_fire` treat exactly like a
  wildfire's perimeter (a test pins it). This PR passes it empty; the building presets with fire
  (#104, n5 of `#sim-disaster-2`) fill it.
- Layout: `behaviour.rs` (node, tree and world types), `behaviour/validate.rs`,
  `behaviour/tick.rs` (each node's semantics and the `Runner`), `behaviour/geometry.rs` (the
  seeded wander stream, distances to fronts, containment).

`actors.rs` runs it in the app: every tick up to the simulation's moment, the wind's runner
first — its wind becomes `Wildfire::wind`, so this tick's vegetation, fire and particles see
it — then every person, each sensing the others' positions. A person faces the way it walks,
its yaw eased, and bobs while it walks; standing (`idle`, a finished tree) it does not.

### The figure (`assets/behaviour/person.figure.json`)

| Field | Meaning (shipped) |
|---|---|
| `yaw_ease_s` | seconds a turn takes to ease to the new heading, the short way round (0.3) |
| `bob_m` | height of a step's bob (0.03) |
| `steps_per_s` | steps per second at `reference_speed_m_s`; faster walking steps faster in proportion (2) |
| `reference_speed_m_s` | the speed `steps_per_s` is quoted at (1.4) |

Each figure's bob has its own phase, derived from its id. The figure itself is the capsule and
sphere every `person` has; it shows no front, so the turn is not visible yet
(`src/surmap/docs/todo/2026-11-03-figure-facing-cue.md`).

### Presets, ground truth and stills

The preset `wildfire-evacuation` is `wildfire-edge` plus three people in orange coats at the
west stand's downwind edge (`evacuee-1..3` at ENU (−16, 52/60/68), wander seeds 7–9), each
running the tree above — wander 6 m at 0.8 m/s; when the front comes within 20 m, flee at
3 m/s until 30 m clear; then wander again, and flee again if the front returns — and a wind
tree `sequence[idle 20 s, set_wind 300° 10 m/s gust 3 over 30 s]`: the 6 m/s westerly holds,
then veers and builds.

Every capture adds `object_tracks.jsonl`, one line per frame:
`{"t_ns": n, "wind_enu": [ve, vn], "objects": [{"id": "evacuee-1", "enu": [e, n, u], "action": "flee_from_fire"}]}`
— the wind's velocity and every person with a tree, sorted by id (`action` is `null` once its
tree finished). `load_bevy_capture(dir).object_tracks` (`t_ns` → id → `Vec3`) and `.wind`
(`t_ns` → `(ve, vn)`) read it; both are empty without the file.

A still of a scene with people adds `people.png` (1280×720, 50° field of view): from 25 m
south-west of the people's centroid and 12 m up, looking at their chests, following them while
the scene settles.

### Verified

Rust tests pin every node kind, determinism of a seeded wander, a fleeing person never inside
the burnt area over 120 s, burning ground in `burning_areas` fled like a front, the wind ramp
and its short way round, the manifest rules per target and the golden
`tests/fixtures/sim_scenario/wildfire-evacuation.json` the station writes; the figure's turn,
bob and track line. Python tests pin validation and edits, the preset, the three tools, the
capture tracks, and an agent turn on a real socket that gives a hiker and the wind their trees.
Native recordings of the preset, read with `load_bevy_capture`, show the evacuees wander and
then flee, the wind at 275° at 25 s and ≈ 287° at 36.9 s, and no evacuee inside the recorded
burnt area over 40–70 s. The planner reviewed native stills at t = 10 and t = 60 in two passes:
`people.png` at t = 60 frames the three evacuees in the grass, and the overview shows the front
pushed north-east by the veered wind. Open work:
`src/surmap/docs/todo/2026-11-03-figure-facing-cue.md`.

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
# ...with people, a fifth still, people.png, follows them from 25 m south-west, 12 m up:
BEVY_ASSET_ROOT=$PWD cargo run --release -- --screenshot shots --at 60 --scenario wildfire-evacuation
# a stereo capture RTAB-Map can replay (hidden window, GPU readback, progress logged):
BEVY_ASSET_ROOT=$PWD cargo run --release -- --record cap --frames 90 --start 15.5 --jpeg \
  [--rate-hz 10] [--camera cameras/wide-baseline-pinhole.camera.json]
```

`--flight survey-loop` flies the deterministic rounded-rectangle loop over the block
(1.5 m/s, 7 ± 1.5 m up, ≤ 10.7 °/s yaw, 182 m, 121 s); stills and recordings imply it. A
capture holds `camera.json`, `calibration.json`, `ground_truth.json` (ENU boxes of every
ground-truth element and model), `frames.jsonl` (each frame's rig pose in ENU), grey8
frames, `object_tracks.jsonl` (the wind and every person with a behaviour tree) and, with
fires, `fire_perimeter.jsonl`; `surmap.simulation.bevy_capture.load_bevy_capture` reads it.

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
