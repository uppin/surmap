# Trackpad PTZ for the simulation chase view

**Date:** 2026-11-04
**Feature:** Bevy simulation ([bevy-simulation.md](../bevy-simulation.md)) · PR #136

The simulation's chase view now takes trackpad PTZ input: two-finger scroll pans
and tilts the camera around the drone, pinch zooms it between 3 m and 40 m. The
orbit lives in a pure `view_orbit` module fed by Bevy `MouseWheel` and
`PinchGesture` messages; the drone stays centred and keyboard flight is unchanged.
With no gesture input the view is exactly the chase view it replaces, so
unattended screenshot and record modes render as before.

Verified by seven unit tests on the orbit math (367 crate tests pass) and live in
the browser, where pan, tilt and pinch gestures each reframed the house-and-tree
scene. On current `main` the orbit follows the fleet's viewed drone.
