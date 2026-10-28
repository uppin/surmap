# Disaster-response Gazebo world

**Date:** 2026-10-28
**Feature:** Machine 3 simulation

Added a fictional civilian earthquake-and-flood block for Gazebo
Harmonic (`disaster_block`), with scoring ground truth in map ENU and
WGS84, a 12 m lawnmower plan the operator loads in QGroundControl, and
`scripts/launch_disaster_sitl.sh`. The stereo airframe from the PX4
SITL bridge is unchanged. SurMap still does not send flight commands.
Runbook: `docs/simulation/disaster-world.md`.
