"""Fetch the Bevy simulation's pinned CC0 assets into examples/bevy-sitl-poc/assets/.

Every file is pinned by URL and sha256 in `assets/assets.lock.json`; files
already present with the right hash are kept. Nothing fetched is committed.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from surmap.simulation.sim_assets import fetch_assets, load_asset_pins

ASSETS = Path(__file__).resolve().parents[1] / "examples" / "bevy-sitl-poc" / "assets"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", type=Path, default=ASSETS, help="assets directory")
    args = parser.parse_args()
    pins = load_asset_pins(args.dest / "assets.lock.json")
    fetch_assets(pins, args.dest)
    print(f"{len(pins)} assets present and verified in {args.dest}")


if __name__ == "__main__":
    main()
