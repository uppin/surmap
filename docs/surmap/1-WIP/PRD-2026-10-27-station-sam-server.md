# Station SAM server — PRD

**Date**: 2026-10-27
**PRD Type**: Enhancement

## Affected Features

- **Primary Feature**: GPU API (docs/architecture.md §10) — the live
  segmentation feed the fusion stage will consume on the station.

## Summary

Expose the station as a ConnectRPC BIDI server with the same raw-frame
input as the CM5: frames in, SAM detection vectors out, each keyed by
the frame's assigned `frame_id`. The requester picks per stream whether
every frame is analyzed (lag accepted) or frames drop under load.

## Proposed Changes

### What's Changing

- `StationSamService.StreamAnalysis` handler: config-first (calibration,
  `AnalysisMode`, optional concept prompts), then frames; each admitted
  frame is analyzed once through n3's gate + `SamDetector` port and
  answered with `SamFrameDetections{frame_id, detections[]}` where each
  detection carries label, score, box, mask polygon, and track id.
- Under `BEST_EFFORT_DROP`, a frame arriving while an analysis is in
  flight gets no response; requesters reconcile by `frame_id`.
- A `surmap.rpc` brick + `ServerDescription` factory for hosts.

### What's Staying the Same

- The station issues no commands to the drone (README, §2.2); this is a
  data-in/detections-out service only. SAM 3.1 itself lands later behind
  the port.

## Acceptance Criteria

- [ ] Every analyzed frame is answered with its own `frame_id` and detection vector.
- [ ] `EVERY_FRAME`: a burst of frames is answered for all, in order.
- [ ] `BEST_EFFORT_DROP`: a frame arriving mid-analysis is unanswered; the next free frame is answered.
- [ ] A stream whose first message is a frame (no config) is rejected.
