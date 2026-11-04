# The map floor, end to end (#131, #map-floor 5/5)

The scene-building subagent's skill (`building-a-simulation-scene`) now
teaches the map-floor flow: base the scene on a GPS bbox first, place objects
by GPS through `geo_to_enu`, heed the re-anchor and outside-floor warnings,
credit OpenStreetMap. The stack PRD's requirements are applied to the stable
docs (`docs/simulation/bevy-simulation.md` "The map as the floor",
`docs/agent.md` tool table) and the history entry
`docs/simulation/changelog/2026-11-04-sim-map-floor.md`. Proven by
`tests/test_sim_map_floor_e2e.py`: a scripted agent turn on a real socket
bases a scenario on a bbox, converts a GPS target through the tool, places a
building at the reported ENU, and the station serves the manifest and the
floor PNG with the OSM credit recorded.
