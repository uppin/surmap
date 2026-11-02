# Changeset: Gazebo disaster flight on Mac (Docker SITL)

**Date**: 2026-11-01
**Status**: 🚧 In Progress
**Type**: Infra
**Behaviour**: preserves
**Complexity**: 5 — several row-4 signals at once: external simulator build, container toolchain, GUI streaming, end-to-end live scoring with an API-key gate

## Workflow

- [wf 1] ✅ 2026-11-01 `/plan-ft-dev` Plan — changeset with V3 Verification and before-output · this file + discovery companion; before: gz missing, --live exits 2, MODEL_API_KEY unset
  - [x] Host preflight recorded (no gz / PX4 / ROS on macOS; Docker arm64 present)
  - [x] User decisions recorded: Docker, VNC GUI, full flight + live scoring
  - [x] Before-output captured for every Verification check
- [wf 2] ✅ 2026-11-01 `/plan-red` Red — failing tests for the Mac launcher contract · 7 tests red: `No module named 'surmap.simulation.mac_sitl'`
  - [x] Launcher rejects a non-arm64 / Docker-less host with a named error
  - [x] Launcher emits the container, VNC, and capture commands without starting PX4 itself
- [wf 3] ⛔ `/green` Green — implement until every red test passes · flight + capture proven in the final image; live scoring halts on the missing MODEL_API_KEY (options in Verification)
  - [x] Dockerfile (Ubuntu 24.04 ARM64: Gazebo Harmonic, ROS 2 Jazzy, PX4 SITL, VNC)
  - [x] Mac launcher script (`scripts/launch_mac_sitl.sh` → `surmap.simulation.mac_sitl`, 7 tests green)
  - [x] Container builds; Gazebo GUI reachable over VNC (`vnc://127.0.0.1:5901`, Xtigervnc session, `gz sim -g` running)
  - [x] PX4 takeoff in disaster_block; stereo topics bridged; capture dumped (`deploy/mac-sitl/capture.sh`: flight 1 wrote 17 pairs + 113 GPS airborne, flight 2 wrote 28 pairs + 51 GPS; EuRoC export 17 pairs / 113 GPS)
  - [ ] `mission_demo --live --capture` scores the capture (needs MODEL_API_KEY)
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded
  - [ ] `docs/simulation/px4-sitl.md` — Mac Docker path documented
  - [ ] Four gates green: ruff check, ruff format, mypy, pytest

## Initial Discovery

See [mac-docker-sitl-initial-discovery.md](mac-docker-sitl-initial-discovery.md).

## State A → State B

- A: Disaster flight runs only on a WSL2 host with gz/PX4/Jazzy preinstalled. This Mac has none of them; the one-command path stops at preflight.
- B: A repo-owned Docker setup builds and runs the same stack on Apple Silicon, exposes the Gazebo GUI over VNC, flies the disaster block, dumps a standard capture, and scores it with the existing live mission command. WSL behaviour unchanged.

## Verification (V3)

| Check | Before (2026-11-01, this host) | After (planned) |
|---|---|---|
| `gz sim --versions` | `gz: command not found` | prints Harmonic ≥ 8 inside the container |
| PX4 model list | n/a (no PX4) | `x500_surmap_stereo_0` spawned in `disaster_block` |
| Stereo topics | n/a | left/right image topics at ~20 Hz, 640×480 |
| Capture | n/a | `wrote N pairs (+ M GPS)` with N ≥ 1, standard capture layout |
| Live score | `mission_demo.py --no-viewer` fixture run only | `--live --capture` writes `impact.json` with `basis: "live"` |

Executed 2026-11-02 in the final image: `gz sim --versions` → Gazebo 8.15.0; PX4 spawned
`x500_surmap_stereo_0` in `disaster_block`, preflight OK after a GCS heartbeat, `commander
takeoff` → Takeoff detected at 2.5 m, capture wrote 17 pairs + 113 GPS (flight 2: 28 + 51),
`export_sitl_session.py` exported 17 pairs / 113 GPS. Live scoring run:
`SURMAP_LIVE_META=1 uv run python scripts/mission_demo.py --live --capture
~/sitl-runs/disaster-mac --no-viewer` → `MODEL_API_KEY is not set`, exit 2. ⛔ Needs the
developer's key: a) export `MODEL_API_KEY` and re-run that command, b) accept the
capture-only result and score later. Also fixed en route, each red-test-first: the world
SDF now declares the Gazebo systems PX4 polls (SceneBroadcaster, Sensors, Imu, NavSat,
AirPressure, Magnetometer, Physics, UserCommands), and the capture dumper no longer
tests a Jazzy covariance array for truth (`accuracy_from_covariance`).

## Decisions & Trade-offs

- Docker over native Homebrew: ROS 2 Jazzy is unsupported on macOS; the container keeps the WSL runbook's commands intact.
- VNC over XQuartz forwarding: one mechanism, works with Rancher Desktop without host X setup.
- Disk (24 Gi free) may halt Green: image/volume growth is checked before the PX4 build; filling the host disk is a stop, not a risk to take silently.
- Live scoring needs `MODEL_API_KEY`, which this session does not have; that sub-step halts for the key rather than faking a score.
