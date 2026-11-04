# The survey agent runs SAM on an on-demand GPU station — PRD

**Date**: 2026-11-04
**PRD Type**: Enhancement

## Affected Features

- **Primary Feature**: [Survey agent](../../agent.md) — new station tools; real SAM through the station
- **Related Feature 1**: [Chat UI](../../agent.md#chat-ui) — SAM station indicator with Start / Stop
- **Related Feature 2**: [Survey servers on Modal](../../modal.md) — the station as a deployed, scale-to-zero app

## Summary

The agent gets a SAM station that costs nothing until it is used: a GPU container comes up on
the first SAM call (or an explicit start), goes down after 5 minutes without use (or an explicit
stop), and its state is visible to the model through tools and to the user in the chat header.

## Background

The agent process runs only the fake SAM (`--sam-fake`). The station (SAM 3.1 on a Modal GPU)
works end to end (verified 2026-11-04), but nothing in the agent can reach it, see whether it is
running, or bring it up and down — and a GPU left up bills by the second.

## Requirements

### R1 — One station interface, two implementations

- R1.1 A `StationControl` interface: `status()`, `start()`, `stop()`, and `detector()` — the
  `VideoSamDetector` the agent's SAM runs on.
- R1.2 `ModalStationControl` — the deployed `surmap-station` app through the `modal` SDK.
- R1.3 `StubStationControl` — in process, deterministic; the same state machine; its detector is
  the fake SAM. Tests, the UI's e2e server and `--station stub` use it.
- R1.4 Tools, the agent's SAM and the UI depend on the interface only.

### R2 — States

`OFF` · `QUEUED` (waiting for a GPU) · `STARTING` · `READY` · `STOPPING` · `ERROR`, plus a one-line
detail, the live container count and the idle timeout. Reading the state never starts or keeps
up a GPU.

### R3 — Lifecycle

- R3.1 First use: the first SAM frame the agent tracks starts the station and waits for it.
- R3.2 `start` brings it up without a frame; `stop` takes it down now.
- R3.3 Idle: 5 minutes (configurable) after the agent's last SAM frame the agent stops it.
- R3.4 A second `start` while starting or ready is a no-op; `stop` while off is a no-op.

### R4 — Agent tools

`get_station_status` (SYNC · 10 s · FAIL), `start_station` (SYNC · 30 s · DETACH — a cold start
outlives the sync window and becomes a job), `stop_station` (SYNC · 30 s · DETACH). They are
mounted only with a configured station, like the simulation tools: without one the model has no
station tools and the UI hides the indicator.

### R5 — Process

`python -m surmap.agent --station modal|stub` (`--station-app`, `--station-idle-s`); with a station,
`--sam-fake` is not required. The `modal` SDK is an optional extra (`uv sync --extra modal`), not a
base dependency.

### R6 — UI

The header shows `SAM` with the state (off / queued / starting / ready / stopping / error) and a
Start or Stop button; it polls the status; it is hidden when the server has no station.

## Out of scope

Stopping containers other clients hold open (the station closes nothing on its own; recorded as a
TODO); the `surmap-sam` app; choosing the workspace from the UI.
