# Rendering the map floor in the Bevy simulation (#130, #map-floor 4/5)

The renderer draws the floor as one untiled plane at the ENU origin, sized
from the bbox, textured with the stitched PNG (which receives the mip chain
every asset-server image gets). Because the preset ground is gone, the floor
carries a fixed collider — a separate, unrotated entity, a slab whose top is
at 0 m; on the rotated plane entity it would stand on edge as a wall. A
hand-edited manifest that still carries a flagged ground box has it hidden.
"© OpenStreetMap contributors" (or the floor's recorded attribution) shows
in the scene's corner. Verified by cargo tests (collider world bounds,
ground hiding, golden fixture) and a native screenshot of a real OSM floor
over Vilnius with a building and a survivor standing on it. The floor code
lives in `world/floor.rs`, split out of `world.rs` for the file-length gate.
