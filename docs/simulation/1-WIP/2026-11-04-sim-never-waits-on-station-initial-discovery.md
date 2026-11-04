# Initial Discovery: The simulation never waits on a slow station, and renders only what is seen

**Changeset**: [2026-11-04-sim-never-waits-on-station.md](./2026-11-04-sim-never-waits-on-station.md)
**Date**: 2026-11-04
**Passes**: 1

## Combined Conclusions

A peer reported a major lag in the WASM simulation on a powerful Windows laptop while the drone
flies. The path in play is page → stereo bridge → RTAB-Map sidecar and back, plus the page's own
rendering.

- **Nothing in the page blocks a thread.** `WebSocket.send` buffers, `Readback` is async, and
  `StreamPacer` drops a due pair when `bufferedAmount` holds more than four pairs. But the
  preview's FPV **waits on the station**: it shows only a frame RTAB-Map has answered
  (`HeldFrames`, 12 frames ≈ 1.2 s at 10 Hz). A station slower than the camera rate builds a
  queue deeper than 12, every answer names a frame already evicted, and the FPV freezes.
- **The bridge stops reading while it processes.** `serve_bevy_bridge`'s handler awaits each
  message's `handle` before reading the next, so a slow session leaves pairs in the websockets
  queue (`max_queue` 16) and TCP buffers and processes them seconds late, in order, with no
  catch-up. The latency is the queue depth, not RTAB-Map's own.
- **The page renders what nobody sees.** Both eyes (`rig.rs`, `Camera { order: 1 }`) render
  every frame — HDR, MSAA ×4, their own four shadow cascades and grass cull — though the stream
  reads them back at the camera's `rate_hz`. In the preview's FPV the chase camera (TAA, bloom)
  still renders under the opaque FPV layer. On a 144 Hz display that is ~3 full-scene renders
  per frame, most of it invisible; it grows once airborne, when the down-pitched eyes take in
  the whole block.
- **The dev page is barely optimised.** Since #142 `scripts/dev.sh` builds trunk's dev profile;
  `Cargo.toml` has `[profile.dev] opt-level = 1` and no override for dependencies, so Bevy,
  Rapier, Hanabi and Feronia run at opt-level 1.
- **Keypoint dots are UI nodes.** `show_fpv_frame` despawns and spawns one `Node` per keypoint on
  every answer (hundreds, ~10 Hz), each forcing a UI layout.
- `StreamingRtabmapBackend._frames` keeps every pair's PNG bytes for the whole session (only
  `frame_id`/`t_ns` are read, at `flush`) — memory grows with the flight.
- Out of scope, recorded for later: each eye goes gray8 → PNG →
  gray8 between `perception._png` and `streaming._to_gray8`; `/sim/map` re-renders the whole map
  each second.
- Conflict: the unmerged `drone-preview-classificat-*` branch draws detection boxes into the held
  frame, which this change retires.

## Exploration 1: what waits on the station, what renders unseen — 2026-11-04

**Agent**: parent Grep/Read
**Scope**: `examples/bevy-sitl-poc/src`, `src/surmap/simulation`, `src/surmap/slam/streaming.py`,
`scripts/dev.sh`

### Sequence

1. Read `main.rs`, `fleet/bridge_wasm.rs`, `fleet/stream.rs` — the stream's per-frame work.
2. Grep `Camera {` / `is_active` — every camera and when it renders.
3. Read `rig.rs`, `look.rs`, `shots.rs`, `close_shots.rs` — the eyes' render stack.
4. Read `preview.rs` — the FPV and its held frames.
5. Read `bevy_bridge.py`, `fleet/perception.py`, `slam/streaming.py`, `slam/stream_outbox.py` —
   what the station does per pair and where it queues.
6. Read `bevy_render-0.18.1/src/gpu_readback.rs` — when a readback copies its texture.
7. Read `scripts/dev.sh`, `Cargo.toml` — how the dev page is built.

### Grep / glob

| Tool | Pattern / glob | Path scope | Notable hits |
|------|----------------|------------|--------------|
| Grep | `Camera {` | `examples/bevy-sitl-poc/src` | `rig.rs:79` (eyes), `main.rs:321` (chase), `shots.rs`, `close_shots.rs` (screenshot only) |
| Grep | `trunk` | `scripts/dev.sh` | `:152` `trunk build index.html --public-url /sim/` (no `--release`) |
| Grep | `_frames` | `src/surmap/slam/streaming.py` | `:355` appended per pair, `:577` read at flush |

### Inspected files

#### `src/surmap/simulation/bevy_bridge.py`

**Why**: whether the bridge keeps reading while a session works.
**Excerpt**:

```python
async for message in socket:
    if isinstance(message, bytes):
        status = await asyncio.to_thread(handle, message)
        await socket.send(encode_status(status))
```

#### `examples/bevy-sitl-poc/src/preview.rs`

**Why**: what the FPV shows.
**Excerpt**:

```rust
/// How many sent frames wait for their odometry; RTAB-Map answering later drops the frame.
pub const HELD_FRAMES: usize = 12;
```

#### `bevy_render-0.18.1/src/gpu_readback.rs`

**Why**: whether an eye switched on for one frame is read back with that frame's render.
**Excerpt**:

```rust
prepare_buffers.in_set(RenderSystems::PrepareResources),
submit_readback_commands.after(render_system).in_set(RenderSystems::Render),
```

### Findings

The bridge's reader is serialised behind processing; the FPV is gated on the station's answers;
the eyes and the hidden chase view render every frame; the dev build is opt-level 1 throughout.
A readback is submitted after the same frame's render, so an eye activated in the frame its pair
is requested renders before it is copied.
