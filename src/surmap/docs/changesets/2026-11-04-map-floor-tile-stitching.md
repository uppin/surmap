# Stitching OSM tiles into a simulation floor (#128, #map-floor 2/5)

`surmap.simulation.map_floor` turns a GPS bbox into a floor texture through a
`TileSource` port: an OpenStreetMap adapter (the URL template lives here and the
station map's OSM layer imports it), an in-memory test adapter, and pure
slippy-tile stitching cropped to the bbox (geodesy inverting the semantic
snapshot's ENU rule). `choose_zoom` picks the sharpest zoom inside zoom ≤ 18,
≤ 64 tiles and ≤ 4 096 px a side; the PNG is named by its content hash so
scenarios share textures. Tiles are disk-cached atomically (temp file +
rename), non-PNG answers are refused and never cached, and entries expire
after 7 days. `SURMAP_TILE_URL_TEMPLATE` / `SURMAP_TILE_CACHE_DIR` repoint the
server or cache for offline use.
