# Initial discovery — behaviour trees for simulation objects and the wind

- `scene_manifest.rs` `Person { id, position_enu, coat, skin }` spawns a static capsule + sphere in
  `world.rs::person`; nothing moves except the drone (`flight.rs`, `SimTime`).
- n3 (#100) gives `WindModel` (`wind.rs`), `FireSpec::{perimeter, burnt}` (`fire.rs`) and
  `weather.wind` in the manifest; `GlobalWind` follows `WindModel::feronia(t)` every frame.
- `scenario_manifest.py` validates elements by kind and edits immutably (`add_element`,
  `remove_element`); n3 adds `set_weather`, `add_fire`, `remove_fire`. The store versions every
  edit; `simulation_handlers.py` maps proto requests to these edits and `ScenarioInvalid` to
  `INVALID_ARGUMENT`.
- `PersonElement` in the proto has no `skin`; the handler fills a default.
- Captures: `frames.jsonl`, `objects.json`, n3's `fire_perimeter.jsonl`; `bevy_capture.py` loads them.
- No behaviour-tree crate is used: none takes JSON in this shape, and determinism + wasm are needed.
