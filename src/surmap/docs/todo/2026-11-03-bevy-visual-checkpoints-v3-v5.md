# 2026-11-03 — Visual checkpoints V3–V5 of the Bevy simulation

**Category:** Deferred scope (changeset milestone M4, visual spec §1, §4.4, §7)
**Source:** PR #89, stack `#sim-disaster` n1
**Packages:** examples/bevy-sitl-poc
**Consent:** Developer, 2026-11-03: "let's wrap the PR with TODO and we'll address the correctness in next PRs".
**Priority:** 2
**Status:** Open

## What is left

- V3: the picked CC0 props (`concrete_road_barrier` ×5, `old_tyre` ×4, `Barrel_01` ×3,
  already pinned in `assets.lock.json`) placed in `scene.json`; debris scatter density.
- V4: the eye sensor model (vignette `1 − 0.30 r⁴`, shot and read noise seeded by
  `frame_id · 2 + eye`) as a full-screen pass on the eye cameras only.
- V5: the same stills in Chrome/WebGPU (`trunk serve`) for parity with native.
- Texture variety: five tiled materials and identical buildings/slabs/cars are strong
  perceptual aliasing for loop detection; add variants before judging closures.
