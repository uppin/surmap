# Initial Discovery: #drone-fleet review fixes

**Changeset**: [2026-11-04-fleet-review-fixes.md](./2026-11-04-fleet-review-fixes.md)
**Date**: 2026-11-04
**Passes**: 2

## Combined Conclusions

The `#drone-fleet` stack (#116, #117, #119, #120, #121) is on `main` at `53858eb`. A high-effort
code review ran over `bd30dc1..53858eb` (11.3k lines, 101 files). The orchestrator re-read the
cited code for each finding, and all 10 were confirmed.

- **8 behaviour defects** (this changeset): F1–F8 below.
- **2 behaviour-preserving cleanups** (a separate Refactor PR, not here):
  - `state_at` / `phase_when` replay from t=0 on every frame and push, which is quadratic.
  - `perception.py` duplicates `bevy_bridge`'s frame-to-backend path, double-encoding PNGs.

  The three oversized-file code issues the stack left for its sweep node join them; the sweep never
  ran because the stack was merged before it.
- **Stage reports add 2 more defects:**
  - F9: `tests/hang_dump.py` crashes on a dead `weakref.proxy`. A patch with a reproduction test
    was prepared during n5's red step.
  - F10: `ListDronesResponse` lost the planned `sim_t_s` (n4's red step dropped it because n3's
    controller did not expose it). No TODO was filed. The controller does receive
    `Telemetry(sim_t_s)`.

## Exploration 1: code review — 2026-11-04

**Agent**: `/code-review high bd30dc1..53858eb` (forked subagent)
**Scope**: every file the stack changed

### Findings (as returned)

| # | File:line | Finding |
|---|---|---|
| F1 | `src/surmap/agent/server/app.py:283` | the bridge segments with the test fake `InMemorySamDetector()`: zero detections, every frame appended to an unbounded `frames` list, one instance shared by every drone's worker |
| F2 | `examples/bevy-sitl-poc/src/fleet/bridge_wasm.rs:235` | `drone_id` is read from `ActiveDrone` when the readback completes, while pose and `t_ns` were captured at the request, so a switch in between mislabels the pair |
| F3 | `src/surmap/simulation/bevy_bridge.py:144` | `session.handle()` / `close()` run synchronously on the event loop the agent server shares (PNG encodes, backend spawn, thread joins, `docker rm`), stalling chat, RPCs and the fleet ack timer |
| F4 | `src/surmap/simulation/fleet/controller.py:362` | the expected phase is dropped at `sim_t_s >= at_s`, but the page applies a command at `due_step(at_s)`, so same-frame telemetry still shows the old phase and the station reverts to it |
| F5 | `src/surmap/simulation/fleet/perception.py:273` | an exception from one drone's backend escapes `handle`, ends the socket handler and closes every drone's session |
| F6 | `src/surmap/simulation/fleet/controller.py:434` | `FleetRegistry.link` attaches without checking that `hello.scenario` equals `?scenario=` |
| F7 | `examples/bevy-sitl-poc/src/fleet/bridge_wasm.rs:47` | `stream_bridge` is unordered against `fleet::fly_fleet` / `follow_drone_rig`, so the pose can be a frame older than `t_ns` |
| F8 | `src/surmap/simulation/fleet/controller.py:412` | a controller caches the manifest's nests at first use; nests added later are unknown, and stale telemetry answers instead of UNAVAILABLE |
| R1 | `examples/bevy-sitl-poc/src/fleet.rs:144` | quadratic replay in `viewed_pose` / `FleetLog::push` (Refactor PR) |
| R2 | `src/surmap/simulation/fleet/perception.py:199` | duplicated frame path with drifted counting; double PNG (Refactor PR) |

## Exploration 2: verification of each finding — 2026-11-04

**Agent**: parent Grep/Read on `origin/main` `53858eb`

### Sequence

1. Read `app.py` 270–295 (`start_bevy_bridge`), `survey/sam.py` 122–136 (`InMemorySamDetector`) — F1
2. Read `bevy_bridge.py` 135–150 (`serve_bevy_bridge` handler); grep `start_bevy_bridge` in `app.py`, `agent/__main__.py` — F3
3. Read `bridge_wasm.rs` 40–52 (plugin) and 200–245 (`stream_bridge`) — F2, F7
4. Read `controller.py` 350–372 (telemetry/expected), 405–445 (`controller`, `link`) — F4, F6, F8
5. Grep `fn due_step|fn steps_until` in `fleet/*.rs`; grep `send_telemetry|fly_fleet` ordering in `link_wasm.rs`, `main.rs` — F4, F7
6. Read `perception.py` 262–280 — F5
7. Read `app.py` 356–392 (`build_demo_workspace` SAM choice), grep `class SamDetector`, `class CentredBox…` — F1's fix shape
8. Read the scratchpad patch `hang-dump-weakproxy.patch`; grep `sim_t_s` in `fleet_tools.proto`, `controller.py` — F9, F10

### Inspected files (excerpts)

#### `src/surmap/agent/server/app.py` (F1)

```python
async def start_bevy_bridge(config, simulation) -> Closeable:
    ...
    detector = InMemorySamDetector()      # one test fake for every drone, never the configured SAM
```

The agent's own SAM choice (`build_demo_workspace`) is the station's detector when there is one,
else `CentredBoxVideoSamDetector` under `--sam-fake`, else it refuses to start.

#### `src/surmap/survey/sam.py:122-134`

```python
class InMemorySamDetector:
    """`SamDetector` adapter for tests and simulation: configured output."""
    def __init__(self, detections=()) -> None:
        self._detections = detections
        self.frames: list[RawFrame] = []
    async def detect(self, frame):
        self.frames.append(frame)          # unbounded
        return self._detections
```

#### `src/surmap/simulation/bevy_bridge.py:139-148` (F3)

```python
async def handler(socket):
    session = session_factory()
    try:
        async for message in socket:
            if isinstance(message, bytes):
                await socket.send(encode_status(session.handle(message)))   # sync, on the loop
    finally:
        session.close()                                                      # sync, on the loop
```

`agent/__main__.py:185` starts it inside the agent server's process and loop.

#### `examples/bevy-sitl-poc/src/fleet/bridge_wasm.rs` (F2, F7)

```rust
app.add_systems(Update, stream_bridge);          // :47 — no .after(fly_fleet)/(follow_drone_rig)
...
let active_drone = active.as_ref().map(|a| (**a).clone()).unwrap_or_default();   // :235, at send
let header = pair_for(&active_drone, stream.frame_id, stream.pending_t_ns, …, stream.pending_pose);
```

By contrast, `main.rs:168-172` orders `follow_drone_rig`, `chase_camera` and `update_status`
`.after(fleet::fly_fleet)`, and `link_wasm.rs:37` orders `send_telemetry.after(fly_fleet)`.

#### `src/surmap/simulation/fleet/controller.py:357-362` (F4)

```python
case Telemetry(sim_t_s):
    self._telemetry = message
    self._expected = {d: (p, at_s) for d, (p, at_s) in self._expected.items() if at_s > sim_t_s}
```

`autopilot.rs:326-333`: `due_step(at_s) = ceil(at_s/STEP_S − slack)`,
`steps_until(t) = floor(t/STEP_S + slack)`. For `at_s = 1.02`, the command applies at step 21
(1.05 s), but telemetry stamped 1.02 (step 20) drops the expectation.

#### `src/surmap/simulation/fleet/controller.py:407-416, 425-436` (F6, F8)

```python
def controller(self, scenario_id):
    found = self._controllers.get(scenario_id)
    if found is None:
        manifest = self._store.scenario(scenario_id).manifest
        found = FleetController(scenario_id, nests_of(manifest), …)   # nests frozen here
        self._controllers[scenario_id] = found
    return found
...
hello = await self._hello_of(socket)
if controller.linked: …close(CLOSE_ALREADY_LINKED)
controller.attach(socket, hello)          # hello.scenario never compared to scenario_id
```

#### `src/surmap/simulation/fleet/perception.py:262-275` (F5)

`session.process(pair, …)` has no guard, so a backend exception propagates out of
`FleetPerception.handle` and out of the socket handler, whose `finally` closes every session.

#### F9 / F10

- F9 patch (`tests/hang_dump.py` `_is_event_loop` catching `ReferenceError`, and
  `tests/test_hang_dump.py::test_a_dead_weak_proxy_in_memory_does_not_cut_the_report_short`). The
  test fails without the fix.
- F10: `grep sim_t_s proto/surmap/agent/v1/fleet_tools.proto` finds nothing.
  `controller.py:357` keeps the latest `Telemetry`, which carries `sim_t_s`.
