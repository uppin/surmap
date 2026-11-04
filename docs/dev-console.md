# Dev console (`scripts/demo.py`)

An engineering console that plays a public stereo dataset in real time
and builds the map live:

```bash
uv run python scripts/demo.py
# open http://127.0.0.1:8765/
```

## Features

- **Live RTAB-Map** (`StreamingRtabmapBackend`): stereo pairs go over
  stdin to a `librtabmap` process in a pinned `linux/amd64` container,
  which streams odometry, keyframe points, and graph re-optimizations
  without stalling playback. `--no-rtabmap` runs without Docker.
- **SAM 3.1 video mode** (`--sam-device cuda:0`): `facebook/sam3.1`
  (gated; `HF_TOKEN` in `.env`) runs in 16-frame windows so long videos
  fit a 16 GB card. `--sam-fake` runs a stand-in without a GPU. Each
  scene has a default concept (`box`, `car`, `person`), changeable on
  the page or with `--sam-label`.
- **SAM 3.1 on a Mac** (`--sam-device mps`): on Apple silicon, SAM
  3.1's image model runs per frame on the GPU (Metal), about 2.4 s a
  frame, with ids kept by box overlap. Play at SAM's pace (`--fps 0.35`)
  so regions stay within the sidecar's 10 s buffer.
- **Persistent surfaces** (`surmap.survey.surfaces`): mask points that
  land on earlier points continue the same surface across SAM window
  resets. A surface that drifts 40 cm or more is drawn red as a moving
  object.
  A region keeps only its points within 1.5 m of its median range from
  the camera (the background a mask edge catches is cut away), and a
  region needs 50 such points to start or grow a surface.
- **Video toggles**: **RTAB-Map points** (checked by default) shows or
  hides the frame's tracked features; **Dense depth** lays RTAB-Map's
  dense stereo depth of the shown frame over it in the same near → far
  colours (`GET /runs/<run_id>/dense-depth?frame_id=<n>`: the SGBM
  disparity the sidecar journalled for that frame, a replay reading its
  recording's; clear where nothing matched), live or on a rewound moment.
  Only frames RTAB-Map computed dense stereo for (the SAM frames) have it;
  nothing else is matched in its place.
- **3D pane** (server-rendered, every map point): **Follow** (checked by
  default) frames it like a navigation app, from behind and above the
  camera along its heading, with the camera low in view; tilt and zoom
  adjust it, and an orbit or a pan takes over. Drag, Shift+drag,
  wheel or pinch work during a run, after it and on a rewound moment.
  Hovering a surface names it (`car #27 · 336 pts · static`) and
  selects all its points; a click opens it in the object feed.
- **Object feed**: one card per surface with its own client-side 3D
  preview (drag, Shift+drag, wheel or pinch, or buttons).
- **SAM pane**: each mask's own dense points, coloured near → far, and
  a card per object next to it (cyan: in 3D, with its surface id; grey:
  too few depth points yet, with SAM's track id). Hovering a mask or
  its card selects the object in 3D and the feed, a click opens it in
  the feed, and a surface hovered anywhere is outlined there in yellow.
- **Run history**: every frame, detection, and cloud update is stored
  in `demo-history.db`; the timeline rewinds through it.
- **Replay cached run, Rebuild to record**: opening or reloading a
  scene plays nothing, so it never takes a running build over. When the
  scene has a complete recording, **Replay cached run** reruns the
  newest one from the journal, with neither RTAB-Map nor SAM, and does
  not persist it again (the timeline scrubs the recording itself).
  **Rebuild** is the only action that runs RTAB-Map (and SAM) and
  records a new run; applying a new SAM prompt rebuilds too. A run cut
  short by another viewer's takeover is recorded as interrupted, never
  cached.
- **Export / Import**: Export downloads the selected run (and any run it
  replays) as one `.surmaprun` file: a gzipped SQLite database in the run
  history's schema, with frames, journal, map, SAM masks, surfaces, rig and
  dense buffer. Import adds a file's runs to this console under their own
  ids, skipping runs already present, and they replay and rewind like runs
  recorded there. Headless: `python -m surmap.demo.run_archive export
  RUN_ID FILE` and `import FILE` (`--history-db` to pick the store). The
  447-frame KITTI 0009 SAM run is about 200 MB exported.
- **Rebuild RTAB-Map** (`GET /stream?rebuild_rtabmap=<run_id>`): runs
  RTAB-Map live again over the run's scene while SAM is not run: each frame
  gets the masks the run recorded for it (`surmap.demo.sam_journal`, by
  `t_ns`). The result is a new recording, with the current sidecar's map
  and dense buffer, that becomes the scene's cached run. Use it after a
  sidecar change, or on a host without the SAM runtime.
- **Replay run** (speed 1×, 4× or max; `GET /stream?replay=<run_id>&speed=N`):
  every run keeps a journal of its events and RTAB-Map's dense buffer
  (the disparity computed for each SAM frame, with its pose), so a
  persisted run plays back without starting RTAB-Map or SAM. Frames,
  map and masks come from the journal; regions and surfaces are
  recomputed by the current code (`surmap.demo.replay.JournalPlayer`
  takes the `SurfaceMap` under tuning). Each replay is saved as a new
  run naming its source, for comparison. A replay or a rewound moment
  shows the run's recorded SAM masks even on a console started without
  SAM, and a long journal starts at once (it is streamed, and map views
  are drawn at the live 0.33 s cadence).

## Demo scenes

Datasets are fetched on first use, SHA-256 verified, and cached in
`~/.cache/surmap/demo-datasets` (`surmap.demo.datasets`, never
re-hosted):

| Scene | Zip | Licence |
|---|---|---|
| `euroc-v1-01-easy` (indoor MAV, 376×240 @ 20 Hz) | 1.15 GB | ETH ASL research dataset |
| `kitti-2011-09-26-drive-0009` (city drive, 620×188 @ 10 Hz) | 1.79 GB | CC BY-NC-SA 3.0 |
| `ntu-viral-sbs-01` (outdoor drone flight) | 3.78 GB | CC BY-NC-SA 4.0 |

## Flags

Useful flags: `--dataset`, `--list-datasets`, `--frames N`,
`--start I`, `--fps F`, `--rtabmap-mode live|batch`, `--prepare-only`,
`--sam-model <id|path>`, `--cm5-host`, `--station-host`,
`--history-db`.

Run `uv run python scripts/demo.py --help` for the full list. Remote
deployment of the console against the CM5 and station servers:
[deployment.md](deployment.md). Back to the [README](../README.md).
