# 2026-11-04 — #drone-fleet review fixes (PR #133)

Ten findings from the review of the `#drone-fleet` stack (#116–#121), each fixed against a
reproduction test that failed on `main`.

- F1: the stereo bridge segments with the agent's configured SAM (station, else `--sam-fake`),
  one video detector per drone; no frame is kept after segmenting (was a shared test fake that
  found nothing and kept every frame).
- F2: a streamed pair is labelled with the drone whose eyes were read back (`PendingPair`).
- F3: the bridge's `handle` / `close` run off the event loop, in order per connection.
- F4: an applied command's expected phase stands until telemetry reaches the renderer's due
  step (`due_step` mirrors `autopilot.rs`).
- F5: one drone's map failure marks only that drone errored; `drone_map_status` reports `error`.
- F6: a page whose `hello.scenario` differs from `?scenario=` is closed with 4400.
- F7: `stream_bridge` runs after `fleet::fly_fleet` and `follow_drone_rig`.
- F8: an unlinked controller reads the scenario's latest nests; a page's stale telemetry no
  longer drives refusals after it disconnects.
- F9: `tests/hang_dump.py` skips a dead weak proxy.
- F10: `list_drones` reports `sim_t_s`.
- Wrap: `FleetRegistry` moved to `surmap.simulation.fleet.registry` (500-line gate on
  `controller.py`).
- Decided without review: F8 keeps the pre-existing order where a never-linked controller
  answers a docked drone's recall `already_docked` before "no simulation connected".
