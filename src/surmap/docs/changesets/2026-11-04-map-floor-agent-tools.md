# The agent's map-floor tools (#129, #map-floor 3/5)

Four `SimulationTools` rpcs (proto in `simulation_tools.proto`, handlers in
`surmap.agent.tools.simulation_floor`): `SetMapFloor` stitches the bbox's
tiles, stores the texture in the library and anchors the scenario — resolving
the scenario before anything is written, so a bad id leaves no orphan — and
warns when re-anchoring (a changed bbox) keeps placed elements' ENU
positions or leaves one outside the floor; `ClearMapFloor` restores the
replaced ground; `GeoToEnu` / `EnuToGeo` convert between GPS and ENU metres
from the floor centre, so the agent never does cos(lat) maths itself. The
floor records its tile source's attribution, and the scenario credits
© OpenStreetMap contributors exactly when that is the attribution. Tiles are
cached beside the served library, never inside it.
