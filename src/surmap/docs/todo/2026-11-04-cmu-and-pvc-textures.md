# 2026-11-04 — True CMU and PVC siding textures

**Category:** Future enhancement
**Source:** PR #105, stack `#sim-disaster-2` n6 (4 of 4), Wrap row
**Packages:** examples/bevy-sitl-poc
**Consent:** n/a — polish beyond the approved review (the planner approved the D1 district stills)
**Priority:** 4
**Status:** Open
**Plan:** ⚠️ recorded debt — no PR planned; a preset JSON and `assets.lock.json` change once CC0 sets exist (decided at the #105 wrap)

## What is left

The `cement_block` facade uses ambientCG `PavingStones125A`, a banded masonry, and the `plastic`
facade uses Poly Haven `brown_planks_05`, a grey lap siding. Neither is the spec's character: a
grey concrete-masonry-unit (CMU) block wall and white PVC (vinyl) siding. Wanted: CC0 PBR sets of
each, pinned in `assets.lock.json`, with a measured `uv_scale`.

## Why it could not be done now

Neither ambientCG nor Poly Haven has a CC0 grey CMU or white PVC siding set; the chosen sets were
the closest, and the industrial and suburban stills passed review with them.

## What was done instead

`PavingStones125A` (grey, block-like courses) and `brown_planks_05` (horizontal lap boards, which
`plastic`'s `colourable` tints) — each closer to the spec than the sets they replaced.

## When it becomes possible

When a CC0 source publishes such sets, or a procedural CMU / siding texture is generated at startup
(as the soft-disc sprite is).
