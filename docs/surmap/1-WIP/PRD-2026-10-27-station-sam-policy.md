# Station SAM analysis policy — PRD

**Date**: 2026-10-27
**PRD Type**: Enhancement

## Affected Features

- **Primary Feature**: GPU API (docs/architecture.md §10) — how the
  station treats incoming frames under SAM load.

## Summary

Define the SAM detector port and the frame-admission policy the station
server enforces: analyze every frame (accept lag) or analyze only when
the detector is free (accept drops, counted).

## Proposed Changes

### What's Changing

- `SamDetector` protocol: one raw frame in, a tuple of `SamDetection`
  (label, score, box, mask polygon, optional track id) out.
- `AnalysisGate`: async admission for one-at-a-time analysis —
  `EVERY_FRAME` waits for the detector; `BEST_EFFORT_DROP` returns
  immediately when busy and records a dropped frame.
- `InMemorySamDetector` fake returning configured detections, for tests
  and simulation.

### What's Staying the Same

- SAM 3.1 itself is not integrated here; it arrives later behind the port.

## Acceptance Criteria

- [ ] Under `EVERY_FRAME`, concurrent frames are analyzed serially, none dropped.
- [ ] Under `BEST_EFFORT_DROP`, a frame arriving while busy is skipped and counted.
- [ ] The fake detector returns its configured detections per frame.
