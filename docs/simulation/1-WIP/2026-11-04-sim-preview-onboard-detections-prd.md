# PRD: simulation preview — on-board detections with non-overlapping labels

**Date**: 2026-11-04
**Affects**: [docs/simulation/bevy-simulation.md](../bevy-simulation.md), [docs/agent.md](../../agent.md) (*Fleet tools*)
**Changeset**: [2026-11-04-sim-preview-onboard-detections.md](2026-11-04-sim-preview-onboard-detections.md)

## Problem

The agent can choose an on-board (Coral) detector model only for recorded runs (`run_demo`,
`run_rtabmap`). On a live simulation nothing it decides about detection is visible: the chat's
preview FPV shows RTAB-Map's keypoints and nothing else.

## Requirements

1. **The agent picks the model for a live simulation.** A fleet tool, `set_onboard_model`
   (`scenario_id`, `onboard_model`: a name from `list_onboard_models`, or `"none"` to stop),
   makes the station's stereo bridge run that model on the processed drone's left frames. The
   choice holds for the scenario: a page that connects later uses it too. An unknown model is
   `INVALID_ARGUMENT`, a model this station cannot run `FAILED_PRECONDITION`, an unknown scenario
   `NOT_FOUND`. The reply says which model now runs and whether a page streams the scenario.
2. **Detections reach the page with their frame.** The bridge's `status` reply for a pair carries
   that pair's detections (label, score, box in raw left-camera pixels, track id).
3. **The preview draws them.** In the FPV, each detection on the shown frame is outlined, and a
   label card (`<label> #<track> <score>%`) sits near it, joined by a leader with a dot at each
   end — the demo page's SAM cards (`layoutCards`): just above the object when free, else the
   nearest free spot; cards never overlap each other and stay inside the image.
4. **Same frame as the keypoints.** Boxes and cards are drawn on the held frame RTAB-Map answered
   for, so they never sit on another frame.
5. **`"none"` clears it.** After `set_onboard_model(..., "none")` the bridge runs no on-board
   model and the preview shows no boxes.

## Out of scope

Overlaying the SAM segmentation the bridge already runs; detections on the full page's stereo
panel; per-drone model choice; scoring detections against ground truth.
