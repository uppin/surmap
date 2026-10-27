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

The deployed processes serve their **in-memory adapters** today: the
CM5 server uses `InMemorySlamBackend` + `InMemoryObjectPointSource`
(no RTAB-Map points, no Coral objects) and the station uses
`InMemorySamDetector` (no detections). The entrypoints and deployment
prove the wire, the service lifecycle, and the restart path; swapping
in the hardware adapters is a code change behind the existing ports,
not a deployment change.
