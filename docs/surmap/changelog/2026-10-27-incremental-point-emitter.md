# Incremental point emitter

**Date:** 2026-10-27
**Feature:** Survey data APIs

Added the CM5's spawn-only point emitter: per designation (a map-layer id) and per
stream, a point at a position that was already sent is never resent,
so the static scene is streamed once as it is spawned instead of in
full on every frame. Object layers are independent — the same
coordinates under another designation (another map-layer id) are a different point.
