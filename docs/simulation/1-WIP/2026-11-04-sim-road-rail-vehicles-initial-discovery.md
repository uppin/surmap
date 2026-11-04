# Initial discovery — road and rail vehicles that drive (n1 of #sim-traffic)

## Conclusions

- The Bevy simulation is `examples/bevy-sitl-poc` (Bevy 0.18, WebGPU, Rapier, Feronia, hanabi).
  Everything a scenario shows is manifest data (`assets/scene.json` or a station scenario);
  element kinds are the only scene knowledge in code (`scene_manifest.rs` `Element`:
  `box`, `collapsed_building`, `building`, `person`, `vegetation`).
- People today: `world.rs` `Builder::person` spawns a `Figure` root with a capsule (coat) and a
  sphere (skin); `actors.rs` ticks the person's behaviour tree at 10 Hz on `SimClock`, eases yaw,
  bobs per step (`assets/behaviour/person.figure.json`) and attaches a visor. No limbs, no
  animation clips, no poses.
- Behaviour trees (`behaviour.rs`, `behaviour/tick.rs`) are pure and target-agnostic for ground
  bodies (`Target::Object`): `move_to`, `follow_path`, `idle`, `wander`, `flee_from_fire`,
  `near_object`, composites. `Runner.position` moves at the node's `speed_m_s` with no
  acceleration or turn limit — fine for people, not for vehicles.
- Moving ground truth: `object_tracks.jsonl` per capture frame (`actors::track_line`: `t_ns`,
  `wind_enu`, `objects[{id, enu, action}]`), read by `surmap.simulation.bevy_capture`. Static
  `ground_truth.json` never holds moving bodies (architecture §1).
- Vehicles today: static glTF `models` only (Poly Haven `covered_car`, `kind: car`); no vehicle
  element, nothing moves, no rail or water semantics. Water is a `box` with material `water`.
- Assets: `assets/assets.lock.json` (97 pins: path, url, sha256, licence, source, optional zip
  `member`), fetched by `scripts/fetch_sim_assets.py` via `surmap.simulation.sim_assets`. Zip
  members are supported, so a CC0 pack zip (Kenney / Quaternius via Poly Pizza) can be pinned.
- Station side: `src/surmap/simulation/scenario_manifest.py` mirrors the element kinds
  (`ELEMENT_KINDS`) and validation; the agent's `add_element` tool is a proto oneof
  (`proto/surmap/.../simulation_tools.proto`, handler `agent/tools/simulation_handlers.py`).
  Shared golden: `tests/fixtures/sim_scenario/*.json` parsed by both Rust and Python.
- Deferred work in scope: `src/surmap/docs/todo/2026-11-03-bevy-visual-checkpoints-v3-v5.md`
  (browser visual checkpoint not yet run) — not blocking; the other bevy TODOs are unrelated.

## Exploration 1

Read: `examples/bevy-sitl-poc/{README.md,Cargo.toml,src/main.rs,src/world.rs,src/scene_manifest.rs,
src/actors.rs,src/behaviour.rs,src/record.rs,src/shots.rs,assets/scene.json,
assets/behaviour/person.figure.json}`, `docs/simulation/bevy-simulation.md` (§ Behaviour trees),
`scripts/fetch_sim_assets.py`, `src/surmap/simulation/{sim_assets.py,scenario_manifest.py}`,
`src/surmap/agent/tools/simulation_handlers.py` (add_element oneof).

## Exploration 2 — n1 specifics

- Recorder: `record.rs` pushes `actors::track_line(t_ns, wind, &bodies)` per frame (line 225) and writes `object_tracks.jsonl`; `bevy_capture._load_object_tracks` reads it by id.
- Station: `scenario_manifest.py` `ELEMENT_KINDS` (line 60), presets in `load_presets` (line 447) built from the block; proto `AddElementRequest` oneof fields 2–6 used.
- Kenney Car/Train/Watercraft kits are CC0 (kenney.nl); download URLs are not on the page — resolve and pin by sha256 at Green.
