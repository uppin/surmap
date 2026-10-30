# CM5 stereo reconstruction

**Date:** 2026-10-27
**Feature:** Survey data APIs

Gave the CM5 real scene points: streamed stereo frames are decoded,
aligned, block-matched, and back-projected into the map frame, then
streamed as before under designation 1 (the static-scene map-layer id). Proven offline by an
end-to-end test over ten real ETH3D stereo pairs asserting detections
are present on every frame; pose and object tracking stay behind
their ports until RTAB-Map and Coral adapters land.
