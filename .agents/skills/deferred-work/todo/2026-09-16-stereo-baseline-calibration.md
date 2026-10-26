# 2026-09-16 — Stereo depth: placeholder calibration awaits a measured baseline

**Category:** Planned scope deferred (placeholder data behind a stable contract)
**Source:** `docs/camera-elp-stereo.md` (ELP dual-lens module evaluation)
**Packages:** `surmap` (`src/surmap/geometry.py`, `StereoFramePair.calibration_id`)
**Consent:** Given by the developer when the camera evaluation landed. The ELP
module's lens baseline is unpublished, so depth output cannot be trusted until
it is measured; the pipeline is built against a placeholder `calibration_id`
with **`TODO` markers where the measured calibration must go**, so every stage
downstream (object points, map layers) is structurally complete now and a
successor swaps in the real calibration without moving the contract.
**Status:** Open

## What is left

Stereo reconstruction projects detected objects into the map frame
(`geometry.to_map_frame`). It is correct in shape today — points, centroids and
layer membership all flow — but the depth scale rests on an assumed baseline:

| Placeholder | Feeds | Real source |
|---|---|---|
| `cal-1` calibration record with a nominal baseline | every `ObjectPoints` position | a measured baseline + calibration session for the actual ELP unit |
| identity-pose replay fixtures | replay-test ground truth | a recorded session over surveyed ground truth (known object positions) |

Each placeholder carries a `TODO(calibration)` naming this record; the contract
does not move: `StereoFramePair` already carries `calibration_id`, so a
successor changes only the calibration data, never the geometry code.

**Depth accuracy figures were dropped from the evaluation summary** until the
measurement exists — an accuracy number computed from an assumed baseline
would be fiction. The successor records: measured baseline, calibration
procedure, and depth error against ground truth at survey distances.
