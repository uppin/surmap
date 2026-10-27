# Station SAM analysis policy

**Date:** 2026-10-27
**Type:** Feature
**Packages:** surmap

Added `surmap.survey.sam`: `SamDetection`, `RawFrame`, the
`SamDetector` protocol, `AnalysisGate` (serial admission;
`EVERY_FRAME` queues, `BEST_EFFORT_DROP` refuses and counts when
busy), and `InMemorySamDetector`. Verification: V1 fail→pass async
unit tests, run twice with no flake (379 passed at wrap, mypy strict
and Ruff clean).
