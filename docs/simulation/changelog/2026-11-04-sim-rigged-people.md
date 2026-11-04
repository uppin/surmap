# Rigged, animated people in the Bevy simulation

**Date:** 2026-11-04
**Feature:** Bevy simulation ([bevy-simulation.md](../bevy-simulation.md)) · Survey agent simulation tools ([agent.md](../../agent.md)) · PR #107 (stack `sim-traffic`, 2 of 3)

People in a scenario are now rigged CC0 humans instead of #111's Cesium Man. Each one walks and
runs with its feet keeping pace with its speed, and each can be posed the way a survey finds
people after a disaster: lying injured, sitting or waving for help. The figure
(`assets/behaviour/person.figure.json`) keeps main's one humanoid concept, `FigureModel`, which
gains an optional `rig`. The rig holds the named clips, the ground each locomotion clip covers,
the walk-to-run threshold, the crossfade, the rig's height and the coat and skin material slots.
The figure also gains `pose_models`, a pose drawn on its own model. No CC0 human on Poly Pizza
carries both a sit and a wave clip, so two Quaternius CC0 models are pinned in
`assets/assets.lock.json` with their animation names. `models/person/wave.glb` carries idle,
walk, run, wave and `Death` as `lie`, and `models/person/sit.glb` carries `SitIdle`. Cesium Man's
pin and credit are dropped. A figure without a model, or with its file missing, keeps the capsule.

`figure_anim.rs` (pure) picks clips by speed and pose. Players are seeked to simulation time every
frame, so a still and a recording replay exactly. A `person` takes an optional `pose` (`standing`,
`lying`, `sitting`, `waving`), `yaw_deg` (the way a posed person faces), `height_m` (0.9–2.2, which
scales the rig and its ground speeds) and `glb` (overrides the model file). Station and renderer
refuse the same bad values with the person's id and the reason. People in `object_tracks.jsonl`
carry `pose`, and a posed person is tracked even without a tree. A lying person's truth box is
horizontal. On the station side, `surmap.simulation.people` validates them, `add_element`'s
`PersonElement` takes `pose`, `height_m` and `yaw_deg`, and the preset `earthquake-survivors`
places a survivor lying, one sitting on rubble and one waving, with two rescuers walking between
them.

The detector cross-check (`scripts/score_sim_detections.py`) now counts person object-frames by
pose. At score 0.3 (found / in view):

| Shipped scene, 75 frames from t = 12 s | Cesium Man (#111) | Rigged CC0 |
|---|---|---|
| efficientdet-lite0 | 7/113 | 20/113 |
| ssd-mobilenet-v2 | 15/113 | 27/113 |
| ssdlite-mobiledet | 38/113 | 65/113 |

| `earthquake-survivors`, whole loop (200 frames) | efficientdet | ssd-mobilenet | ssdlite-mobiledet |
|---|---|---|---|
| standing | 0/66 | 0/66 | 18/66 |
| sitting | 7/38 | 5/38 | 18/38 |
| waving | 0/33 | 0/33 | 0/33 |
| lying | 0/6 | 0/6 | 0/6 |

Standing and sitting clear the 20 % bar for the best profile. Waving and lying do not after three
realism iterations: only the shirt wears the hi-vis coat, the survivors were moved onto open
ground, and the waving survivor was turned to face the route. That gap stays open as
`src/surmap/docs/todo/2026-11-04-waving-and-lying-people-undetected.md`.

At wrap, `actors.rs` (579 → 394 lines; `actors/figure_def.rs`, the figure definition and its
loader) and `scene_manifest.rs` (529 → 481; `scene_manifest/people.rs`, the person element and
its rules) were split, with no change in behaviour.

## Decided without review (deferred answers, awaiting the developer)

- [`deferred-answers/2026-11-04-earthquake-survivors-cast.md`](../deferred-answers/2026-11-04-earthquake-survivors-cast.md):
  the block's seven standing survivors give way to the preset's five.
- `examples/bevy-sitl-poc/docs/deferred-answers/2026-11-04-one-humanoid-model-concept.md`: n2's
  rig is merged into main's `FigureModel`, and main's names win.
- `examples/bevy-sitl-poc/docs/deferred-answers/2026-11-04-two-cc0-people-and-cesium-man-dropped.md`:
  two CC0 models are shipped, and Cesium Man's pin and credit are dropped.
- `examples/bevy-sitl-poc/docs/deferred-answers/2026-11-04-rig-scale-and-crossfade.md`: the rig
  scale is computed in millimetres, and the crossfade spans a quarter of the walk-to-run gap.

Verified by Rust tests (clip selection, rates and crossfade, `clip_time`, `rig_scale`, rig and
figure validation, the shipped clips against the lock's animation names, track `pose`, the horizontal
lying box, manifest rules, the golden `earthquake-survivors.json`). Python tests cover validation,
the preset, the tool and an agent turn on a real socket. The wrap reviewed native stills of
`earthquake-survivors` at t = 20 s (`people.png`, `person-close.png`): rigged people in coats, one
sitting on a slab, one waving and rescuers walking.
