"""Demo runs exported to one `.surmaprun` file and imported into any console's history.

A `.surmaprun` file is a gzipped SQLite database in the run history's own
schema (`history.SCHEMA`) holding one exported run, every run its replay
lineage reaches (a replay answers its regions from its source's rig and
dense buffer), and `export_info(format_version, run_id, exported_at)`. So
an imported run replays and rewinds like one recorded there: frames,
journal, map updates, SAM masks, surfaces, rig and dense buffer all come
along, and nothing has to be recorded again.

Runs keep their ids: importing a run already in the history skips it, so
importing a file twice changes nothing. AUTOINCREMENT rows (map updates,
detections, surfaces, journal events) are renumbered in their order. A
run still recording cannot be exported, as it is not complete yet.

    python -m surmap.demo.run_archive export RUN_ID FILE [--history-db PATH]
    python -m surmap.demo.run_archive import FILE [--history-db PATH]
"""

from __future__ import annotations

import argparse
import gzip
import os
import shutil
import sqlite3
import sys
import tempfile
import time
import zlib
from collections.abc import Sequence
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path

from surmap.demo.datasets import default_cache_dir
from surmap.demo.history import SCHEMA, RunHistoryStore

FORMAT_VERSION = 1
SUFFIX = ".surmaprun"

# Every table that holds a run's rows, and those whose `id` is renumbered on import.
RUN_TABLES = (
    "runs",
    "frames",
    "maps",
    "detections",
    "surface_points",
    "events",
    "run_rigs",
    "dense_frames",
    "run_sources",
)
_RENUMBERED = frozenset({"maps", "detections", "surface_points", "events"})
_EXPORT_INFO = (
    "CREATE TABLE export_info (format_version INTEGER NOT NULL, run_id TEXT NOT NULL,"
    " exported_at REAL NOT NULL)"
)


class RunNotExportable(Exception):
    """The run is not in the history, or is still recording."""


class NotARunArchive(Exception):
    """The file is not a `.surmaprun` export this version can read."""


@dataclass(frozen=True)
class ImportReport:
    imported: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def archive_name(dataset_id: str, run_id: str) -> str:
    """The file name a run is exported as."""
    return f"surmap-{dataset_id}-{run_id[:8]}{SUFFIX}"


def _lineage(db: sqlite3.Connection, run_id: str) -> list[str]:
    """`run_id`, then each run it replays, to the recording at the end of the chain."""
    chain = [run_id]
    while True:
        row = db.execute(
            "SELECT source_run_id FROM run_sources WHERE run_id = ?", (chain[-1],)
        ).fetchone()
        if row is None or row[0] in chain:
            return chain
        chain.append(str(row[0]))


def _columns(db: sqlite3.Connection, table: str, schema: str = "main") -> str:
    names = [row[1] for row in db.execute(f"PRAGMA {schema}.table_info({table})")]
    return ", ".join(name for name in names if not (table in _RENUMBERED and name == "id"))


def _temporary(beside: Path, suffix: str) -> Path:
    handle, name = tempfile.mkstemp(dir=beside, suffix=suffix)
    os.close(handle)
    return Path(name)


def export_from(store: RunHistoryStore, run_id: str, out: Path) -> list[str]:
    """Write `run_id` and its replay lineage to `out`; the run ids exported."""
    out.parent.mkdir(parents=True, exist_ok=True)
    database = _temporary(out.parent, ".surmaprun-db")
    try:
        with store.exclusive() as db:
            row = db.execute("SELECT status FROM runs WHERE run_id = ?", (run_id,)).fetchone()
            if row is None:
                raise RunNotExportable(f"no run {run_id} in {store.path}")
            if str(row[0]) == "running":
                raise RunNotExportable(f"run {run_id} is still recording")
            chain = _lineage(db, run_id)
            with closing(sqlite3.connect(database)) as archive, archive:
                archive.executescript(SCHEMA)
                archive.execute(_EXPORT_INFO)
                archive.execute(
                    "INSERT INTO export_info VALUES (?, ?, ?)",
                    (FORMAT_VERSION, run_id, time.time()),
                )
            db.execute("ATTACH DATABASE ? AS archive", (str(database),))
            try:
                marks = ", ".join("?" * len(chain))
                with db:
                    for table in RUN_TABLES:
                        db.execute(
                            f"INSERT INTO archive.{table} SELECT * FROM main.{table}"
                            f" WHERE run_id IN ({marks}) ORDER BY rowid",
                            chain,
                        )
            finally:
                db.execute("DETACH DATABASE archive")
        with database.open("rb") as raw, gzip.open(out, "wb", compresslevel=6) as packed:
            shutil.copyfileobj(raw, packed, 1 << 20)
        return chain
    finally:
        database.unlink(missing_ok=True)


def import_into(store: RunHistoryStore, archive: Path) -> ImportReport:
    """Add every run in `archive` that `store` does not hold yet."""
    database = _temporary(store.path.parent, ".surmaprun-db")
    try:
        try:
            with gzip.open(archive, "rb") as packed, database.open("wb") as raw:
                shutil.copyfileobj(packed, raw, 1 << 20)
        except (OSError, EOFError, zlib.error) as exc:
            raise NotARunArchive(f"{archive} is not a {SUFFIX} file: {exc}") from exc
        try:
            with closing(sqlite3.connect(database)) as check:
                info = check.execute("SELECT format_version FROM export_info").fetchone()
                runs = [
                    str(row[0])
                    for row in check.execute("SELECT run_id FROM runs ORDER BY created_at")
                ]
        except sqlite3.DatabaseError as exc:
            raise NotARunArchive(f"{archive} is not a {SUFFIX} file: {exc}") from exc
        if info is None or int(info[0]) != FORMAT_VERSION:
            raise NotARunArchive(f"{archive} is not a version-{FORMAT_VERSION} {SUFFIX} file")
        report = ImportReport()
        with store.exclusive() as db:
            db.execute("ATTACH DATABASE ? AS archive", (str(database),))
            try:
                with db:
                    for run_id in runs:
                        held = db.execute("SELECT 1 FROM main.runs WHERE run_id = ?", (run_id,))
                        if held.fetchone() is not None:
                            report.skipped.append(run_id)
                            continue
                        for table in RUN_TABLES:
                            columns = _columns(db, table, "archive")
                            db.execute(
                                f"INSERT INTO main.{table} ({columns}) SELECT {columns}"
                                f" FROM archive.{table} WHERE run_id = ? ORDER BY rowid",
                                (run_id,),
                            )
                        report.imported.append(run_id)
            finally:
                db.execute("DETACH DATABASE archive")
        return report
    finally:
        database.unlink(missing_ok=True)


def export_run(history_db: Path, run_id: str, out: Path) -> list[str]:
    """`export_from` the history at `history_db`."""
    store = RunHistoryStore(history_db)
    try:
        return export_from(store, run_id, out)
    finally:
        store.close()


def import_runs(history_db: Path, archive: Path) -> ImportReport:
    """`import_into` the history at `history_db`."""
    store = RunHistoryStore(history_db)
    try:
        return import_into(store, archive)
    finally:
        store.close()


def main(argv: Sequence[str] | None = None) -> int:
    history = argparse.ArgumentParser(add_help=False)
    history.add_argument(
        "--history-db",
        type=Path,
        default=default_cache_dir() / "demo-history.db",
        help="the dev console's run history (default: %(default)s)",
    )
    parser = argparse.ArgumentParser(
        prog="python -m surmap.demo.run_archive",
        description="Export a dev-console run to a .surmaprun file, or import one.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser(
        "export", parents=[history], help="export a run and its replay lineage"
    )
    export.add_argument("run_id")
    export.add_argument("file", type=Path)
    imported = commands.add_parser("import", parents=[history], help="import a .surmaprun file")
    imported.add_argument("file", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "export":
            chain = export_run(args.history_db, args.run_id, args.file)
            size = args.file.stat().st_size / 1e6
            print(f"exported {', '.join(chain)} to {args.file} ({size:.1f} MB)")
        else:
            report = import_runs(args.history_db, args.file)
            for run_id in report.imported:
                print(f"imported {run_id}")
            for run_id in report.skipped:
                print(f"skipped {run_id} (already in {args.history_db})")
    except (RunNotExportable, NotARunArchive) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
