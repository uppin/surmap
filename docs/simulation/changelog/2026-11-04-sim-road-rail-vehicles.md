# Road and rail vehicles that drive in the Bevy simulation

**Date:** 2026-11-04
**Feature:** Bevy simulation ([bevy-simulation.md](../bevy-simulation.md)) · Survey agent simulation tools ([agent.md](../../agent.md)) · PR #106 (stack `sim-traffic`, 1 of 3)

A scenario can now hold cars, buses, trucks and trains that drive. Each one is a `vehicle`
element of a class (`car`, `bus`, `truck`, `train`) with an optional behaviour tree, `glb`
override, `tint` and, for a train, `cars`. Class files under `assets/vehicle/` set the glTF, the
size, the wheel nodes and the driving limits, and they are data, so changing one needs no
rebuild. `vehicle.rs` (pure, deterministic) drives a vehicle toward the goal its tree's running
leaf proposes. Speed eases within the class's acceleration and braking, a stopping goal is crept
onto without overshoot, and the heading turns at most at the class's rate, so a vehicle never
circles a goal. Wheels spin with the distance travelled. A train's carriages trail the locomotive
along the path it travelled. The models are pinned from poly.pizza: the Quaternius car, truck,
locomotive and wagon (CC0), and one named CC BY 3.0 bus, "Bus" by Poly by Google, by the
developer's decision of 2026-11-04. `model_scale` and `model_yaw_deg` fit a glTF to metres and
to the vehicle's forward.

`object_tracks.jsonl` objects gained `kind` and `yaw_deg`, and they include every tracked
vehicle (a train as its locomotive). `load_bevy_capture` reads them as `object_kinds` and
`object_yaw_deg`. Moving vehicles are never in `ground_truth.json`. On the station side, the
`vehicle` kind is validated by the renderer's rules (`surmap.simulation.vehicles`). The agent's
`add_element` takes a `VehicleElement`, the behaviour tools take a vehicle as a target, and the
preset `street-traffic` puts cars, a bus, a truck and a six-carriage train on the shipped block.

The on-board detector cross-check (`detection_eval`) now knows `bus`, `truck` and `train`. It
places tracked vehicles by their class footprint and heading, and it counts a vehicle found under
another vehicle's label separately. One recorded lap of `street-traffic`, scored at 0.3 (object-frames
found / in view):

| Profile | car | bus | truck | train |
|---|---|---|---|---|
| efficientdet-lite0 | 12/90 | 5/16 | 8/14 | 0/6 |
| ssd-mobilenet-v2 | 2/90 | 0/16 | 1/14 | 0/6 |
| ssdlite-mobiledet | 34/90 | 1/16 (+6 found as another vehicle) | 10/14 | 0/6 |

Car, bus and truck clear the ≥ 20 % bar for the best profile. Two changes got the bus and the
truck there: a school-bus-yellow bus, and a truck moved to the cross street and scaled 1.25. The
train does not clear it after three realism iterations, and that gap stays open as
`src/surmap/docs/todo/2026-11-04-train-detectors-blind.md`. The detector-floor test
(`tests/test_sim_detector_realism_e2e.py`) was not extended to vehicles, because a floor needs a
committed frames fixture of `street-traffic` and none is committed. The table above is the
recorded command's result.

At wrap, `actors.rs` (669 → 414 lines; `actors/tick.rs`, `actors/model.rs`),
`scene_manifest.rs` (538 → 480; `scene_manifest/environment.rs`) and
`scene_manifest/tests.rs` (511 → 409; `tests/nature.rs`) were split, with no change in
behaviour.

Verified by Rust tests (the `Drive` limits, reaching a path's end, determinism, carriages through
a 90° bend, wheel angle, the manifest rules, the golden `street-traffic.json`, the track line).
Python tests cover validation, the preset, the tool, the capture's kinds and headings, and an
agent turn on a real socket. The wrap also reviewed a native still and a 64-frame recording. The
bus's nose leads and its wheels sit on the road, the truck's cab leads, and the train is on its
line.
