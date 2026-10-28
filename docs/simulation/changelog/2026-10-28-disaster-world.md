# Disaster-response Gazebo world

**Date:** 2026-10-28
**Feature:** Machine 3 simulation

Added a fictional civilian earthquake-and-flood block for Gazebo
Harmonic (`disaster_block`), with scoring ground truth in map ENU and
WGS84, a 12 m lawnmower plan the operator loads in QGroundControl, and
`scripts/launch_disaster_sitl.sh`. The stereo airframe from the PX4
SITL bridge is unchanged. SurMap still does not send flight commands.
Runbook: `docs/simulation/disaster-world.md`.

The first pass still read as an intact town from 12 m. The block is now
pancaked slabs, two rubble mounds spilling into the streets, a wide
muddy flood over the avenue and a building footprint, loose debris,
smoke columns, and 1.75 m orange/yellow survivors on the street, on
the mounds, and on a remaining roof. Ground near the collapses is
dust, not grass. Scoring JSON and the 12 m lawnmower were updated
with the new people and hazards.
