# PX4 SITL session bridge

**Date:** 2026-10-27
**Feature:** Machine 3 simulation

Added the offline Gazebo/PX4 SITL → EuRoC session bridge for WSL:
documented capture directory, `surmap.simulation` exporter, CLI,
Harmonic stereo SDF models, and ROS 2 dump script. Architecture now
records Gazebo Harmonic + PX4 SITL as the local Machine 3 path while
SurMap stays passive (no flight commands). Live ConnectRPC bridging
and GPS-on-wire remain deferred todos.
