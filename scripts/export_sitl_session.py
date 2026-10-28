#!/usr/bin/env python3
"""Export a Gazebo/PX4 SITL capture directory to a SurMap EuRoC session.

SurMap is passive survey only: this script never talks to PX4. Fly in
SITL (or record topics), dump a capture directory, then run:

    uv run python scripts/export_sitl_session.py \\
        --capture ~/sitl-runs/hover-01 \\
        --output ~/sitl-runs/hover-01-euroc

See docs/simulation/px4-sitl.md for the capture layout and Gazebo notes.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from surmap.simulation import export_euroc_session, load_sitl_capture


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--capture",
        type=Path,
        required=True,
        help="SITL capture directory (calibration.json, frames.jsonl, …)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Directory that will receive mav0/ (an existing mav0/ is replaced)",
    )
    args = parser.parse_args(argv)

    frames, calibration, gps = load_sitl_capture(args.capture)
    result = export_euroc_session(args.output, frames, calibration, gps)
    print(
        f"exported {result.pair_count} stereo pairs"
        f" and {result.gps_count} GPS checkpoints → {result.root / 'mav0'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
