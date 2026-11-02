#!/usr/bin/env python3
"""Per-class F1 of the Muse label clients on LADI v2 aerial disaster imagery.

LADI v2 is CC BY 4.0 (MIT Lincoln Laboratory). Images are downloaded on
demand to ``~/.cache/surmap/ladi-v2``; nothing is committed.

    uv run python scripts/eval_disaster_labelling.py --download-only --limit 10
    SURMAP_LIVE_META=1 uv run python scripts/eval_disaster_labelling.py --limit 10
    SURMAP_LIVE_META=1 SURMAP_LIVE_BASETEN=1 \\
        uv run python scripts/eval_disaster_labelling.py --provider both --limit 10 \\
        --out ~/surmap-eval/ladi.json

See docs/disaster-labelling-eval.md.
"""

from __future__ import annotations

import sys

from surmap.evaluation.cli import main

if __name__ == "__main__":
    sys.exit(main())
