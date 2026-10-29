#!/usr/bin/env bash
# Start PX4 SITL and Gazebo Harmonic in the SurMap disaster-response world.
# SurMap stays passive: this script only symlinks resources and launches
# the simulator. It does not arm the vehicle or upload a mission.
# The Gazebo GUI is left on so WSLg can show it.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PX4_ROOT="${PX4_AUTOPILOT_ROOT:-${HOME}/PX4-Autopilot}"
MODELS="${PX4_ROOT}/Tools/simulation/gz/models"
WORLDS="${PX4_ROOT}/Tools/simulation/gz/worlds"

if [[ ! -d "${PX4_ROOT}" ]]; then
  echo "PX4-Autopilot not found at ${PX4_ROOT}." >&2
  echo "Set PX4_AUTOPILOT_ROOT to the checkout that already builds px4_sitl_default." >&2
  exit 1
fi

export GZ_SIM_RESOURCE_PATH="${GZ_SIM_RESOURCE_PATH:-}:${ROOT}/docs/simulation/gz:${ROOT}/docs/simulation/gz/worlds:${HOME}/src/PX4-gazebo-models/models"

ln -sfn "${ROOT}/docs/simulation/gz/x500_surmap_stereo" "${MODELS}/x500_surmap_stereo"
ln -sfn "${ROOT}/docs/simulation/gz/worlds/disaster_block.sdf" "${WORLDS}/disaster_block.sdf"
ln -sfn "${ROOT}/docs/simulation/gz/worlds/disaster_block_materials" \
  "${WORLDS}/disaster_block_materials"

cd "${PX4_ROOT}"
exec env \
  PX4_GZ_WORLD=disaster_block \
  PX4_SIM_MODEL=x500_surmap_stereo \
  make px4_sitl gz_x500
