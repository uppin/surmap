# CM5 survey server — PRD

**Date**: 2026-10-27
**PRD Type**: Enhancement

## Affected Features

- **Primary Feature**: Board API (docs/architecture.md §10) — the live
  survey stream a base station or simulator consumes from the CM5.

## Summary

Expose the CM5 as a ConnectRPC BIDI server: raw stereo frames and
calibration in; incremental designated point batches (RTAB-Map scene +
per-object tracking points) and, on request, the chosen video channels
out — points streamed as they are spawned, never resent at a position
already sent.

## Proposed Changes

### What's Changing

- `Cm5SurveyService.StreamSurvey` handler: config-first (calibration +
  requested video channels), then per-channel frames; completed stereo
  pairs drive `SlamBackend` and the object-point source; outputs pass
  through the n2 emitter under designation 1 (scene) and per-object
  designations.
- `ObjectPointSource` port + in-memory adapter (hexagon shape of
  `SlamBackend`): per pair, the tracked objects' map-frame points.
- A `surmap.rpc` brick + `ServerDescription` factory so hosts mount the
  service like any other.

### What's Staying the Same

- No flight commands, ever (§1). RTAB-Map output is never fed back as
  control. Everything runs with the base station absent (§3.3) — the
  server is an output, not a dependency of capture/mapping.

## Acceptance Criteria

- [ ] A pair's scene points stream once; the next frame at the same positions adds nothing.
- [ ] Object points stream under their per-object designation, scene points under 1.
- [ ] Requested video channels are echoed under designations 2/3; unrequested channels are not.
- [ ] A frame whose pair never completes produces no points.
