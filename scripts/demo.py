#!/usr/bin/env python3
"""Launch the SurMap browser demo on a recorded dataset.

Serves the demo page without downloading anything: every registered
scene is offered in the page's scene picker, and a scene is downloaded
into the cache (with progress on the page) the first time it is picked;
later picks and launches reuse the cache. The page plays the stereo
video with RTAB-Map's tracked keypoints overlaid by depth while the map
builds live, with Pause/Resume and Restart.

    uv run python scripts/demo.py                      # opens on EuRoC V1_01
    uv run python scripts/demo.py --dataset kitti-2011-09-26-drive-0009
    uv run python scripts/demo.py --frames 200         # first 200 pairs only
    uv run python scripts/demo.py --prepare-only       # just download+cache --dataset
    uv run python scripts/demo.py --list-datasets
    uv run python scripts/demo.py --sam-device cuda:0 --sam-model /models/sam3.1.onnx

With `--sam-device` the frame preview also shows SAM detections
for each frame, segmented in continuous (video) mode on that GPU
device. The model defaults to the real SAM 3.1 checkpoint
(`facebook/sam3.1`, downloaded with `$HF_TOKEN` from the project
`.env`); `--sam-model` overrides it with another HF id, a local
SAM 3.1 `.pt`, or an `.onnx` export (or set `$SURMAP_SAM_MODEL`).
Without `--sam-device` no SAM runs. The real model needs the
PyTorch stack in the project env (see `sam3_torch`); the `.onnx`
path needs `onnxruntime-gpu` for a GPU device. Startup fails by
name when a runtime, model or provider is missing.

Add a dataset by adding one entry to `DATASETS` in
`surmap.demo.datasets`; it then appears in the page's picker, in
`--list-datasets` and as a `--dataset` choice here. Playback is paced server-side at `--fps`
(default: the dataset's native rate). With
`SURMAP_RTABMAP_SHARED_CONTAINER` set, the final map is built inside
that reusable container, which is never stopped or removed.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from surmap.demo.datasets import DATASETS, default_cache_dir, ensure_dataset
from surmap.demo.server import make_demo_server
from surmap.env import load_env
from surmap.detection.profiles import DEFAULT_PROFILE, MODEL_PROFILES


def main(argv: list[str] | None = None) -> int:
    load_env()  # project .env fills gaps (HF_TOKEN, SURMAP_SAM_MODEL, ...)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=sorted(DATASETS), default="euroc-v1-01-easy")
    parser.add_argument(
        "--list-datasets", action="store_true", help="list registry entries and exit"
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=None,
        help="default: $SURMAP_DEMO_CACHE_DIR or ~/.cache/surmap/demo-datasets",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--fps", type=float, default=None, help="server-side playback rate (default: dataset's)"
    )
    parser.add_argument("--frames", type=int, default=0, help="pairs to play (0 = full sequence)")
    parser.add_argument("--start", type=int, default=0, help="first pair index to play")
    parser.add_argument("--no-rtabmap", action="store_true", help="skip the final RTAB-Map map")
    parser.add_argument(
        "--rtabmap-mode",
        choices=["live", "batch"],
        default="live",
        help="live: map grows during playback; batch: map built at the end",
    )
    parser.add_argument(
        "--coral-model-dir",
        type=Path,
        default=None,
        help="prepared Coral model dir for the tracked-box overlay "
        "(default: $SURMAP_CORAL_MODEL_DIR)",
    )
    parser.add_argument(
        "--coral-model",
        choices=sorted(MODEL_PROFILES),
        default=DEFAULT_PROFILE,
        help="detector model profile for the overlay",
    )
    parser.add_argument(
        "--sam-device",
        "--sam-gpu",
        "--gpu-device",
        dest="sam_device",
        default=None,
        metavar="DEVICE",
        help="run SAM in continuous (video) mode on this GPU device, "
        "e.g. cuda:0 or 0, and show its detections on the frame preview "
        "(without it no SAM runs)",
    )
    parser.add_argument(
        "--sam-model",
        "--sam3-model",
        dest="sam_model",
        type=Path,
        default=None,
        help="SAM model for --sam-device: an HF id, a local SAM 3.1 .pt, "
        "or an .onnx export (default: facebook/sam3.1, or $SURMAP_SAM_MODEL)",
    )
    parser.add_argument(
        "--sam-label",
        default="object",
        help="label attached to SAM detections (concept prompt of the export)",
    )
    parser.add_argument(
        "--prepare-only", action="store_true", help="download+cache the dataset and exit"
    )
    args = parser.parse_args(argv)

    sam_model = args.sam_model
    if sam_model is None and os.environ.get("SURMAP_SAM_MODEL"):
        sam_model = Path(os.environ["SURMAP_SAM_MODEL"])
    if sam_model is None and os.environ.get("SURMAP_SAM3_MODEL"):
        sam_model = Path(os.environ["SURMAP_SAM3_MODEL"])
    if sam_model is not None and args.sam_device is None:
        parser.error("--sam-model requires --sam-device (e.g. --sam-device cuda:0)")

    if args.list_datasets:
        for spec in DATASETS.values():
            print(f"{spec.dataset_id}\t{spec.title}\t{spec.description}")
        return 0

    cache_dir = args.cache_dir or default_cache_dir()
    if args.prepare_only:
        prepared = ensure_dataset(DATASETS[args.dataset], cache_dir)
        print(f"cached under {prepared.root}")
        return 0

    coral_dir = args.coral_model_dir
    if coral_dir is None and os.environ.get("SURMAP_CORAL_MODEL_DIR"):
        coral_dir = Path(os.environ["SURMAP_CORAL_MODEL_DIR"])
    # Nothing is downloaded here: a scene is fetched into the cache the
    # first time it is picked on the page (with progress shown there).
    server = make_demo_server(
        cache_dir=cache_dir,
        default_dataset=args.dataset,
        host=args.host,
        port=args.port,
        fps=args.fps,
        max_frames=args.frames,
        start_index=args.start,
        with_rtabmap=not args.no_rtabmap,
        rtabmap_mode=args.rtabmap_mode,
        coral_model_dir=coral_dir,
        coral_model=args.coral_model,
        sam_model=sam_model,
        sam_device=args.sam_device,
        sam_label=args.sam_label,
    )
    host, port = server.server_address[:2]
    if args.sam_device is not None:
        print(f"SAM (video): {sam_model or 'facebook/sam3.1'} on {args.sam_device}")
    print(f"SurMap demo: open http://{host}:{port}/ in a browser (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
