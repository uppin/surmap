# CM5 incremental point emitter

**Date:** 2026-10-27
**Type:** Feature
**Packages:** surmap

Added `IncrementalPointEmitter` in `surmap.survey.points`: `emit`
forwards only points whose (designation, position) is new to the
stream, in input order, suppressing duplicates within a batch;
`reset` starts a fresh stream. Verification: V1 fail→pass unit tests
(375 passed at wrap, mypy strict and Ruff clean).
