#!/usr/bin/env python3
"""Download openly licensed disaster datasets into the local cache.

Boreal Forest Fire (CC BY 4.0, Fairdata) and NOAA Emergency Response Imagery
for the January 2025 Eaton and Palisades fires (CC0-1.0, AWS ``noaa-eri-pds``).
Files land in ``~/.cache/surmap/{boreal-fire,noaa-eri-2025}``; nothing is
committed.

    uv run python scripts/download_disaster_data.py boreal --sizes
    uv run python scripts/download_disaster_data.py boreal --package
    uv run python scripts/download_disaster_data.py boreal --split test --limit 5
    uv run python scripts/download_disaster_data.py boreal --videos 2 --dry-run
    uv run python scripts/download_disaster_data.py noaa --fire palisades --limit 20 --dry-run
    uv run python scripts/download_disaster_data.py noaa --fire eaton --limit 2 --max-tile-mb 50

See docs/disaster-datasets.md.
"""

from __future__ import annotations

import sys

from surmap.datasets.cli import main

if __name__ == "__main__":
    sys.exit(main())
