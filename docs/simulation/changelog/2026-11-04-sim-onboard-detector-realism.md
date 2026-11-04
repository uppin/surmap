# On-board COCO detectors find the simulation's cars and people

**Date:** 2026-11-04
**Feature:** Bevy simulation ([bevy-simulation.md](../bevy-simulation.md) § *On-board detectors (measured)*)

On the PR #89 capture the three Coral COCO profiles found no car in any of its 90 frames, and
every detection was a false positive. The simulation now gives them something to find, and a
scorer measures it:

- **Cars**: the Poly Haven `covered_car` (a car under a tarp) is replaced by the Khronos
  **Car Concept** (CC-BY-4.0, Eric Chadwick / Darmstadt Graphics Group GmbH). A model can drop
  its normal maps (`normal_maps: false`): Bevy ignores `KHR_texture_transform` on a normal
  texture, and the paint's tiled flake map rendered as speckle.
- **Survivors**: every figure wears the Khronos **Cesium Man** (CC-BY-4.0, Cesium) instead of
  the capsule, posed from its walk clip on the sim clock and tinted with the person's coat
  (`person.figure.json` `model`); every survivor is a `person` ground-truth box (`body_m`).
- **Colour**: `--record … --colour` also writes the left eye in RGB (`frames/left_rgb/`,
  `left_rgb_ref`, `CapturedFrame.left_rgb_ref`), as the ELP module's MJPEG stream gives the
  detector; the grey eyes are unchanged.
- **Licences**: a lock pin carries `attribution`; a test refuses a CC BY pin without one.
- **Scoring**: `surmap.simulation.detection_eval` and `scripts/score_sim_detections.py`; the
  recorded `tests/fixtures/bevy_sim_detector_capture/` and the opt-in
  `tests/test_sim_detector_realism_e2e.py` (CI `coral-e2e`).

Measured on the same 75-frame pass, colour, score 0.3 — cars 0/46 → 9/46 (efficientdet-lite0),
0/46 → 15/46 (ssdlite-mobiledet); people 1/113 → 7/113 and 35/113 → 38/113 against the
capsules. False positives did not go down. Non-COCO kinds (buildings, rubble, debris, fire)
stay out of on-board detection by design.
