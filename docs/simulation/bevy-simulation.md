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
| `scene.json` | `camera` (profile path), `environment` (HDRI, sun, haze, `sky_brightness`, `exposure_ev100`), `materials` (textured: `base_color`/`normal`/`arm` maps + `uv_scale`, or solid: `color`, roughness, metallic, reflectance, clearcoat), `elements`, `models`, and optionally `weather`, `fires`, `districts` and `building_fires` |
| `cameras/<id>.camera.json` | the stereo camera profile — the single source of truth for the renderer **and** RTAB-Map |
| `fx/<name>.fx.json` | one particle effect (flames, embers, smoke, rain) — see *Weather, wind and fire* |
| `species/<name>.species.json` | one vegetation species (pine, dry grass) — see *Weather, wind and fire* |
| `building/{facades,roofs,districts}/<name>.*.json`, `building/look.json`, `building/fire.json` | wall, roof and district presets, the buildings' look and the building fire's tuning — see *Buildings: presets, districts and building fires* |
| `assets.lock.json` | every fetched file: URL, SHA-256, licence (CC0-1.0), source page |

Element kinds the engine knows (positions are ENU metres at the element's base, yaw in
degrees): `box` (ground, roads, water, pads; optional `scatter` of debris and a
`ground_truth` kind), `collapsed_building` (slabs, tilt and a rubble fan laid out by `seed`),
`building` (a window grid and one material, or wall, roof and glazing presets — see *Buildings*), `person`, `vegetation` (a stand of one species). `models` are
glTF/GLB instances with a collider (`none` / `box` / `trimesh`) and an optional ground-truth
kind. The manifest is validated at load, by the renderer (`scene_manifest.rs`) and by the
station (`surmap.simulation.scenario_manifest`) with the same rules: version 1, unique ids
across elements, models, fires and building fires, known materials, relative asset paths, each
referenced file of the right kind (`.fx.json`, `.species.json`), and the ranges below.

Fetch the pinned assets (≈ 66 MB, git-ignored) with `uv run python scripts/fetch_sim_assets.py`.
All are CC0. From Poly Haven: textures `aerial_asphalt_01`, `rocks_ground_02`,
`brown_mud_03`, `concrete_floor_worn_001`, `white_plaster_02`; models
`concrete_road_barrier`, `old_tyre`, `Barrel_01`, `covered_car`; HDRI
`kloofendal_28d_misty_puresky`; and the building presets' textures (17 Poly Haven and 3
ambientCG sets, CC0). An ambientCG set is one zip, downloaded once per run however many of its
members are pinned; requests carry a `User-Agent` (ambientCG refuses urllib's default).

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
  wildfire's perimeter (a test pins it). Burning buildings' footprints fill it
  (*Buildings: presets, districts and building fires*).
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

## Buildings: presets, districts and building fires

A building's walls and roof are presets named after Overture's building attributes — the
`facade_material` and `roof_material` values of the `overture-buildings` layer the station's map
already shows (`src/surmap/agent/tools/map_layers.py`) — so a later import could map attributes
one to one. There is no Overture geometry import: buildings are still the manifest's boxes, by
the developer's choice. The agent styles a **district** (a rectangle with a weighted mix of
presets) and overrides single buildings. Buildings can burn: a fire climbs floor by floor, burns
each floor out, jumps to neighbours (farther downwind) and is lit by a wildfire that reaches
them. Every look and every coefficient is runtime JSON; a new preset is a new file.

Why this shape: preset names come from a vocabulary the station already speaks, and names are
only shorthand for shipped files, so the agent is never limited to what ships. `building_fires`
is a list apart from the wildfire `fires`: the ground fire is untouched, and both reach people
through the behaviour runtime's `burning_areas`.

### Preset files (`assets/building/`)

| File | Holds |
|---|---|
| `facades/<name>.facade.json` | `material` (a manifest material: textured with `uv_scale`, or solid), `colourable` (whether a building's `facade_colour` multiplies it), `glazing` (the default, below), `burnt` (the charred material) |
| `roofs/<name>.roof.json` | `material`, `colourable`, `burnt` |
| `districts/<name>.district.json` | weighted `facades`, `roofs` and `roof_shapes` (`[[name or path, weight], …]`, weights > 0), `facade_colours` / `roof_colours` palettes, `floor_m` (> 0), and optionally `window_ratio` (the glazed share of a facade cell, over the facade's own) and `ground_window_ratio` (the ground floor's — a shopfront) |
| `look.json` | the numbers no preset owns: `roof_shapes` (`flat`: `parapet_m` 0.6, `parapet_thickness_m` 0.25; `gabled` `pitch_deg` 35, `hipped` and `pyramidal` 30, each `eave_m` 0.3); `shopfront.floors` (1 — how many ground floors take `ground_window_ratio`); `interior` (`inset_m` 0.6, `colour` — the dark box behind the walls); and `fire`: `glow_inset_m` (0.5 — the glow plane behind a burning floor's windows), `soot` (`height_m` 1.5, `colour`, `alpha` 0.85 — the band above a burnt floor's windows) and `light` (`colour`, `lumens_per_floor` 600 000, `range_m` 70 — one point light per burning building at its top burning floor, no shadows) |
| `fire.json` | the fire's tuning (*The building fire model*, below), `effects` (`window_flames`, `smoke`, `embers` fx paths) and the window glow: `glow_colour` (`[1.0, 0.42, 0.10]`) × `glow_intensity` (3.5) |

**Glazing** — `kind` `punched` | `curtain_wall` | `none`:

| Field | Kind | Meaning (shipped) |
|---|---|---|
| `window_ratio` | punched | glazed share of each facade cell, in (0, 1] (0.30; a district's ratio wins) |
| `pane_m` `[w, h]`, `bay_m` | punched | pane size and cell width (1.4 × 1.6 m, 3.0 m) |
| `recess_m`, `frame_m` | punched | how far the pane sits behind the wall face (0.12 m); the frame's border around it (0.06 m) |
| `glass`, `frame` | punched | materials (dark glass, roughness 0.08, reflectance 0.5; grey frame) |
| `bay_m`, `mullion_m` `[w, h]`, `mullion` | curtain wall | mullion grid width (1.5 m × the floor height), mullion profile (0.08 × 0.08 m), metallic grey material |
| `spandrel_m`, `spandrel` | curtain wall | the opaque band at each slab (0.9 m) and its darker material |
| `glass` | curtain wall | the facade-wide glass (roughness 0.05, reflectance 0.6, metallic 0 — it mirrors the HDRI sky) |

A building's own `glazing` replaces its facade's; a kind the facade does not carry takes its
other fields from the shipped default of that kind (the `glass` facade is a curtain wall, the
others punched).

**Shipped names.** Facades `brick, cement_block, clay, concrete, glass, metal, plaster, plastic,
stone, timber, wood`; roofs `concrete, copper, eternit, glass, grass, gravel, metal, plastic,
roof_tiles, slate, solar_panels, tar_paper, thatch, wood` — every Overture value of each.
Colourable: facades `clay`, `metal`, `plaster`, `plastic`, `wood`; roofs `metal`, `plastic`.
Districts:

| District | Facades (weight) | Roofs (weight) | Shapes (weight) | `floor_m` | `window_ratio` |
|---|---|---|---|---|---|
| `old-town` | brick .4, plaster .35, stone .25 | roof_tiles .7, slate .3 | gabled .6, hipped .4 | 3.2 | 0.30 |
| `downtown` | glass .45, concrete .3, stone .15, metal .1 | concrete .4, gravel .4, metal .2 | flat 1 | 3.6 | 0.45, ground 0.8 |
| `industrial` | metal .5, cement_block .35, brick .15 | metal .6, eternit .4 | flat .5, gabled .5 | 5.0 | 0.15 |
| `suburban` | wood .4, plaster .3, plastic .2, brick .1 | roof_tiles .5, wood .3, slate .2 | gabled .6, hipped .4 | 2.8 | 0.30 |

A **name** (no `/`) means the shipped file of its kind; a **path**
(`building/facades/my-red.facade.json`) names any other file of that kind. The textures are 17
Poly Haven and 3 ambientCG CC0 sets at 2k, pinned in `assets.lock.json` and fetched with the
rest.

### In the manifest

```json
"districts": [{"id": "core", "preset": "downtown", "position_enu": [0, 0, 0], "size_m": [120, 80], "seed": 4}],
"elements": [{"kind": "building", "id": "tower-1", "size_m": [18, 18, 42], "position_enu": [30, 10, 0],
              "facade": "glass", "roof": "metal", "roof_shape": "flat", "floors": 12,
              "facade_colour": [0.55, 0.6, 0.65], "glazing": {"kind": "curtain_wall"}}],
"building_fires": [{"id": "blaze-1", "building": "tower-1", "floor": 3, "start_s": 5}]
```

- **Resolution** of each building's facade, roof, roof shape, colours, glazing and floors: the
  building's own field › the district whose rectangle holds the building's centre (later
  districts win overlaps), drawn by weight from an FNV-1a hash of the building's id mixed with
  the district's `seed` › the legacy `material` / `windows` › refused (*in no district: give it
  a material, or a facade and a roof*). `floors` defaults to `floor(height / floor_m)`, at
  least 1. A building with no preset and no district is drawn exactly as before.
- **Ranges.** District ids unique, `size_m` > 0; `roof_shape` `flat | gabled | hipped |
  pyramidal` (Overture's other shapes are refused — the agent maps them); colours three numbers
  in 0..1; `floors` ≥ 1; glazing `kind` known, `window_ratio` in (0, 1].
- **`building_fires`**: `building` an existing building id; `floor` counted from 0 at the
  ground, `0 ≤ floor < floors`; `start_s` ≥ 0; `tuning` a `.json` path (default
  `building/fire.json`); ids unique with every element, model and fire id. The renderer
  (`scene_manifest/buildings.rs`, `building_style.rs`, `building.rs`) and the station
  (`surmap.simulation.building_presets`) apply the same rules, except two the station cannot yet
  check and the renderer refuses at load: a floor beyond a floor count that comes from the
  district (`src/surmap/docs/todo/2026-11-04-building-fire-floor-from-district.md`), and a fire
  in a legacy, `material`-only building
  (`src/surmap/docs/todo/2026-11-04-legacy-buildings-burn.md`).

### The building fire model (`building_fire.rs`, pure, stepped)

`BuildingFires::new(footprints: Vec<Footprint { id, polygon_enu, floors }>, ignitions, tuning)`;
`step(t_s, dt, wind_enu, wildfires: &[FireSpec])`; `floor(id, f) -> FloorState::{Intact,
Burning, Burnt}`; `ignited_at(id)`; `burning_footprints()`. Deterministic for the same inputs
and `dt`; `actors.rs` steps it on the behaviour clock's fixed 10 Hz, with that tick's wind.

| `fire.json` field | Meaning (shipped) |
|---|---|
| `climb_s_per_floor` | from ignition floor f₀ at t₀, floor f above it ignites at t₀ + (f − f₀) · climb (45 s) |
| `descend_factor` | floors below ignite this many times slower (3) |
| `floor_burn_s` | a floor burns this long, then is `Burnt` (600 s) |
| `ignite_distance_m` | a burning building whose footprint is this close to B's ignites B … (4 m) |
| `ignite_wind_gain_s` | … plus this many metres per m/s of wind blowing from it toward B (1) … |
| `exposure_s` | … once within reach this long without a break (360 s); B ignites at the floor nearest the source's lowest burning floor |

A wildfire's burnt area touching a building's footprint ignites its floor 0 at that moment.
Burning buildings' footprints are the behaviour runtime's `World.burning_areas`, so `near_fire`
and `flee_from_fire` treat a burning building like a wildfire front. Only preset-styled
buildings burn.

### On screen

Layout: `building.rs` (which preset files to fetch, resolution once they load, the fire's
setup) and `building/{assets,look,spawn,walls,roofs,meshes,surface,fire_view}.rs`;
`building_style.rs` (the preset types, loaders and resolution). Each floor keeps its wall, frame,
pane, glow and soot meshes apart, so a fire changes one floor at a time.

- **Walls**: textured, tiled by world size; punched windows recessed with a frame and a dark
  interior behind, or a curtain wall of glass between spandrel bands and mullions.
- **Roofs**: `flat` with a parapet; `gabled` (ridge along the long axis), `hipped` and
  `pyramidal` with eaves. Parapets and gable ends take the facade material.
- **A burning floor**: panes hidden (broken), an emissive glow plane `glow_inset_m` behind every
  window, `window_flames` at each window (a curtain wall: along the whole band), and the wall
  band in the facade's `burnt` material. A burnt floor stays charred and gains soot above its
  windows; a fully burnt building's roof turns to the roof's `burnt` material.
- **Smoke** (`fx/building_smoke.fx.json`) rises from the top burning floor's windows and the
  roof as one dark plume bending downwind; **embers** are the wildfire's.
- **`emit_radius_m`**, a new optional fx field: particles start within this radius of their
  emitter (window flames 0.35 m, so they stay at their window; smoke 1.0 m); without it they
  spread over half the emitter spacing.

### Presets, ground truth and stills

The station's presets add `district-showcase` — the empty lot with the four districts side by
side (west to east: old-town, downtown, industrial, suburban; 50 × 70 m each, seed 1), six
generic buildings each, no fire — and `downtown-blaze` — a downtown block of eight buildings in
a 5 m/s westerly, a glass tower (`tower-1`, 12 floors, metal flat roof) alight on floor 3 at
t = 5 s, and a neighbour 5 m downwind.

A capture of a scene whose buildings can burn adds `building_fires.jsonl`, one line per frame:
`{"t_ns": n, "buildings": [{"id": "tower-1", "burning": [3, 4], "burnt": [2]}]}` (each building
with a floor alight or burnt out). `load_bevy_capture(dir).building_fires` reads it as `t_ns` →
id → `(burning, burnt)` floor tuples; it is empty without the file.

Stills: `--look-at <district id>` frames that district from the south (1.2 × its depth + 10 m
back, 0.9 × its depth up). Without it, a scene with building fires and no wildfire aims the
overview at the first fire's building from the south-west, and the rig's eye from 55 m south,
12 m up, at the ignition floor, and adds `fire-eye.png`.

### Verified

Rust tests pin the preset loaders and the name-or-path rules, the weighted resolution and its
determinism, every shipped preset parsing, the fire's climb, descent, burn-out, spread farther
downwind than upwind and wildfire ignition, the manifest rules and the golden
`tests/fixtures/sim_scenario/downtown-blaze.json` the station writes. Python tests pin
validation and edits, both presets, the six tools, the capture lines, an agent turn on a real
socket that sets a downtown glass tower alight with the tools, and the served `downtown-blaze`
preset being the golden the renderer validates.

The planner reviewed native stills against a visual spec. **D1** (`district-showcase` at t = 1,
one still per district) passed in one round: old-town reads as terracotta gables over brick and
plaster, downtown as glass curtain-wall and punched towers, industrial as low flat metal roofs,
suburban as pastel houses with tile and slate. **D2** (`downtown-blaze` at t = 15, 120, 400 and
900) took one round of JSON corrections: the window glow from near-white to 3.5 in orange,
window flames from dots to tongues, smoke from puffs to a continuous plume, and the neighbour's
ignition from 65 s to 364.9 s (`exposure_s` 360, `ignite_distance_m` 4). It then passed: at
t = 400 the fire has climbed every floor of the tower — orange floor bands under a smooth black
plume bending downwind; at t = 900 the lower floors are charred and burnt out, the top floors
burn and the neighbour is alight. Open work:
`src/surmap/docs/todo/2026-11-04-{building-texture-character,building-window-glow-variation,building-smoke-prewarm-stills,building-fire-floor-from-district,legacy-buildings-burn}.md`.

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
# ...with building fires (and no wildfire), the overview and fire-eye.png aim at the first one:
BEVY_ASSET_ROOT=$PWD cargo run --release -- --screenshot shots --at 400 --scenario downtown-blaze
# ...framing one district of the scenario:
BEVY_ASSET_ROOT=$PWD cargo run --release -- --screenshot shots --at 1 --scenario district-showcase --look-at old-town
# a stereo capture RTAB-Map can replay (hidden window, GPU readback, progress logged):
BEVY_ASSET_ROOT=$PWD cargo run --release -- --record cap --frames 90 --start 15.5 --jpeg \
  [--rate-hz 10] [--camera cameras/wide-baseline-pinhole.camera.json]
```

`--flight survey-loop` flies the deterministic rounded-rectangle loop over the block
(1.5 m/s, 7 ± 1.5 m up, ≤ 10.7 °/s yaw, 182 m, 121 s); stills and recordings imply it. A
capture holds `camera.json`, `calibration.json`, `ground_truth.json` (ENU boxes of every
ground-truth element and model), `frames.jsonl` (each frame's rig pose in ENU), grey8
frames, `object_tracks.jsonl` (the wind and every person with a behaviour tree), with
fires `fire_perimeter.jsonl`, and with buildings that can burn `building_fires.jsonl`; `surmap.simulation.bevy_capture.load_bevy_capture` reads it.

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
