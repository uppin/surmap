#!/usr/bin/env python3
"""Add Gazebo label-system plugins to the disaster-block models.

Labels: 1 person (survivors), 2 car, 3 debris, 4 water. The world also
gets an empty label-system plugin. Running this twice is a no-op.

    uv run python scripts/gz_label_models.py
    uv run python scripts/gz_label_models.py --sdf docs/simulation/gz/worlds/disaster_block.sdf
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from surmap.simulation.disaster_world import disaster_world_sdf
from surmap.simulation.gz_labels import label_sdf


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdf", type=Path, default=None)
    args = parser.parse_args(argv)
    path = args.sdf if args.sdf is not None else disaster_world_sdf()
    original = path.read_text(encoding="utf-8")
    edited = label_sdf(original)
    if edited.text != original:
        path.write_text(edited.text, encoding="utf-8")
    print(f"labelled {len(edited.labelled)} models in {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
