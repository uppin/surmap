"""``scripts/download_disaster_data.py``: cache open disaster datasets locally.

``boreal`` fetches the Boreal Forest Fire UAV dataset (CC BY 4.0) from
Fairdata; ``noaa`` fetches NOAA's 2025 California fire imagery tiles
(CC0-1.0) from the public ``noaa-eri-pds`` bucket. ``--dry-run`` (alias
``--list``) prints what would be downloaded, with sizes, and writes nothing.
Reruns skip finished files and resume partial ones. See
docs/disaster-datasets.md.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from surmap.datasets.disaster import (
    BOREAL_ATTRIBUTION,
    BOREAL_SITES,
    BOREAL_SPLITS,
    BOREAL_SUBSETS,
    NOAA_ATTRIBUTION,
    NOAA_FIRES,
    DatasetError,
    Plan,
    Transport,
    UrllibTransport,
    boreal_listing,
    boreal_package_plan,
    boreal_package_resolver,
    boreal_plan,
    boreal_resolver,
    boreal_subset_sizes,
    download_plan,
    extract_package,
    human_size,
    noaa_plan,
    write_attribution,
)

_SHOWN = 40


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="dataset", required=True)

    boreal = sub.add_parser("boreal", help="Boreal Forest Fire UAV dataset (CC BY 4.0)")
    boreal.add_argument(
        "--subset",
        action="append",
        choices=sorted(BOREAL_SUBSETS),
        help="segmentation (Subset C, default), bbox (Subset A), videos (Subset B), "
        "notebook; repeatable",
    )
    boreal.add_argument(
        "--site", action="append", choices=BOREAL_SITES, help="bbox/videos site; repeatable"
    )
    boreal.add_argument(
        "--split", action="append", choices=BOREAL_SPLITS, help="segmentation split; repeatable"
    )
    boreal.add_argument(
        "--limit", type=int, default=None, help="at most N samples (an image with its labels)"
    )
    boreal.add_argument(
        "--videos",
        type=int,
        default=None,
        metavar="N",
        help="shorthand for --subset videos --limit N (each clip is ~0.4 GB)",
    )
    boreal.add_argument(
        "--package",
        action="store_true",
        help="fetch each whole subset as one ready-made Fairdata zip and unpack it "
        "(much faster than file by file; no --site/--split/--limit/--videos)",
    )
    boreal.add_argument(
        "--keep-package", action="store_true", help="keep the zip after unpacking it"
    )
    boreal.add_argument(
        "--sizes", action="store_true", help="print each subset's file count and size, then exit"
    )

    noaa = sub.add_parser("noaa", help="NOAA ERI 2025 California fires imagery (CC0-1.0)")
    noaa.add_argument("--fire", choices=sorted(NOAA_FIRES), default=None)
    noaa.add_argument(
        "--bbox",
        type=float,
        nargs=4,
        metavar=("WEST", "SOUTH", "EAST", "NORTH"),
        default=None,
        help="WGS 84 degrees; overrides the --fire area",
    )
    noaa.add_argument("--limit", type=int, default=None, help="at most N GeoTIFF tiles")
    noaa.add_argument(
        "--max-tile-mb",
        type=float,
        default=None,
        help="skip tiles larger than this (tiles are 6 MB to 1.65 GB)",
    )

    for each in (boreal, noaa):
        each.add_argument("--cache-dir", type=Path, default=None, help="dataset cache folder")
        each.add_argument(
            "--dry-run",
            "--list",
            dest="dry_run",
            action="store_true",
            help="show what would be downloaded, with sizes; download nothing",
        )
    return parser


def _print_plan(plan: Plan) -> None:
    for item in plan.files[:_SHOWN]:
        mark = "  [cached]" if plan.cached(item) else ""
        print(f"  {human_size(item.size):>10}  {item.relpath}{mark}")
    if len(plan.files) > _SHOWN:
        print(f"  ... {len(plan.files) - _SHOWN} more files")
    print(
        f"{plan.dataset}: {len(plan.files)} files, {human_size(plan.total_bytes)} total, "
        f"{human_size(plan.missing_bytes())} to download into {plan.root}"
    )


def _print_sizes(transport: Transport) -> None:
    files = boreal_listing(transport)
    for name, (count, size) in boreal_subset_sizes(files).items():
        print(f"  {name:<13} {BOREAL_SUBSETS[name]:<50} {count:6d} files {human_size(size):>10}")
    total = sum(item.size for item in files)
    print(f"boreal-fire: {len(files)} files, {human_size(total)} in total")


def _boreal_package(args: argparse.Namespace, http: Transport, subsets: list[str]) -> int:
    if args.site or args.split or args.limit is not None or args.videos is not None:
        raise DatasetError("--package fetches whole subsets; drop --site/--split/--limit/--videos")
    plan, expected = boreal_package_plan(http, subsets=subsets, cache_dir=args.cache_dir)
    if args.dry_run:
        _print_plan(plan)
        return 0
    write_attribution(plan.root, BOREAL_ATTRIBUTION)
    download_plan(plan, http, resolve=boreal_package_resolver(http), resumable=False, log=print)
    unpacked = 0
    for item in plan.files:
        zip_path = plan.root / item.relpath
        unpacked += extract_package(zip_path, plan.root, expected, log=print)
        if not args.keep_package:
            zip_path.unlink()
    if not args.keep_package and (plan.root / "packages").is_dir():
        if not any((plan.root / "packages").iterdir()):
            (plan.root / "packages").rmdir()
    print(f"{plan.dataset}: {len(plan.files)} package(s), {unpacked} files unpacked in {plan.root}")
    return 0


def main(argv: Sequence[str] | None = None, *, transport: Transport | None = None) -> int:
    args = build_parser().parse_args(argv)
    http: Transport = transport if transport is not None else UrllibTransport()
    try:
        if args.dataset == "boreal":
            if args.sizes:
                _print_sizes(http)
                return 0
            subsets = list(args.subset or [])
            if args.package:
                return _boreal_package(args, http, subsets or ["segmentation"])
            limit = args.limit
            if args.videos is not None:
                subsets = [*subsets, "videos"] if "videos" not in subsets else subsets
                limit = args.videos
            plan = boreal_plan(
                http,
                subsets=subsets or ["segmentation"],
                sites=args.site or (),
                splits=args.split or (),
                limit=limit,
                cache_dir=args.cache_dir,
            )
            attribution, resolve, resumable = BOREAL_ATTRIBUTION, boreal_resolver(http), False
        else:
            max_bytes = None if args.max_tile_mb is None else int(args.max_tile_mb * 1_000_000)
            plan = noaa_plan(
                http,
                fire=args.fire,
                bbox=tuple(args.bbox) if args.bbox is not None else None,
                limit=args.limit,
                max_tile_bytes=max_bytes,
                cache_dir=args.cache_dir,
            )
            attribution, resolve, resumable = NOAA_ATTRIBUTION, None, True
        if args.dry_run:
            _print_plan(plan)
            return 0
        if not plan.files:
            print(f"{plan.dataset}: nothing matched; try --dry-run with other filters")
            return 1
        write_attribution(plan.root, attribution)
        result = download_plan(plan, http, resolve=resolve, resumable=resumable, log=print)
    except (DatasetError, OSError) as exc:
        print(f"download_disaster_data: {exc}", file=sys.stderr)
        return 2
    print(
        f"{plan.dataset}: {result.downloaded} downloaded "
        f"({human_size(result.bytes_written)}), {result.skipped} already cached, in {plan.root}"
    )
    return 0
