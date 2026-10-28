#!/usr/bin/env python3
"""SurMap survey viewer: camera, height-coloured map, landmark list.

    uv run python scripts/viewer.py --source preview
    uv run python scripts/viewer.py                       # EuRoC, same cache as scripts/demo.py
    uv run python scripts/viewer.py --source sitl --capture ~/sitl-runs/hover-01

Open http://localhost:8770/ in a browser. On WSL2 that is the Windows
browser at the same URL. No GPU and no API key. See docs/viewer.md.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

from surmap.demo.datasets import DATASETS, default_cache_dir, ensure_dataset
from surmap.viewer.euroc import EurocReplay
from surmap.viewer.preview import PreviewReplay
from surmap.viewer.server import Replay, make_viewer_server
from surmap.viewer.sitl import SitlReplay


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=("euroc", "preview", "sitl"), default="euroc")
    parser.add_argument("--dataset", choices=sorted(DATASETS), default="euroc-v1-01-easy")
    parser.add_argument("--capture", type=Path, default=None, help="PX4 SITL capture directory")
    parser.add_argument(
        "--snapshot",
        type=Path,
        default=None,
        help="surmap.semantic_map_snapshot.v1 JSON (optional; preview has a bundled one)",
    )
    parser.add_argument("--cache-dir", type=Path, default=None)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8770)
    parser.add_argument("--fps", type=float, default=10.0)
    parser.add_argument(
        "--frames", type=int, default=0, help="ticks to play (0 = the whole source)"
    )
    parser.add_argument("--start", type=int, default=0, help="first EuRoC pair index")
    parser.add_argument("--no-stereo", action="store_true", help="skip the EuRoC stereo cloud")
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--coral-model-dir", type=Path, default=None)
    args = parser.parse_args(argv)

    if args.snapshot is not None and not args.snapshot.is_file():
        print(f"snapshot not found: {args.snapshot}", file=sys.stderr)
        return 2
    if args.source == "sitl" and args.capture is None:
        print("--source sitl needs --capture", file=sys.stderr)
        return 2

    factory = _factory(args)
    server = make_viewer_server(
        factory, host=args.host, port=args.port, fps=args.fps, loop=args.loop
    )
    host, port = server.server_address[:2]
    shown = "localhost" if host in ("0.0.0.0", "") else host
    print(f"SurMap viewer: open http://{shown}:{port}/ in a browser (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
    return 0


def _factory(args: argparse.Namespace) -> Callable[[], Replay]:
    if args.source == "preview":

        def preview() -> Replay:
            return PreviewReplay(frames=args.frames or 72, snapshot_path=args.snapshot)

        return preview
    if args.source == "sitl":
        capture = args.capture
        assert capture is not None

        def sitl() -> Replay:
            return SitlReplay(capture, snapshot_path=args.snapshot, max_frames=args.frames)

        return sitl

    prepared = ensure_dataset(DATASETS[args.dataset], args.cache_dir or default_cache_dir())
    detections = None
    if args.coral_model_dir is not None:
        from surmap.demo.server import coral_detection_source

        detections = coral_detection_source(args.coral_model_dir)

    def euroc() -> Replay:
        return EurocReplay(
            prepared,
            snapshot_path=args.snapshot,
            max_frames=args.frames,
            start_index=args.start,
            stereo=not args.no_stereo,
            detections=detections,
        )

    return euroc


if __name__ == "__main__":
    sys.exit(main())
