# Visual spec — weather, wind-swept vegetation and wildfire

**Owner of every visual decision:** the planner. The implementer builds exactly this; where it is
silent or a value does not work, it stops at the checkpoint and reports (screenshot + one line).
*(tune)* marks first values the planner adjusts after review. Builds on the photo-real block of
#89 (`docs/simulation/bevy-simulation.md`, *Look*).

**Every value below ships as runtime JSON** (`assets/fx/*.fx.json`, `assets/species/*.species.json`,
fire and weather fields in the manifest — changeset § *Everything tunable is runtime JSON*). The
implementer writes these numbers into those files, never into Rust; review corrections are JSON
edits.

## Checkpoints (native, `--screenshot <dir> --at <t> --scenario <id>`)

- **W1 vegetation + wind** — `wildfire-edge` with `fires: []`, t = 5 and t = 6 (motion visible
  between them).
- **W2 fire** — `wildfire-edge` at t = 5, 40, 120.
- **W3 rain** — `flood-street` at t = 20.

## Vegetation (ported from `~/Code/FeroniaDemo`)

- Pines: `meshes::pine(true)` near (< 40 m), `pine(false)` far, on one `ExtendedWindAffectedMaterial`
  with the demo's palette (bark `srgb(111,82,55)`, needles `srgb(56,94,14)…srgb(107,145,31)`) **darkened
  20 % and desaturated 15 %** for late-summer dryness. `pine_wind` scaling as the demo. Heights
  9–15 m (seeded), random yaw.
- Grass: the demo's Eidolon instanced grass, tinted dry: base `srgb(0.42, 0.38, 0.20)`, tip
  `srgb(0.62, 0.55, 0.30)` *(tune)*; only inside `grass` vegetation areas.
- Inside a fire's burnt area (§ Fire), pines turn to charred trunks: needles hidden, bark
  `srgb(0.06, 0.05, 0.045)`; grass instances are removed.

## Wind

`GlobalWind.current` from `WindModel::feronia(t)`, updated every frame; the demo's `previous/current`
blending stays. At 6 m/s pines visibly sway, grass streams downwind.

## Fire (bevy_hanabi)

Per fire, emitters along the perimeter (one per 2 m of perimeter, re-placed every 0.5 s):

- **Flames:** additive, HDR colour gradient `srgb(1.0, 0.85, 0.45)` ×12 → `srgb(1.0, 0.35, 0.05)` ×6
  → transparent; size 0.6→1.4 m; lifetime 0.6–1.0 s; upward speed 2.5 m/s plus **wind lean**:
  velocity += 0.6 × wind vector. Bloom picks them up (chase view only).
- **Embers:** small (0.05 m) orange `srgb(1.0, 0.45, 0.1)` ×8, lifetime 2–4 s, rise 3 m/s, drift
  with 1.0 × wind, gravity −1 m/s².
- **Smoke:** alpha-blended, not additive; colour `srgb(0.32, 0.30, 0.28)` → `srgb(0.55, 0.53, 0.50)`,
  opacity 0.55 → 0; size 2→12 m; lifetime 12–18 s; rise 1.8 m/s, drift 1.0 × wind, so plumes bend
  downwind. Only when `smoke: true`.
- **Burnt ground:** a decal-like flat mesh per fire, rebuilt every 0.5 s from the perimeter, 2 cm
  above ground, material `srgb(0.07, 0.06, 0.05)`, roughness 1.0; the front edge (outer 1.5 m)
  glows `emissive srgb(1.0, 0.3, 0.05)` ×4 *(tune)*.
- The fire lights the scene: one point light per fire at the perimeter centroid, 2 m up,
  colour `srgb(1.0, 0.55, 0.2)`, intensity scaled with perimeter length *(tune)*, no shadows.

## Rain

`rain_mm_h > 0`: streaks (0.01 × 0.5 m stretched billboards), colour `srgb(0.7, 0.72, 0.75)`,
opacity 0.35, count ∝ rain (8 mm/h ≈ 3 000 live), falling 7 m/s plus 1.0 × wind, in a 60 m box
around the active camera. Ground and asphalt get `perceptual_roughness × 0.6` and colour ×0.85 while
it rains (wet look). Fog from `weather.fog_visibility_m`.

## Eyes

Rain and smoke render in the eye cameras too (they are what a real stereo rig sees); flames and
embers too. Bloom stays chase-only (spec of #89).
