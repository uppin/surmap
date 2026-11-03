# 2026-11-03 — Flame tongues that resolve at survey distance (flipbook sprites)

**Category:** Future enhancement
**Source:** PR #100, stack `#sim-disaster-2` n3 — planner's V4 screenshot review, checkpoint W2
**Packages:** examples/bevy-sitl-poc, surmap
**Consent:** n/a — future enhancement. The planner (developer-consented V4 reviewer) accepted W2
with this TODO: "at survey distance the front reads as a saturated orange glow under the smoke,
but individual flame tongues do not resolve".
**Priority:** 2
**Status:** Open

## What is left

- A CC0 flame flipbook texture (an atlas of tongue frames), fetched and pinned in
  `examples/bevy-sitl-poc/assets.lock.json` like the other assets.
- Two optional fields in the fx JSON (`fxdef.rs` `FxDef`): `texture` (the atlas path, validated
  like every asset path by `scene_manifest.rs` and `surmap.simulation.scenario_manifest`) and
  `frames` (`[columns, rows]`, plus a frame rate or "over the lifetime").
- `fx.rs`: a hanabi flipbook (`FlipbookModifier` with a sprite-index over the particle age)
  instead of the generated soft disc when `texture` is set.
- `fx/flames.fx.json` switched to it; W2 re-shot at t = 5, 40, 120 s (`fire-eye.png` and
  `overview.png`) and reviewed against the flame row of the visual spec (now
  `docs/simulation/bevy-simulation.md` § *Weather, wind and fire*).

## Why it could not be done now

The PR's contract was soft particles judged by the planner; two review rounds tuned colour, size,
stretch and glow in JSON as far as soft discs go. Tongues need an image asset and a new fx field
in Rust and Python — new scope a late visual review should not grow into a reviewed diff.

## What was done instead

Flames are additive, stretched (`stretch` 1.8) soft discs (`shape: soft_disc`, `softness` 0.7)
with an HDR gradient; the burnt ground's glowing rim and the fire's point light carry the front.
Accepted at W2 as a glow, not tongues.

## When it becomes possible

Now — any follow-up PR off `main` once #sim-disaster-2 n3 (#100) has landed.
