# 2026-10-27 — Adopt detector track IDs in the moving-areas stream

**Category:** Deferred scope
**Source:** `docs/surmap/1-WIP/2026-10-27-moving-classification.md` (PR #22, stack `#moving-objects` node 4/6)
**Packages:** surmap
**Consent:** Recorded in the n4 changeset at green; the developer's effort direction ("we should put the effort on KITTI stereo e2e", 2026-10-27) prioritised the stereo chain over this wiring.
**Status:** Open

## What is left

Wire detector identity into `stream_moving_areas`
(`src/surmap/survey/cm5_server.py`): when a graduated area
overlaps a Coral detector track (IoU ≥ 0.4 against the
`StreamDetections` track for the same frame_id), pass that
track's ID to `object_track_id` so the snapshot carries
designation `100 + track_id` with
`IDENTITY_SOURCE_DETECTOR` instead of an area-allocated ID.

## Why it could not be done now

`object_track_id` and the disjoint designation space
(`AREA_TRACK_ID_BASE = 1_000_000`) are implemented and
unit-tested, but the handler currently passes `None` for the
detector track: correlating the detections stream with the
moving-areas stream inside one handler needs the detector's
per-frame track table, which the CM5 server does not yet keep.

## What was done instead

Snapshots carry area-allocated identities
(`IDENTITY_SOURCE_AREA_ALLOCATED`), which the wire contract
reserves exactly for this case; consumers can distinguish the
two sources. The KITTI E2E (PR #23) exercises the
area-allocated path end to end.

## When it becomes possible

Any time — no external blocker. It is a handler-level change in
the CM5 server plus a stream-level test. Wanted before
on-board enablement so station-side fusion sees stable object
identities.
