# Visual spec — people moving by behaviour trees, a wind that changes

**Owner of every visual decision:** the planner. Builds on n3's visual spec; nothing there changes.
The implementer builds exactly this; where it is silent, it stops at the checkpoint and reports.

## Checkpoint (native, `--screenshot <dir> --at <t> --scenario wildfire-evacuation`)

- **B1** — t = 10 (calm phase, people wandering near the stand), t = 60 (wind veered to 300° and at
  10 m/s: flames and smoke visibly lean further, pines sway harder; people well clear of the front).

## People

- The existing capsule-and-head figure, rotated each frame to face its heading (yaw eased over
  0.3 s so turns do not snap).
- While moving: a vertical bob of 3 cm at 2 steps/s × (speed / 1.4 m/s), phase per id.
- Standing (`idle`, finished trees): no bob.

## Wind

No new visual: n3's vegetation, flames, embers and smoke already follow `WindModel`; the wind tree
only changes it over time.
