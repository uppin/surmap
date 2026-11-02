# Mac Docker SITL for the disaster Gazebo flight

**Date:** 2026-11-02
**Feature:** Simulation

Brought the Gazebo + PX4 disaster flight to Apple Silicon Macs: a
Docker container (`deploy/mac-sitl/`, launched by
`scripts/launch_mac_sitl.sh`) runs Gazebo Harmonic, PX4's
`x500_surmap_stereo` airframe in `disaster_block`, and ROS 2 Jazzy
capture, with the Gazebo GUI over VNC. The disaster world SDF now
declares the sensor and broadcaster systems PX4 polls, and the
capture dump reads GPS accuracy from the covariance diagonal.
Verified end to end on this Mac: takeoff, landing, 17–28 stereo
pairs per flight captured under `~/sitl-runs/disaster-mac/`, EuRoC
export feeding the mission demo. SurMap stayed passive throughout —
flight commands were typed at PX4's own console.
