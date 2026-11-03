# oversized-file: src/surmap/demo/datasets.py

**Location:** `src/surmap/demo/datasets.py` — whole file
**Category:** oversized-file
**Detected:** 2026-11-03 by `/pr-wrap` step 4 (file-length gate; `/analyze-code-issues` not run on `surmap` yet)
**Metrics:** 989 lines (2026-11-03; was 743 at this PR's merge base) (limit 500) · coverage not measured
**Restructure:** required — split into focused modules, `/code-restructuring` territory
**Status:** Open (a record exists only while the issue is open — fixing it deletes the file)

## Measurement history

| Run | Lines | Note |
|---|---|---|
| 2026-11-03 | 743 → 989 | dataset gallery PR (#94): gallery metadata on `DatasetSpec`, KITTI colour variant, `oxts` GPS extraction, trust-on-first-use SHA, and the generated all-drives registration. The file was already over the limit at the base; this PR grew it further, so the split is this PR's debt to record, not to land inside a feature PR |

## What the tool found

A 989-line module, twice the 500-line limit, holding the dataset registry, all
format extractors (EuRoC zip, KITTI raw, NTU VIRAL rosbag), download/verify,
and preparation. Coverage was not measured; "not measured" is not "clean".

## Why it matters here

Every new data source lands here, and the gallery work showed the cost: one
PR had to touch the registry, one extractor, the verifier and the generated
registration in a single file nobody can hold in their head.

## What would close it

A mechanical split at the seams already visible in the file, each module
under ~300 lines: `demo/datasets_registry.py` (`DatasetSpec`, `DATASETS`),
`demo/datasets_kitti.py` (KITTI extraction + calibration), `demo/datasets_bags.py`
(NTU VIRAL rosbag), leaving download/verify and `PreparedDataset` in
`datasets.py`, with public names re-exported so existing imports keep working.
Same green before and after; `/code-restructuring` territory, its own PR.

## Verified by hand

2026-11-03 — `wc -l` at the merge base (743) and at the wrap (989); the seams
above were read from the file's class and function list, not inferred. No
analyzer ran, so complexity and coverage are unknown.
