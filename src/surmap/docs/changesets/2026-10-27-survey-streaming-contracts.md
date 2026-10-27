# Survey streaming proto contracts

**Date:** 2026-10-27
**Type:** Feature
**Packages:** surmap

Added `proto/surmap/survey/v1/survey.proto` with `Cm5SurveyService` and
`StationSamService` (both BIDI), the shared calibration/frame input,
designated `PointBatch`/`VideoFrameOut` output, and `SamFrameDetections`.
Checked in the generated bindings with `scripts/gen_survey_rpc.py` and
added `surmap.survey.designations` helpers. Verification: V1 fail→pass
contract tests (369 passed at wrap, mypy strict and Ruff clean), plus a
V3 grep proving no `overstack` references remain under `.agents/`.
