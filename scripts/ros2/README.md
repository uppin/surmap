# ROS 2 helpers (operator machine only)

These scripts require a sourced ROS 2 Jazzy install (`/opt/ros/jazzy`).
They are **not** part of the SurMap `uv` environment or CI.

- `dump_sitl_capture.py` — subscribe to stereo Image (+ optional
  CameraInfo / NavSatFix) and write a SurMap capture directory.
  Passive only; never publishes flight commands.

See [`docs/simulation/px4-sitl.md`](../../docs/simulation/px4-sitl.md).
