#!/usr/bin/env python3
"""Launch the SurMap browser demo on a recorded dataset.

Downloads and caches the selected dataset on first run (later runs
reuse the cache), then serves the demo page: real-time stereo video
with projected scene-point detections overlaid, and — at the end of
playback — the real RTAB-Map map built from the same frames.

    uv run python scripts/demo.py                      # full EuRoC V1_01
    uv run python scripts/demo.py --frames 200         # first 200 pairs only
    uv run python scripts/demo.py --prepare-only       # just download+cache
    uv run python scripts/demo.py --list-datasets
    uv run python scripts/demo.py --coral-model-dir tests/fixtures/coral_model \
        --sam2-model-dir ~/.cache/surmap/sam2/sam2.1-hiera-small  # + SAM 2.1 masks

Add a dataset by adding one entry to `DATASETS` in
`surmap.demo.datasets`; it then appears in `--list-datasets` and as
a `--dataset` choice here. Playback is paced server-side at `--fps`
(default: the dataset's native 20 fps). With
`SURMAP_RTABMAP_SHARED_CONTAINER` set, the final map is built inside
that reusable container, which is never stopped or removed.

SAM 2.1 (`scripts/fetch_sam2_model.py` exports it) is prompted by
the Coral boxes: masks are drawn live, and after the map is built
each RTAB-Map keyframe is segmented and its masked stereo points are
placed on the map as a labelled object layer.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from surmap.demo.datasets import DATASETS, default_cache_dir, ensure_dataset
from surmap.demo.server import make_demo_server
from surmap.detection.profiles import DEFAULT_PROFILE, MODEL_PROFILES
from surmap.survey.sam2 import DEVICES, MODEL_DIR_ENV, default_sam2_model_dir


def main(argv: list[str] | None = None) -> int:
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
    parser.add_argument("--fps", type=float, default=20.0, help="server-side playback rate")
    parser.add_argument("--frames", type=int, default=0, help="pairs to play (0 = full sequence)")
    parser.add_argument("--start", type=int, default=0, help="first pair index to play")
    parser.add_argument("--no-rtabmap", action="store_true", help="skip the final RTAB-Map map")
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
        "--sam2-model-dir",
        type=Path,
        default=None,
        help="exported SAM 2.1 model (scripts/fetch_sam2_model.py) for masks prompted by "
        f"the Coral boxes (default: ${MODEL_DIR_ENV}, else {default_sam2_model_dir()} "
        "when present; needs --coral-model-dir)",
    )
    parser.add_argument(
        "--sam2-device",
        choices=DEVICES,
        default="auto",
        help="SAM 2.1 encoder: auto = CUDA, else CoreML on the Mac GPU (Metal), else CPU",
    )
    parser.add_argument("--no-sam", action="store_true", help="never run SAM 2.1")
    parser.add_argument(
        "--prepare-only", action="store_true", help="download+cache the dataset and exit"
    )
    args = parser.parse_args(argv)

    if args.list_datasets:
        for spec in DATASETS.values():
            print(f"{spec.dataset_id}\t{spec.title}\t{spec.description}")
        return 0

    prepared = ensure_dataset(DATASETS[args.dataset], args.cache_dir or default_cache_dir())
    if args.prepare_only:
        print(f"cached under {prepared.root}")
        return 0

    coral_dir = args.coral_model_dir
    if coral_dir is None and os.environ.get("SURMAP_CORAL_MODEL_DIR"):
        coral_dir = Path(os.environ["SURMAP_CORAL_MODEL_DIR"])
    sam_dir = None
    if not args.no_sam:
        sam_dir = args.sam2_model_dir
        if sam_dir is None and (default_sam2_model_dir() / "manifest.json").is_file():
            sam_dir = default_sam2_model_dir()
    if sam_dir is not None and coral_dir is None:
        if args.sam2_model_dir is not None:
            parser.error("--sam2-model-dir needs --coral-model-dir: Coral boxes prompt SAM 2.1")
        sam_dir = None  # a cached model alone does not switch SAM on without Coral
    server = make_demo_server(
        prepared,
        host=args.host,
        port=args.port,
        fps=args.fps,
        max_frames=args.frames,
        start_index=args.start,
        with_rtabmap=not args.no_rtabmap,
        coral_model_dir=coral_dir,
        coral_model=args.coral_model,
        sam2_model_dir=sam_dir,
        sam2_device=args.sam2_device,
    )
    host, port = server.server_address[:2]
    if sam_dir is not None:
        print(f"SAM 2.1 masks on (model {sam_dir}, {args.sam2_device}), prompted by Coral boxes")
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
