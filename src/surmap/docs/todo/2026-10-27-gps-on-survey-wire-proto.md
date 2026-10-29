# 2026-10-27 — GpsCheckpoint on the survey wire proto

**Category:** Future enhancement
**Source:** PX4 SITL session bridge (PR #18); `docs/simulation/px4-sitl.md`
**Packages:** surmap
**Consent:** n/a — future enhancement (explicitly deferred from first Machine 3 PR)
**Status:** Open

## What is left

Add `GpsCheckpoint` (or equivalent) to `proto/surmap/survey/v1/survey.proto`
and the CM5 / station stream path so live and recorded sessions carry GPS
on the wire, not only as `mav0/gps0/data.csv` on disk.

## Why it could not be done now

GPS exists in `surmap.types.GpsCheckpoint` and offline EuRoC export, but
the survey proto only carries calibration + frames today. Expanding the
wire contract is a separate contract-change PR.

## What was done instead

Offline `mav0/gps0/data.csv` in the EuRoC exporter.

## When it becomes possible

When a follow-up plans a survey proto Migration · changes with
preservation tests for existing frame streams.
