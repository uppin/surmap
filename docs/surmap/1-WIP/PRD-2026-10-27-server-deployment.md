# Server deployment — PRD

**Date**: 2026-10-27
**PRD Type**: Enhancement

## Affected Features

- **Primary Feature**: Board API + GPU API (docs/architecture.md §10) —
  the CM5 and station servers become runnable, installable services.

## Summary

Give both servers an executable entrypoint and an SSH deployment path:
`scripts/deploy-cm5.sh <source-dir> <ssh-target>` and
`scripts/deploy-station.sh <source-dir> <ssh-target>` sync the code,
install/refresh a systemd unit, restart the service, and prove it is
active before returning.

## Proposed Changes

### What's Changing

- `python -m surmap.survey.cm5_main` (port 8080 default) and
  `python -m surmap.survey.station_main` (port 8081 default), each
  mounting its service module plus health routes on `HypercornHost`.
- `deploy/systemd/surmap-cm5.service` and `surmap-station.service`:
  system user `surmap`, `Restart=on-failure`, install dir rendered at
  deploy time.
- Deploy scripts (shared logic in `scripts/deploy-lib.sh`): source path
  and SSH target are CLI arguments, optional remote dir / port / SSH
  port follow; restart is always the last step and `is-active` gates
  success.

### What's Staying the Same

- The services still run their in-memory adapters until hardware
  adapters land (RTAB-Map/Coral/SAM); deployment does not change that,
  and `docs/deployment.md` says so plainly.
- No hostname or credential is committed anywhere.

## Acceptance Criteria

- [ ] Both entrypoints build a description serving their service + health route.
- [ ] Both deploy scripts refuse to run without source dir + SSH target (usage, exit 2).
- [ ] A script's remote sequence installs the unit, daemon-reloads, restarts, and checks `is-active`.
- [ ] Each server has a real-socket e2e: a real server process boundary (`HypercornHost` on an ephemeral port) is started, exercised over the wire, and closed after the run — on success and on failure alike.
