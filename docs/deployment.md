# Deploying the survey servers

The two survey servers are systemd services on their machines: the CM5
server on the drone's CM5, the SAM server on the base station.
Deployment is over SSH; the service is restarted after each deployment
and the deploy only succeeds once the service reports active.

## Commands

```bash
scripts/deploy-cm5.sh     <source-dir> <ssh-target> [remote-dir] [port] [ssh-port]
scripts/deploy-station.sh <source-dir> <ssh-target> [remote-dir] [port] [ssh-port]
```

- `<source-dir>` — local path to the SurMap checkout to deploy.
- `<ssh-target>` — SSH destination, e.g. `user@cm5.local`.
- `[remote-dir]` — install path on the target (default `/opt/surmap`).
- `[port]` — survey port (defaults: CM5 `8080`, station `8081`).
- `[ssh-port]` — SSH port (default `22`).

Example:

```bash
scripts/deploy-cm5.sh ~/Code/surmap mantas@cm5.local
scripts/deploy-station.sh ~/Code/surmap mantas@station.local /opt/surmap 8081
```

No hostname, user, or credential is stored in the repo; both are CLI
arguments so the same scripts serve bench, simulation, and flight
machines.

## CM5 configuration: RTAB-Map + CoralAI, everything else by config

A CM5 deploy enables only RTAB-Map and CoralAI. Every other
computation is off unless its deploy option (or the matching
`cm5_main` flag) enables it:

| Computation | Deploy option | `cm5_main` flag | Default |
|---|---|---|---|
| RTAB-Map (streaming) | `--slam streaming` | `--slam-backend streaming` | deploy: on |
| Coral detector | `--model <profile>` | `--detector coral` | deploy: on (`efficientdet-lite0`) |
| Object tracking / object points | `--object-tracking` | `--object-tracking` | off |
| Moving areas | `--moving-areas` | `--moving-areas` | off |
| Region points | `--region-points` | `--region-points` | off |

Further deploy options: `--no-model` (no detector), `--coral-cpu`,
`--slam sidecar|inmemory`, `--calibration-dir <remote-dir>`, and
`--rtabmap-native <remote-binary>`.

## Station: SAM 3.1 (PyTorch) on NVIDIA

A station deploy enables SAM 3.1 in PyTorch on the GPU:

```bash
scripts/deploy-station.sh ~/Code/surmap mantas@station.local \
    --sam31-model /home/mantas/.cache/huggingface/hub/models--facebook--sam3.1/snapshots/<hash>
```

`--detector sam31-torch` (the deploy default) runs Meta's SAM 3.1
image model via `station_main --detector sam31-torch`;
`--sam31-model` takes an HF id, a local `.pt`, or a local snapshot
directory (a local directory needs no HF download).
`--sam31-device` (default `cuda:0`) and `--sam31-label` (the concept
prompt) configure it. Before the restart, the deploy provisions the
optional torch + `sam3` stack into the station venv
(`scripts/provision_sam31.sh`) and fails if torch sees no CUDA
device; `--no-provision` skips that step. `--detector sam3` (ONNX)
and `--detector memory` remain available. Note the `surmap` service
user must be able to read the checkpoint: a snapshot under a
`700`/`750` home directory will not load — copy it somewhere
readable (e.g. `/opt/surmap/models/sam3.1`) and point
`--sam31-model` there.

## RTAB-Map natively on the CM5 (no Docker)

The streaming backend normally launches the pinned `linux/amd64`
Docker image, which runs under qemu emulation on the arm64 CM5.
For native speed, build RTAB-Map and the stream tool on the CM5
itself (system dependency, installed with apt + a pinned upstream
build into `/usr/local`):

```bash
# on the CM5 — binary lands in ~/.cache/surmap-rtabmap/stream-build/
scripts/build_rtabmap_native.sh
```

The deploy handles this for you: with the default streaming slam,
`deploy-cm5.sh` first ensures the stream binary in the target-side
build cache, `~/.cache/surmap-rtabmap/stream-build/` — the build
directory is the cache, the binary is never copied elsewhere, and
the build script exits at once when it already exists there. Only
then does the deploy sync and restart the service.
`--rtabmap-docker` opts back into the Docker image; `FORCE=1`
forces a rebuild. Run by hand with
`cm5_main --slam-backend streaming --rtabmap-native <binary>`.
A missing binary fails startup by name, with this build step named.

## What a deploy does

1. `rsync` the source to `<remote-dir>` (excluding `.git`, `.venv`,
   caches).
2. Install dependencies there: `uv sync --no-dev` when `uv` is present,
   otherwise a fresh venv + `pip install .`.
3. Create the `surmap` system user if needed and own the install dir.
4. Render `deploy/systemd/surmap-{cm5,station}.service` (install dir
   and port substituted) into `/etc/systemd/system/`.
5. `systemctl daemon-reload`, `enable`, then `restart` the service —
   the restart is always the last step — and poll `is-active` for up to
   10 seconds. A service that does not come up fails the deploy.

The target needs SSH access with passwordless `sudo`, plus `rsync` and
Python ≥ 3.11 (or `uv`) on the machine.

## Running by hand

```bash
python -m surmap.survey.cm5_main     --host 0.0.0.0 --port 8080
python -m surmap.survey.station_main --host 0.0.0.0 --port 8081
```

Both serve `/health/is_alive` next to their Connect service.

## Current limitation

The CM5 server's scene points are **real**: its stereo reconstructor
turns streamed pairs into points, and with the streaming backend the
RTAB-Map sidecar's cloud is the scene. Object points are real with
`--detector coral` plus `--object-tracking`: the Coral
detector+tracker lifts stereo points inside tracked boxes into the
object layer, with the rig taken from each stream's config. Object
tracking is off by default (see the configuration table above).
The station still serves `InMemorySamDetector` (no detections until a
SAM adapter lands). Swapping those adapters in is a code change
behind the existing ports, not a deployment change.

Verify a deployed station by feeding it the recorded demo stream.
Every analysis response names the execution that produced it
(`provider` + `device`), and the script reports it as a DEVICE
indicator — GPU or CPU — so a silent CPU fallback cannot pass as a
GPU deployment:

```bash
uv run python scripts/verify_station.py <station-address>:8081 --expect-device gpu
```

It checks health, one analysis response per fed frame (labelled,
in-bounds detections with mask polygons), and the accelerator
indication, and reports the analysis frame rate. The configured
concept (`--sam31-label`) decides what counts as a detection: a
concept SAM does not ground in the demo room (e.g. the generic
`object`) legitimately yields zero detections there, which
`--min-detection-frames 0` accepts while still verifying transport
and execution.

Verify a deployed CM5 by feeding it the recorded demo stream:

```bash
uv run python scripts/verify_cm5.py <cm5-address>:8080 [--rtabmap]
```

It checks health, the detections stream, and the survey point
stream, and reports the Coral detections rate, the survey rate, and
(with `--rtabmap`, needs Docker) the RTAB-Map streaming sidecar's
posed-frames rate, each in frames per second. RTAB-Map alone, with
no object tracking in the loop, is measured with
`scripts/verify_cm5.py --rtabmap-only [--frames N]`.

## Demo page on remote hosts

The demo page can run against the deployed servers instead of its
in-process pipelines:

```bash
./scripts/deploy-demo.sh /path/to/surmap mantas@10.88.77.10 /opt/surmap-demo 8770 22
```

This installs the `surmap-demo` systemd unit on the station host,
launched as
`scripts/demo.py --cm5-host 10.88.77.14:8080 --station-host 127.0.0.1:8081`
(the Radxa CM5 is the CM5 host for now; both hosts are deploy
options). At startup the demo asks each host for its capabilities
(the unary `GetCapabilities` RPC on both survey services) and
renders only what that host reports: a CM5 without a detector
contributes the RTAB-Map cloud pane with no Coral overlay and no
object layer, the station's SAM pane is labelled with its
provider/device (e.g. `GPU · SAM 3.1 (PyTorch) · cuda:0`), and a
host that does not answer contributes no panes at all. Played pairs
stream to the CM5 (`StreamSurvey`, over HTTP/2) and to the station
(`StreamAnalysis`); the survey stream also carries the backend's
per-frame odometry (pose + tracked keypoints, with its stereo
rectification) and its growing map snapshot, so the video keypoint
overlay, the 3D cloud and the floor plan all build live during
playback, and the final cloud lands when the run flushes. Each
demo stream carries its dataset's camera definitions
(`cam0_yaml`/`cam1_yaml` in the stream config), and the CM5 builds
a fresh RTAB-Map backend calibrated for that stream and closes it
with the stream — so every scene shows its own map in real time,
never a previous run's. Streams without camera definitions (the
verify scripts) keep the server's configured backend, with the
pre-existing map and odometry guarded from leaking in. The demo deploys into its own
remote directory (`/opt/surmap-demo`) so its venv sync cannot
disturb the station service's SAM stack in `/opt/surmap`.
