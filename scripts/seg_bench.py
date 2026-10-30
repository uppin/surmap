#!/usr/bin/env python3
"""Offline segmentation benchmark.

Live segmentation and labelling stay behind ``SURMAP_LIVE_*`` and the
``SURMAP_BUDGET_*`` caps. Fuse, score, and compare never open a socket.

    uv run python scripts/seg_bench.py run --route replay \\
        --detections detections.jsonl --out replay.jsonl --usage usage.jsonl
    uv run python scripts/seg_bench.py fuse --bench bench --detections replay.jsonl --out landmarks.json
    uv run python scripts/seg_bench.py score --bench bench --detections replay.jsonl \\
        --landmarks landmarks.json --route replay --out report.json
    uv run python scripts/seg_bench.py compare --reports report.json --out compare.md

See docs/segmentation-benchmark.md.
"""

from __future__ import annotations

import sys

from surmap.segbench.cli import main

if __name__ == "__main__":
    sys.exit(main())
