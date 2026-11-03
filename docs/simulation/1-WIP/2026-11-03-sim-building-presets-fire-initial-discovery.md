# Initial discovery — building presets and building fires

- "Meta Maps": no code by that name; the station's map speaks Overture (`map_layers.py`,
  `overture-buildings`, pinned release), whose building attributes are `facade_material`,
  `roof_material`, `facade_color`, `roof_color`, `roof_shape`, `height`, `num_floors`. The
  developer chose that vocabulary for preset names, without importing geometry.
- `Building { id, material, size_m, position_enu, yaw_deg, tint, windows }` in
  `scene_manifest.rs`; `world.rs::building` draws one cuboid + a punched pane grid; the roof is the
  cuboid's top. `BuildingElement` in the proto: `material`, `size`, `position`, `yaw_deg`, `windows` bool.
- Materials: `MaterialDef` in the manifest — textured (`base_color`, `normal`, `arm`, `uv_scale`) or
  solid; textures pinned in `assets/assets.lock.json` (CC0, Poly Haven), loaded by `textures.rs`.
- n3 (#100): fx loader/emitters (`fxdef.rs`), `FireSpec::burnt`, `WindModel`; n4 (#101):
  `World.burning_areas` for `near_fire`/`flee_from_fire` (added to n4's contract for this layer).
- Licence gate and sources: `asset_sources.py` (`PolyHaven`, `AmbientCg`), `licences.py`.
