# Survey viewer

**Date:** 2026-10-28
**Feature:** Survey viewer

Added a local browser view of one replay clock: camera overlays,
a height-coloured map with trajectory and landmark mask clouds,
moving-track trails, a two-series time cursor, and the landmark list.
`POST /ask` cites tracks from a `surmap.semantic_map_snapshot.v1`
file, delegating to `surmap.mapqa` when `SURMAP_LIVE_META=1` and that
package imports. EuRoC uses the existing dataset cache; a SITL capture
directory and a preview fixture run without that download. The viewer
binds `127.0.0.1` unless `--host` says otherwise.
