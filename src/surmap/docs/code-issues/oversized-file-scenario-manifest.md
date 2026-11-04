# oversized-file: src/surmap/simulation/scenario_manifest.py

**Location:** `src/surmap/simulation/scenario_manifest.py`
**Category:** oversized-file
**Detected:** 2026-11-04 by `/pr-wrap` step 4 (file-length gate)
**Metrics:** 495 → 509 lines (limit 500)
**Restructure:** required — left for the `#drone-fleet` sweep node (stack-shared file)
**Status:** Open (a record exists only while the issue is open — fixing it deletes the file)

## Measurement history

| Run | Lines | Note |
|---|---|---|
| 2026-11-04 | 495 → 509 | `pr-1-drone-fleet` (#116): `drone_nest` in `ELEMENT_KINDS`, nest validation and nest drone ids in `element_ids`; left for the #drone-fleet sweep node — later stack PRs edit this file too, so splitting it here would conflict every node above |

## What would close it

Move per-kind element validation into a `scenario_elements.py` module, leaving `scenario_manifest.py` as load/validate entry points.
