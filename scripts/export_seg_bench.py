#!/usr/bin/env python3
"""Export a SITL capture to a seg_bench directory at 1 Hz keyframes.

The capture must contain segmentation images and a camera pose. Record
those with scripts/ros2/dump_sitl_capture.py --seg and --pose. This
script does not launch Gazebo and does not call a model.

    uv run python scripts/export_seg_bench.py \\
      --capture ~/sitl-runs/disaster-01 \\
      --out ~/sitl-runs/bench
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from surmap.segbench.dataset import export_sitl_bench, load_bench, select_dev_set


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--hz", type=float, default=1.0)
    parser.add_argument("--dev-set", action="store_true")
    parser.add_argument("--survivors", type=int, default=20)
    parser.add_argument("--negatives", type=int, default=10)
    args = parser.parse_args(argv)
    bench = export_sitl_bench(args.capture, args.out, hz=args.hz)
    if args.dev_set:
        dataset = load_bench(bench)
        chosen = select_dev_set(
            dataset.frames,
            survivor_count=args.survivors,
            negative_count=args.negatives,
        )
        print(
            f"dev set would keep {len(chosen)} frames "
            f"({args.survivors} survivor, {args.negatives} hard negative)"
        )
    print(f"wrote bench {bench}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
