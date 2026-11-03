# Building presets and building fires - PRD

**Date**: 2026-11-03
**PRD Type**: Enhancement

## Affected Features

- **Primary Feature**: Bevy disaster simulation ([bevy-simulation.md](../bevy-simulation.md))
- **Related Feature**: [Survey agent](../../agent.md) — Simulation tools; the map's Overture layer

## Summary

Buildings get wall and roof presets named after Overture's building attributes (brick, glass,
roof_tiles, slate…), roof shapes, punched windows or glass curtain walls. The agent styles a
district — a rectangle with a weighted mix — and overrides single buildings. Buildings can burn:
fire climbs floor by floor, jumps to neighbours downwind and is lit by a wildfire reaching them.
All of it is runtime JSON.

## Proposed Changes

### What's Changing

- Facade, roof, district and building-fire JSON files; manifest `districts`, `building_fires` and
  building style fields.
- Rendering: textured walls/roofs, roof shapes, glazing, per-floor fire, smoke, charring.
- Tools to list presets, set/remove districts, style a building, add/remove building fires.
- Captures carry `building_fires.jsonl`; burning buildings make behaviour-tree people flee.

### What's Staying the Same

Existing scenarios render as before (legacy `material`/`windows`); no Overture geometry import;
passive survey only.

## Acceptance Criteria

1. Every Overture facade and roof value has a shipped preset; a new preset is a file.
2. A district's mix is deterministic and weighted; a building's own field wins.
3. A building fire climbs and burns out per its tuning; it spreads downwind farther than upwind;
   a wildfire reaching a building ignites it.
4. The agent builds `downtown-blaze` through tools; the renderer accepts what the store writes.
5. D1/D2 screenshots pass the planner's review.
