# Discovery: Mac Docker SITL

Date: 2026-11-01. Host: Mac LT-R1VXTH2V6H, macOS 26.6.2, arm64 (Apple Silicon), 32 GB RAM, 24 Gi free on data volume (98% full).

## Observed

- `gz` not found; `~/PX4-Autopilot`, `~/src/PX4-gazebo-models`, `/opt/ros/jazzy` all missing. WSL runbook (`docs/simulation/px4-sitl.md`) cannot run here as-is.
- Repo assets present: `docs/simulation/gz/worlds/disaster_block.sdf`, `x500_surmap_stereo`, `surmap_stereo_cam/model.sdf`, `scripts/launch_disaster_sitl.sh` (WSL-only), `scripts/ros2/dump_sitl_capture.py` (needs Jazzy `rclpy`).
- Docker present via Rancher Desktop: `linux/arm64` (aarch64), so an Ubuntu 24.04 ARM64 container runs natively (no x86 emulation).
- Homebrew present. ROS 2 Jazzy has no supported macOS build, so native Homebrew was rejected by the user in favour of Docker.
- User decisions (2026-11-01): Docker container; Gazebo GUI via VNC; done = full flight + capture + `mission_demo --live` scoring.
- Live scoring additionally needs `SURMAP_LIVE_META=1` + `MODEL_API_KEY` (Meta SAM/Muse) — no key is present in this session. RTAB-Map live backend needs Docker (`StreamingRtabmapBackend`, pinned `linux/amd64` — on this arm64 host that image runs emulated or must be rebuilt; to be verified during Green).
- Disk is the binding constraint: PX4 source+build (~15 GB) plus Gazebo/ROS images may exceed the 24 Gi free. Builds must live in a Docker volume/image with size checks, and the run must halt rather than fill the disk.

## Contract reused, not reinvented

Capture dir (`calibration.json`, `frames.jsonl`, `gps.csv`, `images/`) from `docs/simulation/px4-sitl.md`; dump via `scripts/ros2/dump_sitl_capture.py`; score via `scripts/mission_demo.py --live --capture <dir>`. SurMap stays passive: takeoff is a PX4 console command typed by the operator (or PX4's own console in the container), never a SurMap publisher.
