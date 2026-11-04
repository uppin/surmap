# Initial discovery — sim-disaster-2 sweep

- Grass: `vegetation/grass.rs::sow_grass` inserts Feronia's global `WorldSeed(stand.seed)` per
  stand, so the last-sown stand's seed decides every stand's scatter.
- Metallic: `textures.rs::tiled_material` zeroes `metallic` for roughness-only sets (ambientCG),
  because Bevy reads metalness from the texture's B channel.
- Glow: `building/look.rs::FireLook` has one glow for every window of a burning floor.
- Figure: `actors.rs::FigureDef` (`behaviour/person.figure.json`, `deny_unknown_fields`) has gait only.
- Fx: `fxdef.rs::FxDef` has no flipbook or pre-warm; particles are soft discs.
- `building_presets.py::add_building_fire` checks nothing against floors.
- `tests/test_moving_differencing.py:89-92` times with `perf_counter` against 0.05 s.
- Captures: recorder writes `fire_perimeter.jsonl`, `object_tracks.jsonl`, `building_fires.jsonl`;
  only line builders and loaders are tested, never a real run.
