#!/usr/bin/env python3
"""Print SurMap credit-usage totals per provider, model, and UTC day."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from surmap.usage import default_usage_log_path, render_usage_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--log",
        type=Path,
        default=None,
        help="Usage JSONL file (default: $SURMAP_USAGE_LOG or ~/.surmap/usage.jsonl)",
    )
    args = parser.parse_args(argv)
    path = args.log if args.log is not None else default_usage_log_path()
    sys.stdout.write(render_usage_report(path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
