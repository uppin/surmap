# The sim-disaster-2 sweep: correctness and visual polish of the stack's TODOs

**Date:** 2026-11-04
**Feature:** Bevy simulation ([bevy-simulation.md](../bevy-simulation.md)) · Survey agent simulation tools ([agent.md](../../agent.md)) · PR #105

The sweep node of stack `#sim-disaster-2` carried the TODOs that #100, #101 and #104 recorded on
their code. At the TODO gate (developer, 2026-11-04) it took the **correctness** group (C1–C4)
and the **visual polish round** (P1–P6). Two were deferred with consent, each recorded in its
file: `2026-11-03-fire-eye-mount-pitch` and `2026-11-04-legacy-buildings-burn`. Ten solved TODO
files were deleted. Every value stays runtime JSON.

Correctness:

- **C1 — district-resolved floors.** `add_building_fire(..., assets_dir=)` gives a building
  without `floors` the `floor(height / floor_m)` of the district holding its centre and refuses a
  floor past it; the store passes its `assets_dir`, so the `add_building_fire` tool answers
  `INVALID_ARGUMENT`. A district preset the station cannot read is left to the renderer (no floor
  height is guessed).
- **C2 — recorded dynamics fixtures.** Native recordings of `wildfire-evacuation` and
  `downtown-blaze` under `tests/fixtures/bevy_capture_dynamics/` (68 KB and 28 KB, no frames)
  prove `fire_perimeter.jsonl`, `object_tracks.jsonl` and `building_fires.jsonl` end to end: no
  evacuee inside the front, and the blaze climbs from floor 3 and never un-burns.
- **C3 — per-stand grass.** `vegetation::grass_instances(stand, def)` places a stand's clumps from
  its own seed, a pure function the renderer instances exactly; Feronia's global `WorldSeed` no
  longer decides a stand's grass.
- **C4 — load-independent differencing budget.** The frame-budget test takes the best of three
  `time.process_time()` runs against the same 0.05 s budget (4 000 points at 5 Hz).

Visual polish:

- **P1 — flame tongues.** fx `flipbook: {texture, columns, rows, fps}`; `flames` and
  `window_flames` play OpenGameArt "Animated Fire" (`fire1_64.png`, CC0, 10 × 6 frames of 64 px)
  upright (`stretch` 1.0), their gradient intensities scaled × 0.4 so the tongues resolve.
- **P2 — texture character.** `cement_block` `PavingStones125A`, `copper` the verdigris
  `Metal058C`, `wood` `WoodSiding009` (ambientCG); `plastic` `brown_planks_05`, `eternit`
  `asbestos_sheet_02` (Poly Haven); `uv_scale` rechecked. `textures::pack_metallic_roughness`
  repacks a roughness-only map so its blue channel carries the preset's `metallic`.
- **P3 — per-window glow.** `look.json` `fire.glow_variation` (0.5) and `fire.glow_flicker_hz`
  (1.5); the glow is unlit, one vertex colour per window rewritten each frame from
  `FireLook::window_glow`; `fire.json` `glow_colour` `[1.0, 0.32, 0.05]` × `glow_intensity` 0.8.
- **P4 — pre-warmed smoke.** fx `prewarm_s`; in screenshot mode the one global effect clock runs
  ahead at most 0.2 s per frame until the longest `prewarm_s` has passed (`smoke` 18 s,
  `building_smoke` 25 s).
- **P5 — facing cue.** `person.figure.json` `visor: {size_m, offset_m, colour}`, a dark box on
  the front of the head.
- **P6 — fire lights.** The light-on / light-off still pairs (W2 t = 40, D2 t = 400) were
  indistinguishable in daylight — a point light cannot compete with the sun — so the lights keep
  their values; they matter at dusk and night only.

Screenshot mode adds two close stills (`close_shots.rs`): `flame-close.png` (8 m outside the
front, 2 m up) and `person-close.png` (4 m in front of the first figure, at its head).

Verified: Rust and Python tests for C1–C3 and P1–P5's contracts (the fx fields, pre-warm steps,
window glow, metallic packing, visor, grass placement); C4 10/10 under full CPU load (`yes` on
every core, load average 10–14); and the planner's review of native stills, with the developer's
consent — D1 textures (downtown, suburban, industrial), W1 per-stand grass with sway (mean
absolute pixel difference 3.2 between t = 5 and t = 6), D2 pre-warmed smoke, B1 people and the
P6 pairs at the green commit, then review round 1 (saturated, distinct window panes; wispy flame
tongues in `flame-close.png`; the visor in `person-close.png`), all approved. Follow-ups:
`src/surmap/docs/todo/2026-11-04-{flame-flipbook-resolution,cmu-and-pvc-textures,texture-uv-scale-measured}.md`.

Part of stack `#sim-disaster-2` (4 of 4): `main ← n3 #100 ← n4 #101 ← n5 #104 ← n6 #105`. Green
wave 4 of 4; it needs #100, #101 and #104, whose TODOs it carries, and blocks nothing.
