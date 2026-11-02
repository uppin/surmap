#!/usr/bin/env bash
# One-command Gazebo disaster flight on an Apple Silicon Mac.
# Builds and starts the Docker SITL container (Gazebo GUI over VNC on
# 127.0.0.1:5901), where PX4 waits at its pxh> console in tmux.
# SurMap stays passive: this script sends no flight command.
# Requires the docker CLI on PATH (Rancher Desktop or Docker Desktop).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
exec uv run python -m surmap.simulation.mac_sitl "$@"
