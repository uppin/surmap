# 2026-11-04 — Building textures that do not match the visual spec's character

**Category:** Future enhancement
**Source:** PR #104, stack `#sim-disaster-2` n5 (3 of 4), Wrap row — the planner's D1/D2 screenshot review
**Packages:** examples/bevy-sitl-poc, surmap
**Consent:** n/a — future enhancement (the planner, owner of every visual decision, approved D1 with these textures; the developer consented to planner-reviewed screenshots as V4)
**Status:** Open
**Plan:** follow-up PR off `main` after `#sim-disaster-2` lands (a visual round for the planner; decided at the #104 wrap)

## What is left

The visual spec gave each Overture preset a character; five presets read differently:

- `cement_block` (`building/facades/cement_block.facade.json`, Poly Haven `concrete_block_wall`)
  reads dark brown-grey, not grey CMU.
- `copper` (`building/roofs/copper.roof.json`, ambientCG `Metal047B`) is oxidised brown with no
  verdigris. Its `metallic` 0.8 is also overridden: the set has a roughness map and no ARM, and
  `textures.rs` `tiled_material`'s roughness-map path sets `metallic = 0.0` (so a greyscale map
  is not read as metal from its blue channel).
- The `plastic` and `wood` facades (`white_planks_clean`, `weathered_plank_siding`) are plank
  sets, not white PVC siding and painted clapboard.
- `eternit` (`corrugated_iron_02`) is ribbed metal sheet, not grey fibre-cement corrugate.
- `uv_scale` was checked against real sizes (6.5 cm brick courses, 20 cm blocks, 15 cm boards,
  30 cm tiles) only for brick.

Wanted: CC0 sets of the right character through the licence-gated sources (`asset_sources.py`,
pinned in `assets.lock.json`), a `metallic` that a roughness-map material keeps when its file
names one (a `tiled_material` change, tested), and `uv_scale` checked per preset in a still.

## Why it could not be done now

Each is a visual decision the planner owns, and the D1 review approved the four districts as
they read. Swapping sets at wrap time would grow a reviewed diff with a look nobody reviewed.

## What was done instead

All 25 presets ship with CC0 textures (17 Poly Haven, 3 ambientCG sets) and parse in tests; D1
passed: the four districts read distinctly.

## When it becomes possible

Now: pick the sets, fix the roughness-map `metallic`, then a D1 still per changed preset for the
planner.
