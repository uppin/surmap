# Visual spec — building presets (walls, roofs, glazing, districts) and building fires

**Owner of every visual decision:** the planner. The implementer builds exactly this and writes
every value into the runtime JSON files (changeset § *Everything is runtime JSON*), never into
Rust; review corrections are JSON edits. *(tune)* marks first values the planner adjusts.

## Checkpoints (native, `--screenshot <dir> --at <t> --scenario <id>`)

- **D1 look** — `district-showcase` at t = 1 from the chase view and one eye; one shot per district
  (the chase camera framed on each district rectangle, via a `--look-at <district id>` flag or four
  scenario copies with the camera moved — implementer's choice, reported).
- **D2 fire** — `downtown-blaze` at t = 15 (tower floor 3 alight), 120 (fire climbed ~2 floors),
  400 (neighbour ignited downwind), 900 (lower floors burnt out, charred bands).

## Textures

CC0 PBR sets (Poly Haven first, then ambientCG), 2k, fetched through the existing licence-gated
sources and pinned in `assets.lock.json`. Pick by character; the planner reviews:

| Facade | Character | | Roof | Character |
|---|---|---|---|---|
| brick | red-brown running bond, mortar visible | | roof_tiles | terracotta pantiles |
| cement_block | grey CMU, 40×20 cm | | slate | dark blue-grey slate |
| clay | sand-coloured render over clay | | metal | standing-seam steel |
| concrete | board-formed / smooth cast, stained | | copper | verdigris copper |
| glass | (no texture — glazing) | | concrete | weathered flat slab |
| metal | corrugated / cladding panels | | gravel | grey gravel ballast |
| plaster | white plaster (existing `white_plaster_02`) | | tar_paper | black bitumen sheet |
| plastic | white PVC siding | | eternit | grey fibre-cement corrugate |
| stone | ashlar limestone | | grass | green roof (moss/grass) |
| timber | dark horizontal timber boards | | thatch | straw thatch |
| wood | painted wooden clapboard | | wood | wood shingles |
| | | | plastic | translucent corrugated (solid ok) |
| | | | glass | glazing material |
| | | | solar_panels | dark-blue PV grid, low roughness |

`uv_scale` so bricks read ~6.5 cm courses, blocks 20 cm, boards 15 cm, tiles 30 cm *(tune)*.
`colourable` facades (plaster, clay, plastic, wood, metal) take `facade_colour` as a multiply
tint; the others ignore it.

## Glazing

- **Punched:** recessed 12 cm, panes `glass` = `srgb(0.06, 0.07, 0.08)` roughness 0.08 reflectance
  0.5 (as #89), frame `srgb(0.18, 0.18, 0.19)` 6 cm border; `window_ratio` 0.30 old-town/suburban,
  0.45 downtown, 0.15 industrial *(tune)*. Ground floor of downtown buildings: shopfront (ratio 0.8).
- **Curtain wall:** the whole facade is glass, base `srgb(0.10, 0.14, 0.17)`, roughness 0.05,
  reflectance 0.6, metallic 0 — it must mirror the HDRI sky; mullions `srgb(0.25, 0.26, 0.28)`
  metallic 0.8, 8 cm, grid 1.5 m × floor height; spandrel band 0.9 m at each slab, darker
  `srgb(0.07, 0.08, 0.09)`.

## Roofs

- `flat`: a 0.6 m parapet in the facade material; roof plane in the roof material.
- `gabled`: ridge along the long axis, 35° pitch; `hipped` 30°; `pyramidal` 30° — 0.3 m eave
  overhang, gable ends in the facade material.

## Districts

| District | Facades (weight) | Roofs | Shapes | Colours | floor_m |
|---|---|---|---|---|---|
| old-town | brick .4, plaster .35, stone .25 | roof_tiles .7, slate .3 | gabled .6, hipped .4 | plaster ochres/creams | 3.2 |
| downtown | glass .45, concrete .3, stone .15, metal .1 | concrete .4, gravel .4, metal .2 | flat 1.0 | cool greys | 3.6 |
| industrial | metal .5, cement_block .35, brick .15 | metal .6, eternit .4 | flat .5, gabled .5 | faded blue/grey/green | 5.0 |
| suburban | wood .4, plaster .3, plastic .2, brick .1 | roof_tiles .5, wood .3, slate .2 | gabled .6, hipped .4 | soft pastels | 2.8 |

## Building fire

- **Burning floor:** every window on it: panes hidden (broken), interior emissive glow
  `srgb(1.0, 0.45, 0.12)` ×10 *(tune)* on a plane 0.5 m inside; `window_flames` per window —
  additive, `srgb(1.0, 0.8, 0.4)` ×14 → `srgb(1.0, 0.3, 0.05)` ×6 → transparent, size 0.8→1.8 m,
  lifetime 0.5–0.9 s, out of the window then up the facade (up 2 m/s, wind coupling 0.5).
  Curtain walls: panels of the floor shatter (hidden) and flames come out along the whole band.
- **Smoke:** `building_smoke` from the top burning floor's windows and the roof — alpha, colour
  `srgb(0.12, 0.11, 0.10)` → `srgb(0.35, 0.34, 0.33)`, opacity 0.7 → 0, size 3→18 m, lifetime
  15–25 s, rise 2.5 m/s, drift 1.0 × wind. Thick and dark — denser than the wildfire's.
- **Embers** as n3's.
- **Charring:** a burning and a burnt floor's facade band switches to the preset's `burnt` material
  (sooted, near-black `srgb(0.05, 0.045, 0.04)`, roughness 1.0), soot streaks above windows of
  burnt floors (a 1.5 m gradient band) *(tune)*; a fully burnt building's roof → roof `burnt`.
- **Light:** one point light per burning building at the top burning floor, colour
  `srgb(1.0, 0.5, 0.18)`, intensity ∝ burning floors, no shadows.
