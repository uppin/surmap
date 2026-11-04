# 2026-11-04 — Mirror fleet routes and drone markers onto the chat map

**Category:** Future enhancement
**Source:** #drone-fleet (n4, PR #120: the survey agent's fleet tools, Wrap row `[wf 4]`)
**Packages:** src/surmap
**Consent:** PRD `fleet-tools` out of scope ("Mirroring routes and drone positions onto the chat map (a follow-up TODO)")
**Priority:** 4
**Status:** Open
**Plan:** ⚠️ recorded debt, no PR planned

## What is left

The fleet tools fly simulated drones in ENU metres on the simulated block, but the chat map
(`MapTools`, `MapSceneStore`) shows none of it: a person watching the conversation cannot see
where a launched drone is, nor the route it is flying.

Mirror it, display only:

1. Convert fleet ENU positions and route waypoints to WGS84 with `enu_to_wgs84` (the scene's
   origin) and publish them into the scenario's `MapSceneStore` scene: one marker per drone
   (id, phase) and one route line per airborne drone's remaining route.
2. Refresh from `list_drones` telemetry (the controller's last report, while a page is linked);
   clear the mirror when the link drops or the drone docks.
3. Keep it a display: map routes stay drawings, never flight plans — flying still goes through
   the fleet tools, and nothing here commands a drone.

## Why it is not done now

n4's boundary is the agent's fleet surface (proto, handlers, skill). The chat-map mirror is a
separate display concern that needs its own scene-revision and polling decisions, and the PRD
kept it out of scope.

## When it becomes possible

Any time after PR #120 merges: the fleet handlers, `MapSceneStore` and `enu_to_wgs84` all exist.
