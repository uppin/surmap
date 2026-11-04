# Map floor in the scenario manifest (#127, #map-floor 1/5)

A scenario manifest may carry `map_floor {sw, ne, texture, zoom, attribution?,
replaced_ground?}`: a GPS bounding box (SW + NE WGS84 corners, at most 1 000 m a
side, the same cap in the station validator and the Rust renderer, proven on the
shared golden fixture `tests/fixtures/sim_scenario/map-floor.json`).

Setting a floor replaces the preset ground: box elements flagged `ground`
(legacy ids `ground`, `block-ground`, `apron` as fallback) are removed and
recorded in `replaced_ground`; clearing the floor restores exactly those boxes.
The ENU origin is the bbox centre (111 320 m per degree of latitude, longitude
scaled by cos(latitude), as the semantic snapshot).

For the file-length gate, manifest validation moved to
`surmap.simulation.manifest_validation` and the floor edits to
`surmap.simulation.floor_edits`; in Rust, `MapFloor` and `ModelInstance` moved to
`scene_manifest/map_floor.rs` and `scene_manifest/instances.rs`. Behaviour
unchanged; Python manifest suites and the Rust suite green.
