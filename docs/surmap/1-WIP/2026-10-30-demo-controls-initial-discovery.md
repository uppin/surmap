# Initial Discovery: demo scene selection and playback control

**Changeset**: [2026-10-30-demo-controls.md](./2026-10-30-demo-controls.md)
**Date**: 2026-10-30
**Passes**: 1

## Combined Conclusions

- **One scene per server.** `make_demo_server(prepared, …)` stores a single
  `PreparedDataset`; `scripts/demo.py` prepares only `--dataset` (download
  if missing). The page is formatted per dataset (title, view size, depth
  ramp, credit), so switching scene means a new page.
- **One viewer, refused not replaced.** `_stream` takes `stream_lock`
  non-blocking and answers 409 "a demo stream is already running"; the
  page shows "Stream unavailable…" on any SSE error. A reload or a second
  tab races the old connection, which only notices it is gone on its next
  write.
- **No control surface.** Only `GET /`, `/health`, `/stream`; no POST
  handler. `DemoPlayer.events()` is a paced generator: frame → sidecar
  `process_frame` → `display.release()` → sleep to the frame interval;
  `finally` closes the worker and backend (removing the sidecar container).
- **Pausing must keep releasing.** `_Display` gives up on a held frame
  after `HOLD_MAX_S` (2 s); a pause that stops the loop would expire held
  frames, so the paused loop has to keep polling and releasing.
- **Seek/speed are not natural here.** The live SLAM map is incremental
  (no rewind); faster than native rate drops more pairs under emulation
  (KITTI already at 63/111 ms median/p95 against a 100 ms budget).

## Exploration 1: server surface and player loop — 2026-10-30

**Agent**: parent Grep/Read
**Scope**: what scene selection and playback control touch

### Sequence

1. Grep `class _DemoHttpServer`, `def _stream`, `def do_GET|do_POST` in `src/surmap/demo/server.py`.
2. Read `scripts/demo.py` 75–110 — launcher prepare + serve.
3. Read `src/surmap/demo/server.py` `events()` loop (prior pass, live-map-display).

### Inspected files

#### `src/surmap/demo/server.py`

```python
def _stream(self) -> None:
    if not self.server.stream_lock.acquire(blocking=False):
        self._send(409, "text/plain", b"a demo stream is already running")
        return
    ...
        player = DemoPlayer(self.server.prepared, **self.server.player_options)
```

#### `scripts/demo.py`

```python
prepared = ensure_dataset(DATASETS[args.dataset], args.cache_dir or default_cache_dir())
...
server = make_demo_server(prepared, host=args.host, port=args.port, fps=args.fps, ...)
```

### Findings

Only GET handlers exist; the server holds one prepared dataset and one
stream lock.
