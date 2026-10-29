#!/usr/bin/env python3
"""Build the derived RTAB-Map streaming image (idempotent).

Tag is a content hash of deploy/rtabmap-stream sources, so a source
change forces a rebuild and an unchanged source never rebuilds.
Nothing is installed on the host.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "deploy" / "rtabmap-stream"


def image_tag() -> str:
    sys.path.insert(0, str(ROOT / "src"))
    from surmap.slam.streaming import stream_image_tag

    return stream_image_tag(SOURCE_DIR)


def main() -> int:
    tag = image_tag()
    present = subprocess.run(
        ["docker", "image", "inspect", tag], capture_output=True, text=True
    )
    if present.returncode == 0:
        print(f"image {tag} already present")
        return 0
    print(f"building {tag} (once per source hash, ~1-3 min)…")
    result = subprocess.run(
        ["docker", "build", "-t", tag, str(SOURCE_DIR)], text=True
    )
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
