# Discovery: map floor manifest contract

Scenarios are `scene.json` manifests validated twice: `surmap.simulation.scenario_manifest.validate_manifest` (station) and `SceneManifest::from_json` (Rust renderer), same rules. Top-level optional sections (`weather`, `fires`) are the pattern for a new `map_floor`. Asset paths must be relative, inside `assets/`. No GPS anchor exists in any manifest today.
