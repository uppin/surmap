# 2026-11-04 — the station closes sockets other clients leave open

**Category:** Deferred scope
**Source:** `docs/surmap/1-WIP/2026-11-04-agent-station-lifecycle.md` (#113), PRD *Out of scope*
**Packages:** surmap
**Consent:** Planned out of scope in the PRD the developer approved for #113 (2026-11-04): "Stopping containers other clients hold open (the station closes nothing on its own; recorded as a TODO)"
**Status:** Open

## What is left

On Modal an open WebSocket is an active input, so a container serving one does not scale down.
The agent closes its own link on stop and on idle (`ModalStationControl`), but a client that
leaves its socket open (a verifier, a demo page) keeps the GPU up until it closes, up to the
function `timeout` (86400 s). The station should close a Connect WebSocket that has carried no
call for its idle timeout.

## Why it could not be done now

The socket is served by the generic `surmap.rpc` Hypercorn host (`station_main.py:76-88`), so an
idle close is an rpc-layer change for every survey server, not a station change; #113 is the
agent's side of the lifecycle.

## History

| Date | Event |
|---|---|
| 2026-11-04 | Recorded at the #113 wrap |
