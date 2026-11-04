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
| `vehicle/<class>.vehicle.json` | one vehicle class: glTF, size, wheels, driving limits, carriages — see *Vehicles* |
| `assets.lock.json` | every fetched file: URL, SHA-256, licence (CC0-1.0, or CC-BY with its `attribution`), source page |

Element kinds the engine knows (positions are ENU metres at the element's base, yaw in
degrees): `box` (ground, roads, water, pads; optional `scatter` of debris and a
`ground_truth` kind), `collapsed_building` (slabs, tilt and a rubble fan laid out by `seed`),
`building` (a window grid and one material, or wall, roof and glazing presets — see *Buildings*), `person`, `vegetation` (a stand of one species), `vehicle` (a car, bus, truck or train that drives — see *Vehicles*). `models` are
glTF/GLB instances with a collider (`none` / `box` / `trimesh`) and an optional ground-truth
kind. The manifest is validated at load, by the renderer (`scene_manifest.rs`) and by the
station (`surmap.simulation.scenario_manifest`) with the same rules: version 1, unique ids
across elements, models, fires and building fires, known materials, relative asset paths, each
referenced file of the right kind (`.fx.json`, `.species.json`), and the ranges below.

Fetch the pinned assets (≈ 66 MB, git-ignored) with `uv run python scripts/fetch_sim_assets.py`.
From Poly Haven (CC0): textures `aerial_asphalt_01`, `rocks_ground_02`,
`brown_mud_03`, `concrete_floor_worn_001`, `white_plaster_02`; models
`concrete_road_barrier`, `old_tyre`, `Barrel_01`, `covered_car` (pinned, no longer placed); HDRI
`kloofendal_28d_misty_puresky`; and the building presets' textures (17 Poly Haven and 3
ambientCG sets, CC0). An ambientCG set is one zip, downloaded once per run however many of its
members are pinned; requests carry a `User-Agent` (ambientCG refuses urllib's default).
From the Khronos glTF-Sample-Assets, pinned at commit `8f492390`, one CC-BY-4.0 model whose
pin carries its credit (`attribution` in `assets.lock.json`; a test refuses a CC BY pin
without one): **Car Concept** by Eric Chadwick, Darmstadt Graphics Group GmbH (the scene's
cars). Poly Haven has no uncovered car and no human, and a Sketchfab download needs a token
and gives a signed URL no lock can pin. The people are two CC0 Quaternius characters from Poly
Pizza (`models/person/wave.glb`, `sit.glb`), pinned with the animation names the tests read.

From Poly Pizza, one CC-BY-3.0 model, by a developer decision of 2026-11-04 (no CC0 bus can be
pinned): the bus (`models/poly-pizza/bus.glb`, the `bus` vehicle class), credited as *"Bus" by
Poly by Google, https://poly.pizza/m/4CPpvEmrMoF, CC BY 3.0
(https://creativecommons.org/licenses/by/3.0/)* in its lock entry. The model is
authored at 157 × 50 × 49 units, not metres, so its class file scales it by `model_scale` 0.07 to
11.0 × 3.5 × 3.4 m.

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

For local development `./scripts/dev.sh` serves the page by default and ensures its
prerequisites before anything starts: `uv` and `yarn` on PATH, the chat UI's
`node_modules`, the pinned textures, models and HDRI fetched and hash-verified
(`scripts/fetch_sim_assets.py`), and a page build whose JS/WASM are addressed under
`/sim/` — rebuilt with `trunk build --public-url /sim/` when the build is missing or
was made for another prefix, since root-addressed assets 404 under `/sim/` and leave
a black canvas. `SURMAP_DEV_SIM_DIST` and `SURMAP_DEV_SIM_FETCH_CMD` override the
page location and the fetch command.

## Controls

Keyboard flies the drone (Space take off/land, WASD move, Q/E yaw, R/F up/down).
The chase view follows the viewed drone, and the trackpad orbits it (PTZ):
two-finger scroll pans and tilts the view around the drone (tilt clamped between
horizon and top-down), pinch zooms between 3 m and 40 m (`view_orbit.rs`, fed by
`MouseWheel` and `PinchGesture`). With no gesture input the view is the original
chase view, so unattended screenshot and record modes are unchanged.
### The map as the floor

A scenario may be based on the real map: `set_map_floor` takes a GPS bounding box (south-west
and north-east corners), the station stitches OpenStreetMap raster tiles cropped to that box
into one PNG, and the manifest gains `map_floor {sw, ne, texture, zoom}`. Tiles are disk-cached
(`tile-cache/` in the library; `SURMAP_TILE_URL_TEMPLATE` / `SURMAP_TILE_CACHE_DIR` repoint the
server or the cache for offline use), and the stitched texture — zoom at most 18, at most 64
tiles, at most 4 096 px a side — is shared between scenarios under its content hash in
`library/map-floor/`. © OpenStreetMap contributors is credited in the scenario's credits.

The floor replaces the ground, it does not lie under it: `set_map_floor` removes the preset
`ground` box (its opaque top at 0 m would hide the floor), `clear_map_floor` restores it, and
the renderer draws the floor as one untiled plane at the ENU origin sized from the bbox, with
a fixed collider whose top is at 0 m — the floor is what people, vehicles and nests stand on.
Its texture gets the mip chain every asset-server image gets, so it does not shimmer from
altitude. The ENU origin is the bbox centre (111 320 m per degree of latitude, longitude scaled
by cos(latitude) — the semantic snapshot's rule). The agent never converts GPS itself:
`geo_to_enu` turns a lat/lon into the ENU the placement tools take (and says whether it lies
inside the floor), `enu_to_geo` converts back, and `set_map_floor` warns when re-basing moves
already-placed elements or leaves one outside the floor. A floor is at most 1 000 m a side.
The floor is flat and printed: it gives the stereo rig no ground depth of its own — the placed
objects supply the 3D — and it is display geometry only, never a control signal.

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
| `stretch` | length over width along the velocity (1, a camera-facing quad); rain uses it for streaks. A flipbook effect keeps 1: stretching orients the quad along its velocity and would lay the sprite on its side |
| `flipbook` | `{"texture", "columns", "rows", "fps"}` — animate each particle through a sprite sheet (`textures/fx/*.png`, pinned in `assets.lock.json`) of `columns` × `rows` frames at `fps`, each particle starting at a phase its lifetime picks; the sheet replaces `shape`. Absent: `shape` is drawn |
| `prewarm_s` | screenshot mode only: seconds the effect is advanced before a still, so a plume is as old as the scene it is shot in (0; ≥ 0) |
| `box_m` | rain: the side of the box of air it fills around each viewing camera (60) |
| `emitter_spacing_m`, `refresh_s` | fire effects: one emitter per this many metres of front (2), re-placed every this many seconds (0.5) |
| `ground` | flames only — the burnt area: `height_m` above the terrain, `colour`, `roughness`, and the front's glowing rim `glow_width_m`, `glow_colour`, `glow_intensity` |
| `light` | flames only — one unshadowed point light per fire at the front's centroid: `colour`, `height_m`, `lumens_per_m` of perimeter, `range_m` |

Shipped: `flames` (additive flame tongues from the `flame_tongues.png` flipbook — OpenGameArt
"Animated Fire", CC0, 10 × 6 frames of 64 px at 30 fps — upright (`stretch` 1), 1.0→2.6 m,
0.5–0.9 s, rising 2.5 m/s and leaning with 0.6 × wind, 16 per metre of front, the gradient's HDR
intensities at most 1.2 so the tongues resolve instead of washing out; burnt ground near-black
with a 1.5 m orange rim; the glow light), `embers` (0.06 m sparks, 2–4 s, rising 3 m/s, falling
back at 1 m/s², drifting with the wind), `smoke` (alpha soft discs 3→16 m, 12–18 s, rising
1.8 m/s and drifting with the wind, so plumes bend downwind; pre-warmed 18 s), `rain` (streaks 0.015 m wide and 0.7 m long, falling 7 m/s plus
the wind, 141 per second per mm/h in a 60 m box). Rain, smoke, flames and embers render in the
eye cameras too — they are what a real stereo rig sees; bloom stays on the chase view.

**Pre-warm in stills (`prewarm.rs`).** Hanabi has no pre-warm, so in screenshot mode, once the
scene is ready and its emitters exist, the one global effect clock (`Time<EffectSimulation>`, not
the simulation's clock) is sped up — at most 0.2 s of effect time per rendered frame, so emitted
particles stay a continuous plume rather than clumps — until the longest `prewarm_s` among the
loaded effects has passed; then it returns to real time and the still's settle wait restarts.
Effects without a pre-warm (short-lived flames) are in their steady state either way. Shipped
smokes pre-warm at least their longest lifetime: `smoke` 18 s, `building_smoke` 25 s.

### Vegetation (`species/<name>.species.json`, Feronia wind)

| Field | Meaning |
|---|---|
| `generator` | `pine` or `grass` — procedural meshes, no external models |
| `palette`, `burnt_palette` | sRGB stops (pines: bark first, then needles); a charred pine takes the burnt palette |
| `height_m` | `[min, max]`, drawn per plant from the stand's `seed` |
| `wind_damping` | multipliers on Feronia's `strength`, `micro_strength`, `s_curve_strength`, `bop_strength`, `twist_strength` |
| `lod_distance_m` | pines: the detailed mesh up to here, the far one beyond; grass: drawn up to here |
| `plants_per_unit` | plants per unit of `density_per_100m2` (1; grass clumps are small, so 30) |

Pines are entities on Feronia's wind material with a near and a far mesh. Grass is
GPU-instanced (`bevy_eidolon`) on Feronia's wind material, so it sways: where each clump stands is
`vegetation::grass_instances(stand, def) -> Vec<Vec2>` (ENU), a pure function of the stand — its
own `seed`, rectangle and density — and the species' `plants_per_unit`, and each clump's yaw and
height are drawn from the same seed. The renderer instances exactly these, replacing Feronia's
global-seed scatter (Feronia only makes the batch), so no global seed decides a stand's grass. Inside a fire's burnt area, checked
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
first read as a saturated glow without resolvable tongues at survey distance. The sweep
([changelog/2026-11-04-sim-disaster-2-sweep.md](changelog/2026-11-04-sim-disaster-2-sweep.md)) gave the flames the flipbook tongues, each grass stand its own seed (a sway of
3.2 mean absolute pixel difference between t = 5 and t = 6), and the fire perimeter an end-to-end
recording; its light-on / light-off still pairs were indistinguishable in daylight, so the fire
lights keep their values — they matter at dusk and night only. Open work:
`src/surmap/docs/todo/2026-11-03-fire-eye-mount-pitch.md`,
`src/surmap/docs/todo/2026-11-04-flame-flipbook-resolution.md`.

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
| `bob_m` | height of a step's bob (0.03); applied to the capsule figure only, since a rig's clips carry the gait |
| `steps_per_s` | steps per second at `reference_speed_m_s`; faster walking steps faster in proportion (2) |
| `reference_speed_m_s` | the speed `steps_per_s` is quoted at (1.4) |
| `visor` | optional `{"size_m", "offset_m", "colour"}`: a box on the figure (`size_m` x, y, z in the figure's frame; `offset_m` from its feet, −z its front; solid sRGB `colour`). Shipped 0.18 × 0.05 × 0.06 m, 1.63 m up and 0.12 m forward, near-black; drawn on the capsule figure only |
| `model` | optional `{"glb", "scale", "yaw_deg", "clip_s", "coat_tint", "rig"}`: a humanoid glTF worn instead of the capsule, scaled and turned to stand on the feet facing −z. Without a `rig` it is posed from its first clip (held at `clip_s` standing, played in step walking); with one, its named clips play (below). `coat_tint` multiplies its colours by the person's `coat`. Shipped `models/person/wave.glb` (Quaternius, CC0), scale 1, 180°, rigged |
| `model.rig` | `clips` (`idle`, `walk`, `run` required; `wave`, `sit`, `lie` the poses this file carries) → the glTF's animation names; `walk_ground_m_s` / `run_ground_m_s`, the ground each clip covers per second at rate 1 (no foot slide); `run_above_m_s`, where walking crosses to running; `blend_s`, the crossfade; `standing_height_m`, the rig's height at scale 1; `coat_slots` / `skin_slots`, the glTF material names that take the person's `coat` / `skin`. Shipped: idle, walk, run, wave, and `Death` as `lie`; 1.1 / 2.5 m/s, run above 1.8 m/s, 0.3 s, 1.8 m, coat on the shirt (`White`) |
| `pose_models` | optional `{pose: model}`: a pose drawn on its own rigged model, because no single CC0 file carries every clip. Never `standing`, which the figure's `model` carries. Shipped `sitting` → `models/person/sit.glb` (Quaternius, CC0, `SitIdle`), scale 0.346, coat-tinted |
| `body_m` | the `person` ground-truth box (east, north, up) over the feet, holding the body whatever way it faces (0.6 × 0.6 × 1.8 m) |

`FigureDef::from_json` refuses a figure where some pose has no clip in `model` or in its
`pose_models` entry, and `the_shipped_figure_has_a_clip_for_every_pose_in_a_pinned_file` checks
the shipped clip names against the `animations` that `assets/assets.lock.json` records for each
pinned file. CI does not fetch models, so it checks the same names.

**Poses and clips (`figure_anim.rs`, pure).** A person's `pose` is `standing` (the default),
`sitting`, `waving` or `lying`. `locomotion(rig, speed, pose)` gives weighted clips with their
rates. Standing still plays `idle`, walking plays `walk` at `speed / walk_ground_m_s`, and the walk
crossfades to `run` around `run_above_m_s`. A posed person who stands still plays the pose clip:
`wave` loops, while `sit` and `lie` are held at their last frame. A posed person with a tree walks
while it moves. `clip_time(now, phase, rate, duration)` uses the per-id phase (`phase_of`), so a
crowd is not in step. The app builds one `AnimationGraph` per rig file (`actors/rig.rs`) and seeks
every `AnimationPlayer` to its clip time from `SimClock` each frame. Players never free-run, so a
still at `--at t` and a recording replay exactly. A person's `height_m` (0.9–2.2) scales the rig
and its ground speeds (`RigDef::at_height`), their `glb` replaces the model file, and their `yaw_deg`
faces a posed person.

Each figure's bob has its own phase, derived from its id. Without a `model` the figure is the
capsule and sphere every `person` is built with (`FallbackBody`), plus the visor on the front of its head
(`actors::attach_visors`), so the way it faces and turns reads ([sweep](changelog/2026-11-04-sim-disaster-2-sweep.md)).
With one (`actors::attach_bodies`, once the look has loaded) the capsule is dropped for the
humanoid. A missing model file (assets not fetched) keeps the capsule, so a checkout without
assets still renders people. Either way, every survivor enters `ground_truth.json` as a `person`
box. A posed person is tracked in `object_tracks.jsonl` even without a tree, with its `pose`, and a
lying person's truth box is horizontal: `body_m`'s height laid along its `yaw_deg`, 0.3 m thick
(`posed_person_truth`) ([changelog](changelog/2026-11-04-sim-rigged-people.md)).

### Presets, ground truth and stills

The preset `wildfire-evacuation` is `wildfire-edge` plus three people in orange coats at the
west stand's downwind edge (`evacuee-1..3` at ENU (−16, 52/60/68), wander seeds 7–9), each
running the tree above — wander 6 m at 0.8 m/s; when the front comes within 20 m, flee at
3 m/s until 30 m clear; then wander again, and flee again if the front returns — and a wind
tree `sequence[idle 20 s, set_wind 300° 10 m/s gust 3 over 30 s]`: the 6 m/s westerly holds,
then veers and builds.

The preset `earthquake-survivors` is the earthquake block with its seven standing survivors
replaced by five people in the poses a survey looks for: `survivor-lying` on open ground south of
`collapsed-0`, `survivor-sitting` on the rubble of `collapsed-2`, `survivor-waving` facing the
route by `collapsed-3` (yellow coats, 1.7–1.75 m), and `rescuer-1`/`rescuer-2` in orange walking
a `follow_path` between them. The station writes it as the golden
`tests/fixtures/sim_scenario/earthquake-survivors.json`, which Rust parses
([decision](deferred-answers/2026-11-04-earthquake-survivors-cast.md)).

Every capture adds `object_tracks.jsonl`, one line per frame:
`{"t_ns": n, "wind_enu": [ve, vn], "objects": [{"id": "evacuee-1", "enu": [e, n, u], "action": "flee_from_fire", "kind": "person", "yaw_deg": 92.0}]}`
— the wind's velocity and every person with a tree and every tracked vehicle (*Vehicles*),
sorted by id, plus every posed person with or without a tree, which also carries `"pose"`. `action` is `null` once its tree has finished, `kind` is `person` or the
vehicle's class, and `yaw_deg` is the way it faces (ENU, counter-clockwise from east). `load_bevy_capture(dir).object_tracks` (`t_ns` → id → `Vec3`) and `.wind`
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
pushed north-east by the veered wind. The figure's front cue followed in the sweep
([changelog/2026-11-04-sim-disaster-2-sweep.md](changelog/2026-11-04-sim-disaster-2-sweep.md)): the close still `person-close.png` shows the visor on the front of the head.

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
| `look.json` | the numbers no preset owns: `roof_shapes` (`flat`: `parapet_m` 0.6, `parapet_thickness_m` 0.25; `gabled` `pitch_deg` 35, `hipped` and `pyramidal` 30, each `eave_m` 0.3); `shopfront.floors` (1 — how many ground floors take `ground_window_ratio`); `interior` (`inset_m` 0.6, `colour` — the dark box behind the walls); and `fire`: `glow_inset_m` (0.5 — the glow plane behind a burning floor's windows), `soot` (`height_m` 1.5, `colour`, `alpha` 0.85 — the band above a burnt floor's windows), `light` (`colour`, `lumens_per_floor` 600 000, `range_m` 70 — one point light per burning building at its top burning floor, no shadows), `glow_variation` (0.5 — each window's glow is scaled within `1 ± glow_variation`, seeded per window) and `glow_flicker_hz` (1.5 — how fast it flickers) |
| `fire.json` | the fire's tuning (*The building fire model*, below), `effects` (`window_flames`, `smoke`, `embers` fx paths) and the window glow: `glow_colour` (`[1.0, 0.32, 0.05]`) × `glow_intensity` (0.8) — the glow is unlit, and above about 1 it desaturates, so the brightest windows (× 1.5) stay a saturated orange |

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
Poly Haven and 5 ambientCG CC0 sets at 2k, pinned in `assets.lock.json` and fetched with the
rest: among them `cement_block` takes ambientCG `PavingStones125A`, `copper` the verdigris
`Metal058C`, `plastic` Poly Haven `brown_planks_05` (lap siding), `wood` ambientCG
`WoodSiding009` (clapboard) and `eternit` Poly Haven `asbestos_sheet_02` (fibre-cement corrugate).
Neither source has a CC0 grey CMU or white PVC set
(`src/surmap/docs/todo/2026-11-04-cmu-and-pvc-textures.md`), and the `uv_scale` of `timber`,
`roof_tiles` and `slate` is counted from the texture rather than measured
(`src/surmap/docs/todo/2026-11-04-texture-uv-scale-measured.md`).

**Metalness of roughness-only sets.** ambientCG sets ship a greyscale roughness map and no ARM
map, and Bevy reads metalness from a metallic-roughness texture's blue channel. On load, such a
map is repacked by `textures::pack_metallic_roughness(roughness_rgba, metallic) -> rgba` (R 255,
G the roughness, B the preset's `metallic` · 255, A 255) before its mips are built, and the
material's `metallic` factor is 1, so a roughness-only set keeps its preset's `metallic` (copper
0.8). A file shared by two sets takes the last set's value.

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
  (`surmap.simulation.building_presets`) apply the same rules. A floor count that comes from the
  district is checked too: `add_building_fire(manifest, id, *, building, floor, start_s=0,
  assets_dir=None)`, given `assets_dir`, gives a building without `floors` the
  `floor(height / floor_m)` of the district holding its centre (later districts win) and refuses
  a floor past it; the store passes its `assets_dir`, so the `add_building_fire` tool answers
  `INVALID_ARGUMENT`. A district preset the station cannot read is left to the renderer, which
  refuses it at load. One rule only the renderer checks: a fire in a legacy, `material`-only
  building (`src/surmap/docs/todo/2026-11-04-legacy-buildings-burn.md`).

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
- **A burning floor**: panes hidden (broken), an unlit glow plane `glow_inset_m` behind every
  window, each window its own vertex colour rewritten every frame from
  `FireLook::window_glow(building_seed, window, t_s)` — in `[1 − v, 1 + v]` for `glow_variation`
  v, seeded per window (FNV-1a of the building id, splitmix64 of the window), flickering at
  `glow_flicker_hz` — so the panes read as distinct orange windows, not one band; `window_flames` at each window (a curtain wall: along the whole band), and the wall
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
burn and the neighbour is alight. The sweep ([changelog/2026-11-04-sim-disaster-2-sweep.md](changelog/2026-11-04-sim-disaster-2-sweep.md)) then gave the facades their
spec's character with metalness kept, each window its own flickering glow (review round 1:
`glow_variation` 0.5, colour `[1.0, 0.32, 0.05]`, intensity 0.8 — distinct saturated orange
panes), pre-warmed smoke in stills, district-resolved floors in the station and a recorded blaze
end to end. Open work:
`src/surmap/docs/todo/2026-11-04-{legacy-buildings-burn,cmu-and-pvc-textures,texture-uv-scale-measured}.md`.

## Vehicles

Cars, buses, trucks and trains drive, and boats and ships sail on water (*Boats and ships*). Each is a `vehicle` element of a class: a pinned glTF,
moved by the same behaviour trees people use (*Behaviour trees*), with speed, acceleration,
braking and turning limited the way a real vehicle's are. A train runs as a locomotive with
carriages trailing it along its path. Moving vehicles are layered ground truth for the survey,
recorded per frame in `object_tracks.jsonl`. They are never written into `ground_truth.json`,
the static scene or RTAB-Map's map ([architecture.md](../architecture.md) §1).

Why this shape: one motion mechanism. The trees are already validated by the station and the
renderer and already editable by the agent's tools, so a vehicle is just a body that cannot turn
on the spot. The trees stay target-agnostic, and `Drive` limits whatever they propose. Trains
follow their path, not a rail graph, so there is no switching and no collision.

### In the manifest

```json
{"kind": "vehicle", "id": "bus-cross-1", "class": "bus", "position_enu": [-45.0, 62.5, 0.0],
 "tint": [1.0, 0.78, 0.1],
 "behaviour": {"node": "repeat", "child": {"node": "sequence", "children": [
   {"node": "follow_path", "enu": [[45.0, 62.5]], "speed_m_s": 8.0},
   {"node": "idle", "s": 10.0},
   {"node": "follow_path", "enu": [[-45.0, 62.5]], "speed_m_s": 8.0}]}}}
{"kind": "vehicle", "id": "freight", "class": "train", "cars": 6, "yaw_deg": 90.0,
 "position_enu": [-62.0, -50.0, 0.0], "behaviour": {"node": "follow_path", "enu": [[-62.0, 140.0]], "speed_m_s": 15.0}}
```

| Field | Meaning |
|---|---|
| `class` | `car` \| `bus` \| `truck` \| `train` \| `boat` \| `ship`; picks `vehicle/<class>.vehicle.json` |
| `position_enu`, `yaw_deg` | the start pose (yaw counter-clockwise from east, as for `models`) |
| `behaviour` | optional tree, validated as a ground body's (no `set_wind`); parked without one |
| `glb` | optional override of the class glTF (a relative asset path, `.glb` / `.gltf`), e.g. a station-library asset |
| `cars` | trains only: carriages behind the locomotive (default 0; refused on any other class) |
| `tint` | optional sRGB multiplier on the glTF's base colours |
| `ground_truth` | default `true`: tracked in `object_tracks.jsonl` with `kind` = `class` |

The renderer (`scene_manifest.rs`) and the station (`surmap.simulation.vehicles`, through
`scenario_manifest`) apply the same rules and refuse a vehicle by its id with the reason.

### Class files (`assets/vehicle/<class>.vehicle.json`, data, no rebuild)

| Field | Meaning |
|---|---|
| `glb` | the class glTF |
| `model_scale` | uniform scale of the glTF and its carriages (default 1, > 0), for a model not authored in metres |
| `model_yaw_deg` | the turn that points the glTF's nose along the vehicle's forward |
| `length_m`, `width_m`, `height_m` | the collider and ground-truth extent |
| `wheel_nodes`, `wheel_radius_m` | glTF node-name prefixes spun about their own bounds centre by distance / radius (road classes; empty when the model has no separable wheels) |
| `max_speed_m_s`, `accel_m_s2`, `brake_m_s2`, `turn_rate_deg_s` | the driving limits |
| `carriage_glb`, `carriage_spacing_m` | trains only |

| Class | Model (licence) | Size (m) | Max speed · accel · brake · turn |
|---|---|---|---|
| `car` | Quaternius car (CC0) | 4.2 × 1.8 × 1.2 | 15 m/s · 3 · 6 m/s² · 45°/s |
| `bus` | "Bus" by Poly by Google (CC BY 3.0), `model_scale` 0.07 | 11.0 × 3.5 × 3.4 | 12 · 1.2 · 3 · 20 |
| `truck` | Quaternius truck (CC0), `model_scale` 1.25 | 6.6 × 3.4 × 3.6 | 12 · 1.0 · 3 · 18 |
| `train` | Quaternius locomotive and wagon (CC0), carriages 8.4 m apart | 8.1 × 2.9 × 6.1 | 30 · 0.5 · 1.0 · 6 |

The Quaternius models are pinned from poly.pizza. The fetch sends a `Referer` for
`static.poly.pizza`, which refuses hot links without one. Kenney's kits cannot be pinned because
their download links are signed and expire. The bus is the one non-CC0 vehicle asset (see
*Everything is data*), and `test_the_only_pin_off_cc0_is_the_named_cc_by_bus` holds that line.
It is one coach mesh, so its `wheel_nodes` is empty and its wheels do not spin. Its nose is +Z
(`model_yaw_deg` 180), the end with the mirror arms.

### Boats and ships

`boat` and `ship` are vehicle classes with `"medium": "water"`. They are driven by the same trees
and the same `Drive` limits as the road classes, and they ride a water surface instead of the
ground:

- **Water** is a `box` with `"water": true` (an explicit flag, because material keys are
  free-form). A vessel floats on the top of the box it starts in.
- **Validation** (`scene_manifest/water.rs`, and `surmap.simulation.water` for the station): a
  vessel must start on water, and every `move_to` / `follow_path` point must lie on water. A
  vessel's tree may not contain `wander` or `flee_from_fire`, whose points are not known at load.
  A road or rail class may not start on water. A refused vessel is named with the reason.
- **Sea state** (`sea.rs`, pure, kinematic, no buoyancy physics): wave height follows the
  scenario's base wind speed (a 100 m fetch, capped at 1 m), and the period runs from 2.5 to 6 s.
  Three swells give each vessel heave, pitch and roll, scaled by its class's `wave_response` and
  phased by its id, so a still at `--at t` and a recording replay identically. The sea follows
  the base wind, not the live (behaviour-tree) wind.
- **Class fields** beside the road ones: `medium` (`water`), `draft_m`, `wave_response` (required
  for a water class), and `keel_below_origin_m`, which lifts the model so its keel sits on the
  surface. `wheel_nodes` is empty.

| Class | Model (licence) | Size (m) | Max speed · accel · brake · turn | Draft · wave response |
|---|---|---|---|---|
| `boat` | Quaternius boat (CC0), `model_scale` 0.56, `model_yaw_deg` 180 | 5.0 × 2.6 × 1.1 | 8 m/s · 1.5 · 1.0 m/s² · 25°/s | 0.6 m · 1.0 |
| `ship` | Quaternius ship (CC0), `model_scale` 3.9, `model_yaw_deg` 270 | 60.0 × 20.7 × 44.9 | 7 · 0.1 · 0.08 · 2 | 4.0 m · 0.1 |

Kenney's *Watercraft Kit* was the first choice, but its download refuses a scripted fetch, so the
equivalent Quaternius CC0 pair is pinned from poly.pizza. The ship is a three-masted sailing
ship, the only CC0 ship that could be pinned. Its masts make it 44.9 m tall.

The preset `flood-rescue` (golden `tests/fixtures/sim_scenario/flood-rescue.json`) is the flood
with a 10 m × 100 m water channel and two rescue boats shuttling along it in opposite
directions. It has no ship, because a 20.7 m beam does not fit the channel.

### Kinematics (`vehicle.rs`, pure, deterministic)

The tree's running leaf proposes a **goal** (`behaviour::Goal`: a point, a speed, and `stop` at a
path's end). `Drive` turns the goal into motion the class allows:

- **Speed** eases toward the node's `speed_m_s`, capped at `max_speed_m_s`, at `accel_m_s2`. It
  slows at `brake_m_s2` to stop at a stopping goal (the last point of a `move_to` or
  `follow_path`). It closes that goal no faster than its stopping distance allows, and no faster
  than half of turn rate × distance, so it creeps onto the goal and never overshoots.
- **Heading** turns toward the goal at most at `turn_rate_deg_s`, and the body moves along it.
  A goal to the side or behind is approached only at the speed that keeps the bearing turning
  at most half the turn rate (`BEARING_SHARE`). The heading always catches up, so a vehicle never
  circles a goal.
- **A drive-through point** (a path corner) counts as reached when the vehicle passes it.
- **Wheels** turn by distance / `wheel_radius_m`.

Each tick the runner is reset to where the vehicle really is (`VehicleBody`), so a tree's
`near_object` and its path ends see the vehicle's place. Vehicles tick with the people at 10 Hz
(`actors/tick.rs`), and each body senses the others. A train's heading follows its path, and its
carriages are placed `k × carriage_spacing_m` behind the locomotive **along the travelled
polyline** (`carriage_poses`), so they stay on the track through bends. `vehicle/scene.rs` puts
it on screen: the class glTF under a moving root, its wheel nodes spun, the carriages as
separate roots.

### Ground truth

Every `object_tracks.jsonl` object carries `kind` (`person`, `car`, `bus`, `truck`, `train`, `boat`, `ship`) and
`yaw_deg` (ENU, counter-clockwise from east), beside `id`, `enu` and `action`. A train is tracked
as its locomotive, and its carriages are not tracked. A parked vehicle (no tree) is still only a
track. `load_bevy_capture(...).object_kinds` (id → kind) and `.object_yaw_deg` (`t_ns` → id →
degrees) read them, and both are empty for older tracks. How the on-board detectors are scored
against them: *On-board detectors (measured)* § *Road and rail vehicles*.

### Station, agent and preset

`add_element` takes `VehicleElement {id, vehicle_class, position, yaw_deg, cars,
behaviour_json}`. The proto field is `vehicle_class` because `class` is a Python keyword, and
the manifest key stays `class`. The tree is validated by `surmap.simulation.behaviour_tree`. The
behaviour tools (`set_behaviour`, …) take a vehicle's id as their target. The preset
`street-traffic` (golden `tests/fixtures/sim_scenario/street-traffic.json`, parsed by the
renderer's tests) is the shipped block with:

- two cars driving the avenue and one parked;
- a school-bus-yellow bus and a truck on the cross street;
- a rail line (`box`, material `ballast`) along the block's west edge, with a six-carriage
  freight train.

### Verified

Rust tests pin the following. `Drive` never exceeds speed, acceleration or turn rate, and it
reaches a path's end without overshoot or circling. A scenario replays the same track.
Carriages stay on the path at their spacing through a 90° bend. Wheel angle follows distance.
The manifest rules (unknown class, `cars` off a train, a bad `glb`, a tree that sets the wind)
and the golden `street-traffic.json` hold, and so does the track line with `kind`/`yaw_deg`.
Python tests pin the same validation, the preset, `add_element` with a vehicle through the
tool, the capture's kinds and headings, and an agent turn on a real socket that adds a truck
driving up the avenue. A native still and a 64-frame recording of `street-traffic` were
reviewed at wrap (2026-11-04):

- the cars drive the avenue, and the bus and truck drive the cross street side by side;
- the bus's mirror end leads along its travel, which confirms `model_yaw_deg` 180, and its
  wheels sit on the road;
- the truck's cab leads;
- the train stands on its ballast line at the west edge.

## Drone nests

A scenario can hold drone nests: 2.4 m × 2.4 m docking pads, each housing one to four simulated
drones. The agent places them with `add_element` like any other element. The renderer draws each
one as a landing pad (a dark rim, a deck and an "H" marking) turned by `yaw_deg`, tags it
`NestPad { id }`, and publishes every nest in the `Nests` resource (id, ENU pad centre, yaw, drone
ids). The fleet's drones dock on them (*The fleet and its autopilot*).

Nests are the simulation-only exception's scene data ([architecture.md](../architecture.md) §1):
the agent may task the simulation's own drones on machine 3, and SurMap still has no write path to
any real flight controller.

### In the manifest

```json
{"kind": "drone_nest", "id": "nest-north", "position_enu": [40, 30, 0], "yaw_deg": 90, "drones": 2}
```

| Field | Meaning |
|---|---|
| `id` | letters, digits and `-`; the drones are `<id>-d1` … `<id>-dN` and join the manifest's one id namespace |
| `position_enu` | the pad centre at deck level: `0` on open ground, the roof's top on a building |
| `yaw_deg` | heading, degrees counter-clockwise from east; default 0 |
| `drones` | 1–4; default 1 |

Placement rules, refused with the nest id and the rule, identically by the station
(`surmap.simulation.fleet_nests.validate_nests`) and the renderer (`scene_manifest/fleet.rs`):

- the pad lies within ±500 m east/north of the origin and 0–60 m up;
- it does not overlap a building, collapsed building or solid box footprint unless it stands on
  that element's top (a rooftop nest);
- it does not overlap a `water: true` surface (a water box with a collider is still water);
- nest centres are at least 6 m apart horizontally;
- a scenario holds at most 8 nests;
- a drone id never collides with another id, whichever was added first.

The rules are footprint-only (a yawed 2D box), the same way water and vehicles validate, so the two
languages agree exactly. The shared golden is `tests/fixtures/sim_scenario/fleet-nests.json`.

### Preset

`earthquake-fleet`: the earthquake block with three nests and five drones — two on open ground at
opposite corners, one on a standing building's roof.

### Verified

2026-11-04 (#116): `uv run pytest -q tests/test_sim_fleet_nests.py tests/test_agent_simulation_tools.py`
36 passed; `cargo test --locked fleet` 18 passed (the rule tests and the golden). The native
`earthquake-fleet` still could not be taken in the wrap worktree: its pinned textures and figure
models were not fetched there (`aerial_asphalt_01_diff_2k.jpg`, `person/wave.glb` missing).

## The fleet and its autopilot

When a scene has nests, each nest's drones spawn docked on its pad (`fleet.rs::spawn_fleet`, one
body per drone id, tagged `FleetDrone { id }`, kinematic) and the legacy keyboard `Drone` is
despawned. A kinematic autopilot flies them from a simulation-time-stamped command log. Scenes
without nests are unchanged: one legacy drone, keyboard flight, and the `survey-loop` for stills
and recordings.

### The fleet log (`fleet/log.rs`)

One JSON object per line, in `at_s` order (ties broken by `seq`):

```json
{"seq": 1, "at_s": 2.0, "command": {"type": "launch", "drone": "nest-sw-d1",
  "route": {"waypoints": [[-10, 20, 12], [10, 60, 15]], "speed_m_s": 5, "on_complete": "return"}}}
{"seq": 2, "at_s": 9.5, "command": {"type": "detour", "drone": "nest-sw-d1", "waypoints": [[0, 35, 18]]}}
{"seq": 3, "at_s": 12.0, "command": {"type": "set_active", "drone": "nest-sw-d1"}}
```

Commands: `launch` (with a route), `set_route`, `detour`, `recall` and `set_active`. A route's
`on_complete` is `hover` or `return`. `FleetLog::push(at_s, command)` checks each command against
the drone's phase at `at_s`, read from a per-drone checker `Autopilot` that has followed the log so
far (it never replays from `t = 0`), and returns the assigned `seq` or a
`Refusal`. A command is refused for any of these:

- an unknown drone;
- `launch` when the drone is not `Docked`;
- `set_route` or `detour` when it is `Docked` or `Landing`;
- `recall` when it is `Docked`;
- empty waypoints;
- a speed outside 0.5–8 m/s;
- a waypoint `up` outside 5–60 m.

The log keeps refusals (`refused()`) but never applies them. `from_jsonl` keeps the file's `seq`s
and refuses a line whose `at_s` is out of order.

### The autopilot (`fleet/autopilot.rs`, pure)

The autopilot uses a fixed step, `STEP_S = 0.05` from `t = 0`, so the result does not depend on
frame rate. A command takes effect at the first step at or after its `at_s`.
`state_at(home, id, log, t)` is a pure function. The runtime `Autopilot` advances step by step and
equals `state_at` at every `t` (a test checks this). `state_at`, `phase_when` and `viewed_pose` are
the replay-from-the-pad definitions, kept as the test oracle only (`#[cfg(test)]`). An `Autopilot`
asked for an earlier moment than its last replays from the pad.

The two callers that move forward in time advance instead of replaying: `FleetLog` keeps one
checker `Autopilot` per drone (`phase_when` continues from its last check, and rewinds if a refused
command had advanced it past a later accepted one), and the recorder keeps its own
`ViewedPoses`, one `Autopilot` per drone. It does not read `Fleet.autopilots`, because the live set
follows `SimClock` while the recorder pins `SimTime` per frame. Recording `n` frames and pushing `k`
commands therefore cost linear steps. Measured: 6000 frames at 10 Hz over 600 s dropped from
35 994 000 to 17 996 steps, and 1000 pushes from 5 005 000 to 10 000.

| Phase | Motion |
|---|---|
| `Docked` | on the pad, facing the nest's `yaw_deg` |
| `Climbing` | straight up at ≤ 2 m/s to the first target's `up` (at least 5 m above the pad) |
| `Cruising` | toward the current target. Horizontal speed ramps at ≤ 2.5 m/s² up to the route speed. Vertical speed is ≤ 2 m/s. Heading turns toward the velocity at ≤ 60°/s. A target within 1 m counts as reached |
| `Detouring` | as `Cruising`, over the detour's waypoints. Afterwards it resumes the target that was current when the detour arrived |
| `Hovering` | holds position, decelerating within the acceleration limit (`on_complete: hover`) |
| `Returning` | cruises at its current altitude to the point above the pad (`recall`, or `on_complete: return`) |
| `Landing` | straight down at ≤ 1 m/s to the pad, then `Docked` |

`set_route` replaces the remaining targets and never resets position or velocity, so the path stays
continuous. There is no obstacle avoidance and no drone-to-drone separation: routes are flown
exactly as given, so the agent must plan them around buildings
([TODO](../../src/surmap/docs/todo/2026-11-04-fleet-obstacle-avoidance.md)).

### The active drone, recording and `--fleet-log`

- `ActiveDrone` starts as the first drone id, and `set_active` entries switch it at their `at_s`.
  "The viewed drone" is the active fleet drone, or the legacy `Drone` when there is no fleet. The
  stereo rig, the chase camera and the status line follow it. The status line names the drone, its
  phase and its leg, and the UI lists the fleet (id · phase). Keyboard flight drives only the legacy
  drone.
- Rotors spin whenever a fleet drone is not `Docked`.
- `record_frames` takes `pose_enu` from `ViewedPoses::viewed(t)` (equal to the replayed `viewed_pose(t)`): the autopilot's pose of the active drone
  at `t`, or `SurveyLoop` when there is no fleet. With a fleet, each `frames.jsonl` line carries
  `"drone_id"`, and `CapturedFrame.drone_id` reads it (`None` for older captures).
- `--fleet-log <path>` replays a log for stills and recordings:

```bash
BEVY_ASSET_ROOT=$PWD cargo run --release -- --scenario <id> \
  --fleet-log sorties/survey-sortie.fleet.jsonl --screenshot shots/fleet --at 20
```

A sample log is `tests/fixtures/fleet/survey-sortie.fleet.jsonl`.

### Verified

2026-11-04 (#117): `cargo test --locked` 334 passed, including the fleet log, the autopilot limits,
`Autopilot` = `state_at`, and `viewed_pose`. `uv run pytest -q` 2238 passed, 38 skipped. Native
stills of `earthquake-fleet` replaying `survey-sortie.fleet.jsonl` at `--at 20` and `--at 40`:
the chase camera shows the active drone airborne over the block, at a different point of its route
in each still.

2026-11-04 (#138): `cargo test --locked` 369 passed, 0 ignored: the three characterisation tests
(cached recorder pose = replay on every frame, every push = a fresh replay's decision, a rewound
recorder) green before and after, and the two step bounds.

## The fleet link

The station commands a running page's drones over one WebSocket, `/sim/fleet?scenario=<id>` on
the agent server's own origin. A page opens it only with `?fleet=1`. Without that, and in native
builds, nothing is sent: native runs take their commands from `--fleet-log`.

### `fleet/v1` messages (JSON text frames)

| Direction | Message |
|---|---|
| sim → station | `{"type":"hello","protocol":"fleet/v1","scenario":"…","sim_t_s":0.0,"drones":["nest-sw-d1",…]}` |
| station → sim | `{"type":"command","request":7,"command":{…a fleet-log command…}}` |
| sim → station | `{"type":"applied","request":7,"seq":3,"at_s":41.25}` |
| sim → station | `{"type":"refused","request":7,"at_s":41.25,"reason":"nest-sw-d1 is docked: detour needs a drone in flight"}` |
| sim → station | `{"type":"telemetry","sim_t_s":41.5,"active":"nest-sw-d1","drones":[{"id":"…","phase":"cruising","enu":[x,y,z],"yaw_deg":…,"speed_m_s":…,"targets_left":2}]}` every 0.5 s |

- Frames are compact JSON with the keys in this order. The goldens are
  `tests/fixtures/fleet_link/{hello,command,applied,refused,telemetry}.json`. Both codecs (Python
  `surmap.simulation.fleet.link`, Rust `fleet/link.rs`) re-encode them byte for byte.
- Phase words: `docked climbing cruising detouring hovering returning landing`.
- The route accepts the upgrade and then closes on a fault. These close with 4400: a missing
  `?scenario=`, an unknown scenario, a first frame that is not a `fleet/v1` hello, and an unknown
  `type`. A second page for a scenario that already has one closes with 4409, and the first page
  stays linked.

### The station (`surmap.simulation.fleet`)

- **`FleetRegistry`** (`fleet/registry.py`) is `SimulationRig.fleet`, one per server.
  `controller(id)` builds a `FleetController` on first use and caches it. While no page is
  linked, the controller reads the scenario's latest manifest nests on every validation, so a
  nest added later has drones it knows; once linked, the page's `hello` drones are
  authoritative. `link(id, socket)` runs one page: hello first, then every frame goes to the
  controller until the page closes, which detaches the link. A `hello` whose `scenario` differs
  from `?scenario=` is closed with 4400, and nothing is attached.
- **`FleetController.send(command)`** validates, sends and waits, in that order:
  1. **Validate.** The drone must be known: one of the scenario's nests' drones, or one in the
     linked page's `hello` list. The route must be non-empty. Every waypoint must be within
     ±500 m east and north and 5–60 m up, and the speed 0.5–8 m/s. The drone's phase must allow
     the command, by the fleet log's rules. A failure raises `FleetInvalid(rule)` and nothing is
     sent.
  2. **No link** raises `FleetUnavailable("no simulation connected for scenario <id>")`.
  3. **Send and wait** up to 5 s for `applied` or `refused` with the same request id. `applied`
     is logged and returned as `Applied(request, seq, at_s)`. `refused` raises
     `FleetRefused(reason)` with the page's text. Silence raises `FleetTimeout`. An `applied`
     that arrives after the timeout is still logged, because the page did apply it.

  Requests are numbered from 1 and serialised per scenario, so the order sent is the order
  applied. The phase comes from the last telemetry, and before any telemetry every drone is
  `docked`. A drone the page just launched (or recalled) keeps its expected phase until telemetry
  reaches the step the page applies the command at. `due_step` / `steps_until` and the 0.05 s
  `STEP_S` mirror `fleet/autopilot.rs`, so telemetry from the frame a launch lands in does not
  drop the expectation early. After the page disconnects, its retained telemetry no longer
  decides phases. A controller that was never linked still answers a recall of a docked drone
  with `already_docked` before it reports no simulation connected. The page still refuses on its
  own phase, because telemetry can be up to 0.5 s old. `telemetry_time()` is the last
  telemetry's `sim_t_s` while linked (`list_drones.sim_t_s`), else `None`.
- **`FleetLogStore`** keeps two tables in the scenario store's SQLite file. `fleet_sessions` has
  one row per linked page (`session_id`, `scenario_id`, `started_at`, `hello`). `fleet_log` has
  the session's applied commands (`seq`, `at_s`, `command_json`). The simulation stamps the time,
  and the station keeps the stamped copy. `export_jsonl(session)` writes the session as a
  `--fleet-log` file, so a browser sortie replays natively. A refused request leaves a gap in the
  `seq`s, which `FleetLog::from_jsonl` accepts.

### The page (`fleet/link_wasm.rs`, wasm only)

- `FleetLinkPlugin` opens `ws[s]://<location.host>/sim/fleet?scenario=<id>` and sends `hello`
  once the scene is built.
- Incoming commands are queued. A Bevy system drains the queue each frame and calls
  `FleetLog::push(SimClock::now(), command)`. It answers `applied` with the log's `seq`, or
  `refused` with the refusal's text.
- A timer system sends telemetry every 0.5 s.
- The pure parts (`fleet_enabled`, `fleet_socket_url`, the codec, `refusal_text`,
  `drone_telemetry`) live in `fleet/link.rs` and are unit-tested natively.
- The page's `web-sys` features gain `WebSocket`, `MessageEvent`, `CloseEvent` and `ErrorEvent`.
  The page banner and `Cargo.toml` say that frames stay in the page and that the optional
  `?fleet=1` link exchanges fleet commands and telemetry.

### Trying it in a browser

`scripts/fleet_link_smoke.py` is a station for one tab, with a scripted sortie:

1. It creates an earthquake-fleet scenario, prints the page URL and waits for the `hello`.
2. It launches `nest-sw-d1` and sends it a detour 15 s later.
3. It launches `nest-ne-d1` and makes it the active drone.
4. It recalls both.

It prints each `applied` and the drones' phases, and exports the session as a `--fleet-log` file.

```bash
cd examples/bevy-sitl-poc && trunk build index.html --release && cd ../..
uv run python scripts/fleet_link_smoke.py --sim-dist examples/bevy-sitl-poc/dist --preset earthquake-fleet
# open the printed /sim/?scenario=<id>&fleet=1 in Chrome (WebGPU)
```

### Verified

2026-11-04 (#119):

- The fleet suites (`tests/test_sim_fleet_{link,controller,registry,log_store,link_e2e}.py`) 74
  passed. The end-to-end suite runs a real `HypercornHost` and a fake page.
- `cargo test --locked link` 18 passed, including `the_station_export_is_a_valid_fleet_log`.
- `cargo check --locked --target wasm32-unknown-unknown` compiles `link_wasm.rs`, with no warning
  in `fleet/link`.
- The smoke script flew the whole sortie against a scripted fake page: 6 applied, both drones
  docked, a 6-line export.
- Chrome run after merge —
  [`src/surmap/docs/todo/2026-11-04-fleet-browser-verification.md`](../../src/surmap/docs/todo/2026-11-04-fleet-browser-verification.md).

## Live stream: the active drone mapped and segmented, one map per drone

A page opened with `?bridge=ws://<station>:8773` streams the **active drone's** stereo pairs to
the station's bridge, and the station keeps **one RTAB-Map session and one segmentation run per
drone**. Only the active drone's frames are processed; the other drones keep flying unprocessed.

- **Starting the bridge.** `python -m surmap.agent --bevy-bridge-port 8773` serves the bridge
  (`surmap.simulation.bevy_bridge.serve_bevy_bridge`) with a `FleetPerception` router per page
  connection and the streaming RTAB-Map factory. Segmentation uses the agent's configured SAM
  (`bridge_segmentation`: the station's detector, else the centred-box fake under `--sam-fake`),
  one `VideoAsFrameSamDetector` (one video) per drone session; no frame is kept after `detect`
  returns. The bridge runs each connection's `handle` / `close` off the event loop
  (`asyncio.to_thread`) under a per-connection lock, so a slow map start never stalls the agent
  server and one connection's messages stay in order. The page and the bridge share one origin through `--sim-dist`; there is no
  separate `serve_bevy_sim.py`.
- **The page (`fleet/bridge_wasm.rs`, wasm only).** `?bridge=` opens a binary `WebSocket` and
  sends `hello` (camera profile, ground truth, optional `scenario`) at scene ready. Each
  sim-time tick, `StreamPacer` (`fleet/stream.rs`, pure) sends at the camera's `rate_hz`: it
  reads back the eyes (`Readback`, as `record.rs` does). The `PendingPair` captured at the
  request holds the active drone's id, pose and `t_ns`, so a switch during the readback still
  labels the pair with the drone whose eyes were read. `stream_bridge` runs in
  `BridgeStreamSet`, ordered after `fleet::fly_fleet` and `follow_drone_rig`. When `bufferedAmount` exceeds four frame sizes the pair is
  dropped, never queued without bound. A pair without a fleet carries no `drone_id` and stays
  byte-identical to the old golden (`pair.bin`); `pair-drone.bin` pins the labelled form.
- **Per-drone sessions (`surmap.simulation.fleet.perception`).** `hello` stores the camera
  profile and scenario and registers the connection in `PerceptionRegistry[scenario]`. Each
  `pair` is routed by `drone_id` (`default` when absent) to that drone's `DroneSession` — a
  backend from the factory, a `SamSegmentationSink` on its left frames (worker thread, queue
  of 2, drop oldest), an optional per-drone `CaptureRecorder`, and counts. At most
  `MAX_DRONE_SESSIONS = 4` sessions live per connection; a fifth drone's pairs are answered
  `error: "drone session limit (4) reached; <id> not processed"` and the first four keep
  working. A drone whose backend raises is marked errored: its backend is closed once, its
  counts freeze, later pairs get the same `error` status, and the other drones and the socket
  keep running. A drone whose frames stop is idle with its backend and map alive; when its frames
  resume they go to the same backend — RTAB-Map resets odometry after the gap and starts a new
  sub-map in the same graph, which joins on loop closure. Closing the page finishes every
  session (backends closed, recorders finished, in drone-id order) and unregisters it.
- **Status.** The bridge replies with a `status` per pair (`frames`, `posed`, `lost`,
  `keyframes`, `dropped`, `drone_id`, and `error` for a failed drone); the page shows it under the feed panel as
  `MAP <drone> · <n> frames · <k> keyframes · tracking`. The agent reads every drone's counts
  with `drone_map_status` ([docs/agent.md](../agent.md), *Fleet tools*).

### Verified

2026-11-04 (#121): V1 — `tests/test_fleet_perception.py`,
`tests/test_fleet_perception_e2e.py`, `tests/test_bevy_wire.py` and
`tests/test_agent_fleet_tools.py` pass; the real-sidecar
`tests/test_fleet_perception_rtabmap_e2e.py` (CI `rtabmap-e2e`) feeds the committed capture as
two drones in alternating blocks — both sessions gain keyframes and the first drone's backend
is the same object with counts continuing after the switch back. V3 —
`cargo check --locked --target wasm32-unknown-unknown` compiles `fleet/bridge_wasm.rs`.
2026-11-04 (#133, review fixes): V1 fail→pass — eleven reproductions (bridge SAM and frame
retention, off-loop work, per-drone failure, scenario check, step mirror, latest nests,
`sim_t_s`, the readback's drone label and the stream's schedule order) pass. Chrome
run (V4) after merge —
[`src/surmap/docs/todo/2026-11-04-fleet-browser-verification.md`](../../src/surmap/docs/todo/2026-11-04-fleet-browser-verification.md).

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
# ...with a wildfire, flame-close.png looks at the front from 8 m outside it, 2 m up; with
# people, person-close.png stands 4 m in front of the first figure and looks at its head:
BEVY_ASSET_ROOT=$PWD cargo run --release -- --screenshot shots --at 60 --scenario wildfire-evacuation
# a stereo capture RTAB-Map can replay (hidden window, GPU readback, progress logged):
BEVY_ASSET_ROOT=$PWD cargo run --release -- --record cap --frames 90 --start 15.5 --jpeg \
  [--rate-hz 10] [--camera cameras/wide-baseline-pinhole.camera.json] [--colour]
```

`--flight survey-loop` flies the deterministic rounded-rectangle loop over the block
(1.5 m/s, 7 ± 1.5 m up, ≤ 10.7 °/s yaw, 182 m, 121 s); in a scene without nests, stills and recordings imply it (with nests the fleet flies instead). A
capture holds `camera.json`, `calibration.json`, `ground_truth.json` (ENU boxes of every
ground-truth element and model, and every survivor), `frames.jsonl` (each frame's rig pose
in ENU), grey8 frames (with `--colour` also the left eye in RGB under `frames/left_rgb/`,
named by `left_rgb_ref`; the grey eyes RTAB-Map reads are unchanged), `object_tracks.jsonl` (the wind and every person with a behaviour tree), with
fires `fire_perimeter.jsonl`, and with buildings that can burn `building_fires.jsonl`; `surmap.simulation.bevy_capture.load_bevy_capture` reads it.

`BEVY_ASSET_ROOT=$PWD`, run from `examples/bevy-sitl-poc`, points Bevy's asset server at the
crate's `assets/`: the scene, presets, fx files, textures and the flame flipbook are all loaded
from there at runtime, and a binary started outside `cargo run` (or from another directory)
would otherwise look for `assets/` next to the executable. The close stills (`close_shots.rs`)
exist because survey-range stills cannot show a flame sprite or a visor; their distances are the
constants at the top of the file.

**Recorded dynamics fixtures.** `tests/fixtures/bevy_capture_dynamics/{evacuation,blaze}/` are
real native recordings, committed without `frames/` (the loader only stores the image
references; 68 KB and 28 KB), that prove `fire_perimeter.jsonl`, `object_tracks.jsonl` and
`building_fires.jsonl` end to end (`tests/test_sim_disaster_sweep.py`). To re-record, from
`examples/bevy-sitl-poc`, then delete each `frames/` before copying:

```bash
BEVY_ASSET_ROOT=$PWD cargo run --release -- --record evacuation --frames 20 --start 25 --rate-hz 2 --scenario wildfire-evacuation
BEVY_ASSET_ROOT=$PWD cargo run --release -- --record blaze --frames 20 --start 5 --rate-hz 0.1 --scenario downtown-blaze
```

Verified natively (Metal) throughout; the browser build compiles for `wasm32` but the
runtime-scene version has not been checked in Chrome yet (visual checkpoint V5,
`src/surmap/docs/todo/2026-11-03-bevy-visual-checkpoints-v3-v5.md`).

Browser → RTAB-Map: the wire format (`src/wire.rs`, goldens in
`tests/fixtures/bevy_sim_wire/`), the Python bridge (`surmap.simulation.bevy_bridge`) and the
wasm WebSocket client (`?bridge=`, *Live stream* above) stream the active drone's pairs into
one RTAB-Map session per drone.

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

## On-board detectors (measured)

The ELP module streams MJPEG from a colour sensor (`docs/camera-elp-stereo.md`), so the Coral
COCO profiles (`surmap.detection.profiles`) see colour on board; `--colour` records that frame.
`surmap.simulation.detection_eval` projects every ground-truth `car` and `person` box onto the
left image of each frame (`bevy_ground_truth.project_box`). An object is **in view** when at
least half its projected box is inside the image and its shorter side is ≥ 12 px; a detection
**finds** it when its label is one the kind answers to (`car`: car, truck, bus; `person`:
person; a `bus`, `truck` or `train` only its own label — see *Road and rail vehicles* below) at
IoU ≥ 0.3. A detection of an object present but too small or too clipped to be in
view is neither; every other detection is a false positive. Occlusion is not tested (no depth
is recorded). `building`, `collapsed_building`, `debris`, `box` and `fire` are not COCO
classes: no on-board detector can name them, so they are never expected — SAM labels them
([meta-sam.md](../meta-sam.md)).

```bash
uv run python scripts/fetch_coral_model.py
uv run python scripts/score_sim_detections.py tests/fixtures/bevy_sim_detector_capture [--grey]
```

`tests/fixtures/bevy_sim_detector_capture/` (6.6 MB, colour left frames only — the grey eyes
are left out, as the dynamics fixtures leave out `frames/`) is the shipped scene recorded with
`--record cap --frames 75 --rate-hz 1 --start 12 --jpeg --colour`: the loop's east side past
the cars, then the north-east corner and the north side past the survivors. The *before* rows
re-record the same pass from the scene and figure before this change (cars under a tarp,
capsule survivors in hi-vis coats). Object-frames found / in view, score 0.3:

| Pass | Frames | Profile | Cars | People | False positives |
|---|---|---|---|---|---|
| PR #89 fixture (`bevy_sim_capture`, 15.5–24.4 s, grey, no people in its truth) | 90 | efficientdet-lite0 | 0/130 | — | 47 |
| | | ssd-mobilenet-v2 | 0/130 | — | 10 |
| | | ssdlite-mobiledet | 0/130 | — | 500 |
| before, grey | 75 | efficientdet-lite0 | 0/46 | 0/113 | 42 |
| | | ssd-mobilenet-v2 | 0/46 | 2/113 | 10 |
| | | ssdlite-mobiledet | 0/46 | 11/113 | 292 |
| before, colour | 75 | efficientdet-lite0 | 0/46 | 1/113 | 47 |
| | | ssd-mobilenet-v2 | 0/46 | 14/113 | 14 |
| | | ssdlite-mobiledet | 0/46 | 35/113 | 266 |
| after, grey | 75 | efficientdet-lite0 | 5/46 | 4/113 | 37 |
| | | ssd-mobilenet-v2 | 1/46 | 0/113 | 15 |
| | | ssdlite-mobiledet | 8/46 | 8/113 | 272 |
| **after, colour (the fixture)** | 75 | efficientdet-lite0 | **9/46** | **7/113** | 52 |
| | | ssd-mobilenet-v2 | **1/46** | **15/113** | 29 |
| | | ssdlite-mobiledet | **15/46** | **38/113** | 254 |

What moved it, and what did not:

- **Cars** went from never found to found: the uncovered model, with its normal maps dropped
  (`normal_maps: false` on the model — Bevy ignores `KHR_texture_transform` on a normal
  texture, so Car Concept's 30×-tiled paint-flake map landed as one coarse speckle that the
  detectors called a cake or a donut). Seen from 8 m up at 35° pitch the cars are mostly
  top-down views, which COCO's training data rarely shows; the hits come from the oblique
  frames.
- **People**: an untinted Cesium Man (white) was found *less* often than the orange capsules
  on the same pass (colour, ssdlite-mobiledet 6/113 vs 35/113), so the humanoid wears its
  coat (`coat_tint`). Tinted, it is found a little more often than the capsule (34 % vs 31 %
  ssdlite, 6 % vs 1 % efficientdet). In 99 of the 113 object-frames the survivor is under
  64 px tall (under 32 px at the networks' 300–320 px input); one cropped to fill the input
  is called a person by all three profiles (0.59–0.77). The pass's geometry, not the figure,
  now bounds person recall.
- **Colour** matters for every profile (grey after: cars 5/8, people 4/8 for efficientdet /
  ssdlite).
- **False positives** did not go down: the profiles still fire on rubble slabs, water and sky
  (`tv`, `airplane`, `bird`, `bench`, `book`); ssdlite-mobiledet is the noisiest.

**Rigged CC0 people (PR #107).** The survivors' Cesium Man gives way to two CC0 Quaternius
characters (a waving/walking/running/lying one, a sitting one), re-measured on the same pass
and on the `earthquake-survivors` scenario (`scripts/score_sim_detections.py` now also counts
person object-frames by pose from the tracks' `pose`). Object-frames found / in view, score 0.3:

| Pass | Profile | People, Cesium Man (#111) | People, rigged CC0 |
|---|---|---|---|
| shipped scene, `--record … --frames 75 --rate-hz 1 --start 12 --jpeg --colour` | efficientdet-lite0 | 7/113 | 20/113 |
| | ssd-mobilenet-v2 | 15/113 | 27/113 |
| | ssdlite-mobiledet | 38/113 | **65/113** |

| `earthquake-survivors`, `--frames 200 --rate-hz 1 --start 0` (the whole loop) | efficientdet | ssd-mobilenet | ssdlite-mobiledet |
|---|---|---|---|
| standing (rescuers, walking) | 0/66 | 0/66 | 18/66 (27 %) |
| sitting | 7/38 | 5/38 | 18/38 (47 %) |
| waving | 0/33 | 0/33 | 0/33 |
| lying | 0/6 | 0/6 | 0/6 |

Three realism iterations on the scenario: (1) the whole figure in the hi-vis coat (shirt and
trousers) found people *less* (ssdlite standing 4/66 against 11/66 with the shirt only), so only
the shirt wears it and the model's own skin is kept (a flat library skin read as grey); (2) the
waving and lying survivors stood half inside a slab and under its lean, so they are moved onto
open ground (the scene does not test occlusion, so a hidden person still counts as in view);
(3) the waving survivor faces the route. Waving and lying stay unfound: the loop sees them from
above at 15-40 px, a raised arm and a body lying on tarmac are not what COCO's person class was
trained on, and a lying person's truth box is now horizontal (`posed_person_truth`).
Recorded in `src/surmap/docs/todo/2026-11-04-waving-and-lying-people-undetected.md`.

### Road and rail vehicles (`street-traffic`)

The vehicles of `street-traffic` are not in `ground_truth.json`: only `object_tracks.jsonl` places
them (`kind`, `yaw_deg`, position per frame). `detection_eval` gives each tracked vehicle the
footprint of its class (`VEHICLE_FOOTPRINT_M`, from `assets/vehicle/<class>.vehicle.json`; a train
is its locomotive) at its recorded position, the axis-aligned box around its yawed rectangle. A
`car` answers to car, truck or bus; a `bus`, `truck` or `train` only to its own label. A vehicle
that is not found but is covered (IoU ≥ 0.3) by a detection with another vehicle's label counts as
**found as another vehicle** (`+n` in the score script's table); that detection is not a false
positive.

```bash
uv run python scripts/fetch_coral_model.py
cd examples/bevy-sitl-poc
BEVY_ASSET_ROOT=$PWD cargo run --release -- --record <dir> --scenario street-traffic --colour --jpeg --rate-hz 1 --start 0 --frames 128
cd ../.. && uv run python scripts/score_sim_detections.py <dir>
```

`--scenario street-traffic` loads `assets/scenarios/street-traffic.json` (copy
`tests/fixtures/sim_scenario/street-traffic.json` there, the folder is not tracked); 128 frames at
1 Hz are one lap of the survey loop (127 s): the loop passes the avenue, the cross street (bus and
truck) and the rail line (train, in view for six frames). Frames are not committed. Object-frames
found / in view, score 0.3, colour (the bar: the best profile finds each kind in ≥ 20 % of its
object-frames, and no kind is 0 across all profiles):

| Pass | Profile | Cars | Bus | Truck | Train | False positives |
|---|---|---|---|---|---|---|
| before (white bus, truck on the avenue, scale 1) | efficientdet-lite0 | 12/90 | 1/16 +1 | 1/13 +1 | 0/6 | 84 |
| | ssd-mobilenet-v2 | 3/90 | 0/16 | 0/13 | 0/6 | 35 |
| | ssdlite-mobiledet | 33/90 | 0/16 +5 | 2/13 | 0/6 | 355 |
| **after (the preset)** | efficientdet-lite0 | 12/90 | **5/16** | **8/14** | 0/6 | 85 |
| | ssd-mobilenet-v2 | 2/90 | 0/16 +2 | 1/14 | 0/6 | 32 |
| | ssdlite-mobiledet | **34/90** | 1/16 +6 | **10/14** | 0/6 | 344 |

What moved it, and what did not (three iterations at most per class, each a full re-record):

- **Bus** 1/16 → 5/16: the model is white, and a red tint scored 0/16 on the same pass; school-bus
  yellow (`tint [1.0, 0.78, 0.1]`) is read as a bus by efficientdet-lite0. ssdlite-mobiledet calls
  it another vehicle (car or truck) in 6 more frames.
- **Truck** 1/13 → 10/14: the Quaternius truck reads as a van at 8 m up, and on the avenue it was
  seen end-on, far off and behind rubble slabs (occlusion is not tested). It now drives the cross
  street (5 m south of the bus's lane), side-on and close to the loop's passes, and its class is
  scaled 1.25 (6.6 × 3.4 × 3.6 m) so it is not smaller than the bus beside it. (On the same pass a
  scale-only change, with the avenue unchanged, left it 1/13.)
- **Cars** are unchanged by this PR (12/90, 34/90 here; 9/46, 15/46 on #111's fixture window).
- **Train** stays at 0/6 on every profile, **under the bar**. Tried: the rail 36 m closer to the
  loop (x −30, then −26; the locomotive is then clipped by the top of the image — box 0–45 px tall
  — and ssdlite calls the tender's figure a person), and 22 m closer with the train slowed to
  8 m/s (the same six frames, 51–56 s). A tint cannot lighten the locomotive: its glTF colours are
  linear 0.02–0.04, near black. Recorded as
  `src/surmap/docs/todo/2026-11-04-train-detectors-blind.md`.
- A recording's light can differ from run to run: one capture of the same scenario was 25 %
  darker and scored lower on every class; it was discarded and re-recorded. Re-record before
  comparing a pass with another.

`tests/test_sim_detector_realism_e2e.py` (in CI's `coral-e2e` job, `SURMAP_REQUIRE_CORAL_E2E=1`)
holds floors under these numbers: efficientdet-lite0 finds cars in ≥ 10 % of their frames,
ssdlite-mobiledet finds cars and people in ≥ 25 %. To re-record, from `examples/bevy-sitl-poc`,
keep `frames/left_rgb/` and the JSON files of
`BEVY_ASSET_ROOT=$PWD cargo run --release -- --record cap --frames 75 --rate-hz 1 --start 12 --jpeg --colour`.

### Boats and ships (`flood-rescue`)

`boat` and `ship` both answer to COCO's `boat` label. Their footprints come from the class files
(`VEHICLE_FOOTPRINT_M`), as the road classes' do. Boats are scored on the preset. The ship is
scored on an untracked variant of the preset with the water widened to 40 m and one moored ship
at (0, 62), because the preset's channel cannot hold one. One lap each (`--frames 128 --rate-hz 1
--start 0 --colour --jpeg`), score 0.3, object-frames found / in view:

| Scene | Profile | Boat | Ship | False positives |
|---|---|---|---|---|
| `flood-rescue` | efficientdet-lite0 | 0/47 | – | 90 |
| | ssd-mobilenet-v2 | 0/47 | – | 57 |
| | ssdlite-mobiledet | 3/47 (6 %) | – | 407 (66 of them `boat`) |
| ship variant | efficientdet-lite0 | 0/47 | 0/0 | 71 |
| | ssd-mobilenet-v2 | 0/47 | 0/0 | 47 |
| | ssdlite-mobiledet | 0/47 | 0/0 | 423 (23 of them `boat`) |

Both classes are **under the bar**, and no realism iteration was run (fast-tracked).
- **Boat:** ssdlite-mobiledet fires `boat` 66 times on the preset, yet matches only 3 boats. The
  detections may be falling beside the expected boxes, for example because heave and keel lift
  are not in the tracked height, or because they land on the water box itself.
- **Ship:** never counts as in view. Its 60 × 20.7 × 44.9 m box (the masts) is never half inside
  the frame from the survey loop's height.

Recorded as `src/surmap/docs/todo/2026-11-04-vessels-detectors-miss.md`.
