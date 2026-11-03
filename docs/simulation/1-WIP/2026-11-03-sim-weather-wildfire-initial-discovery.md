# Initial discovery — weather, wind-swept vegetation and wildfire

**Changeset:** `2026-11-03-sim-weather-wildfire.md`

- **Reference: `~/Code/FeroniaDemo`** (the developer's Codex-built demo, Bevy 0.18.1 / Feronia 0.8.4
  / `bevy_eidolon` 0.4.1, WebGPU). Pines: procedural `meshes::pine(detailed)`, one
  `ExtendedWindAffectedMaterial` whose `WindAffectedExtension.current/previous` follow `GlobalWind`
  through `sync_pine_wind` with `pine_wind` damping. Grass: Eidolon instanced
  `InstancedWindAffectedMaterial` with `GpuCullComputePlugin`, scattered by
  `instancing::scatter_layer`. Wind: `GlobalWind::from(WindPreset::…)`; a change sets `previous =
  current` then the new `current`, and Feronia blends.
- **Feronia 0.8.4** (`~/.cargo/registry/…/bevy_feronia-0.8.4`): `Wind { direction: Vec2, strength,
  micro_strength, s_curve_strength, bop_strength, twist_strength, … }`, `GlobalWind`,
  `WindAffected`, examples `scatter_extended_trees.rs`, `full.rs`.
- **bevy_hanabi 0.18.0** targets Bevy `^0.18` (crates.io, checked 2026-11-03); GPU compute
  particles, WebGPU only — the PoC is WebGPU-only already.
- **SurMap state** (`main` 7c12264): the declarative manifest (`scene_manifest.rs`,
  `scenario_manifest.py`), `SimulationTools` with the SQLite store, `/sim/` serving, `--scenario`,
  the recorder (`record.rs`) and capture loader (`bevy_capture.py`).
- Baseline (main 7c12264, from #91's CI): every check green; pytest 1832 passed.
