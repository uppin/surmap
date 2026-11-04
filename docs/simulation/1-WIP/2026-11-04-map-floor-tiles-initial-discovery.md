# Discovery: tile stitching

The station map already names OpenStreetMap raster tiles (`surmap.agent.tools.map_layers`, `https://tile.openstreetmap.org/{z}/{x}/{y}.png`, "© OpenStreetMap contributors"). No slippy-tile math, stitching, or tile fetching exists in Python. Pillow is a runtime dependency. ENU conversion lives in `surmap.map.snapshot` (111 320 m/degree, cos(lat) for longitude). Hexagon precedent: `surmap.slam` port + native + in-memory adapters.
