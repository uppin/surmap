"""Demo runs export to one `.surmaprun` file and import into any console's history."""

import gzip
import json
import sqlite3
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from surmap.demo.history import RunHistoryStore
from surmap.demo.replay import JournalPlayer
from surmap.demo.run_archive import (
    ImportReport,
    NotARunArchive,
    RunNotExportable,
    export_run,
    import_runs,
)
from tests.test_demo_replay import Console, a_console, a_recorded_run, kinds

# Every table a run's rows live in, and the columns that make a row (ids left out:
# AUTOINCREMENT ids are renumbered on import, in the same order).
RUN_TABLES = {
    "runs": "dataset_id, title, total_frames, status, created_at, finished_at",
    "frames": "seq, frame_id, t_ns, jpeg, overlay, camera",
    "maps": "frame_id, points, colors, trajectory_xy, extent, cloud_points, keyframes, odom_state",
    "detections": "frame_id, t_ns, objects",
    "surface_points": "frame_id, surface_id, label, track_id, moving, points",
    "events": "kind, data",
    "run_rigs": "rig",
    "dense_frames": "frame_id, channel, t_ns, to_map, disparity_png",
    "run_sources": "source_run_id",
}
ORDER = {"frames": "seq", "dense_frames": "frame_id, channel"}


def rows_of(db: Path, run_id: str) -> dict[str, list[tuple[object, ...]]]:
    """A run's rows in every table, in their stored order."""
    with sqlite3.connect(db) as connection:
        return {
            table: connection.execute(
                f"SELECT {columns} FROM {table} WHERE run_id = ?"
                f" ORDER BY {ORDER.get(table, 'rowid')}",
                (run_id,),
            ).fetchall()
            for table, columns in RUN_TABLES.items()
        }


def replayed(db: Path, run_id: str) -> list[str]:
    """The kinds of event a replay of `run_id` from the history at `db` plays."""
    return [event.kind for event in JournalPlayer(RunHistoryStore(db), run_id).events()]


def an_empty_store(tmp_path: Path, name: str) -> Path:
    path = tmp_path / name / "history.db"
    RunHistoryStore(path).close()
    return path


def a_replay_of(console: Console, run_id: str) -> str:
    events = console.stream(f"?replay={run_id}&speed=0")
    return str(kinds(events, "run")[0]["run_id"])


def test_an_exported_run_imports_into_another_history_unchanged(tmp_path: Path) -> None:
    # Given a recorded run: frames, journal, map updates, surfaces, rig and dense buffer
    with a_console(tmp_path) as console:
        run_id = a_recorded_run(console)
    source = tmp_path / "history.db"

    # When it is exported, then imported into an empty history
    archive = tmp_path / "run.surmaprun"
    export_run(source, run_id, archive)
    target = an_empty_store(tmp_path, "elsewhere")
    report = import_runs(target, archive)

    # Then the other history holds the run, row for row, in the same order
    assert report == ImportReport(imported=[run_id], skipped=[])
    original, imported = rows_of(source, run_id), rows_of(target, run_id)
    assert {table: len(rows) for table, rows in imported.items() if rows} == {
        table: len(rows) for table, rows in original.items() if rows
    }
    assert imported == original


def test_an_imported_run_replays_like_the_original(tmp_path: Path) -> None:
    # Given a recorded run imported into another history
    with a_console(tmp_path) as console:
        run_id = a_recorded_run(console)
    archive = tmp_path / "run.surmaprun"
    export_run(tmp_path / "history.db", run_id, archive)
    target = an_empty_store(tmp_path, "elsewhere")
    import_runs(target, archive)

    # When both are replayed
    imported, original = replayed(target, run_id), replayed(tmp_path / "history.db", run_id)

    # Then they play the same events, surfaces from the imported dense buffer included
    assert imported == original
    assert "surface" in imported


def test_exporting_a_replay_brings_the_run_it_replays(tmp_path: Path) -> None:
    # Given a replay of a recorded run
    with a_console(tmp_path) as console:
        run_id = a_recorded_run(console)
        replay_id = a_replay_of(console, run_id)

    # When the replay is exported and imported elsewhere
    archive = tmp_path / "replay.surmaprun"
    exported = export_run(tmp_path / "history.db", replay_id, archive)
    target = an_empty_store(tmp_path, "elsewhere")
    report = import_runs(target, archive)

    # Then its source came along, and the imported replay still finds it
    assert exported == [replay_id, run_id]
    assert sorted(report.imported) == sorted([replay_id, run_id])
    assert RunHistoryStore(target).root_run(replay_id) == run_id


def test_importing_a_run_already_present_skips_it(tmp_path: Path) -> None:
    # Given a run already imported once
    with a_console(tmp_path) as console:
        run_id = a_recorded_run(console)
    archive = tmp_path / "run.surmaprun"
    export_run(tmp_path / "history.db", run_id, archive)
    target = an_empty_store(tmp_path, "elsewhere")
    import_runs(target, archive)
    before = rows_of(target, run_id)

    # When the same file is imported again
    report = import_runs(target, archive)

    # Then nothing is added
    assert report == ImportReport(imported=[], skipped=[run_id])
    assert rows_of(target, run_id) == before


def test_an_archive_is_compressed(tmp_path: Path) -> None:
    # Given a recorded run's export
    with a_console(tmp_path) as console:
        run_id = a_recorded_run(console)
    archive = tmp_path / "run.surmaprun"
    export_run(tmp_path / "history.db", run_id, archive)

    # Then it is gzip, holding a SQLite database
    assert archive.read_bytes()[:2] == b"\x1f\x8b"
    assert gzip.decompress(archive.read_bytes())[:16] == b"SQLite format 3\x00"


@pytest.mark.parametrize(
    "content",
    [b"not an archive at all", gzip.compress(b"still not a database")],
    ids=["plain bytes", "gzip of something else"],
)
def test_a_file_that_is_not_a_run_export_is_refused(tmp_path: Path, content: bytes) -> None:
    archive = tmp_path / "bogus.surmaprun"
    archive.write_bytes(content)
    with pytest.raises(NotARunArchive):
        import_runs(an_empty_store(tmp_path, "elsewhere"), archive)


def test_a_database_without_export_info_is_refused(tmp_path: Path) -> None:
    # Given a whole history database, gzipped, rather than an export
    with a_console(tmp_path) as console:
        a_recorded_run(console)
    archive = tmp_path / "history.surmaprun"
    archive.write_bytes(gzip.compress((tmp_path / "history.db").read_bytes()))

    # Then importing it is refused: it does not say what it holds
    with pytest.raises(NotARunArchive):
        import_runs(an_empty_store(tmp_path, "elsewhere"), archive)


def test_a_run_still_recording_cannot_be_exported(tmp_path: Path) -> None:
    store_path = tmp_path / "history.db"
    store = RunHistoryStore(store_path)
    run_id = store.create_run("tiny-test", "Tiny")
    store.close()
    with pytest.raises(RunNotExportable):
        export_run(store_path, run_id, tmp_path / "run.surmaprun")


def test_an_unknown_run_cannot_be_exported(tmp_path: Path) -> None:
    store_path = an_empty_store(tmp_path, "here")
    with pytest.raises(RunNotExportable):
        export_run(store_path, "no-such-run", tmp_path / "run.surmaprun")


def download(url: str) -> tuple[int, dict[str, str], bytes]:
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            return int(response.status), dict(response.headers), response.read()
    except urllib.error.HTTPError as error:
        return int(error.code), dict(error.headers), b""


def upload(url: str, content: bytes) -> tuple[int, dict[str, object]]:
    request = urllib.request.Request(
        url, data=content, headers={"Content-Type": "application/octet-stream"}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return int(response.status), json.loads(response.read())
    except urllib.error.HTTPError as error:
        return int(error.code), {}


def test_a_console_exports_a_run_as_a_named_download(tmp_path: Path) -> None:
    # Given a console with a recorded run
    with a_console(tmp_path) as console:
        run_id = a_recorded_run(console)

        # When the run is exported over HTTP
        status, headers, body = download(f"{console.base}/runs/{run_id}/export")

    # Then it downloads as a .surmaprun attachment named for its scene and run
    assert status == 200
    assert headers["Content-Disposition"] == (
        f'attachment; filename="surmap-tiny-test-{run_id[:8]}.surmaprun"'
    )
    assert body[:2] == b"\x1f\x8b"


def test_another_console_imports_an_uploaded_run(tmp_path: Path) -> None:
    # Given a run exported from one console
    with a_console(tmp_path / "here") as console:
        run_id = a_recorded_run(console)
        body = download(f"{console.base}/runs/{run_id}/export")[2]

    # When it is uploaded to another console
    with a_console(tmp_path / "there") as other:
        status, answer = upload(f"{other.base}/runs/import", body)
        listed = [run["run_id"] for run in other.runs()]

    # Then that console imported it and lists it
    assert (status, answer) == (200, {"imported": [run_id], "skipped": []})
    assert run_id in listed


def test_exporting_an_unknown_run_is_not_found(tmp_path: Path) -> None:
    with a_console(tmp_path) as console:
        assert download(f"{console.base}/runs/no-such-run/export")[0] == 404


def test_uploading_something_else_is_a_bad_request(tmp_path: Path) -> None:
    with a_console(tmp_path) as console:
        assert upload(f"{console.base}/runs/import", b"not an archive")[0] == 400


def test_the_page_offers_export_and_import(tmp_path: Path) -> None:
    with a_console(tmp_path) as console:
        with urllib.request.urlopen(f"{console.base}/", timeout=5) as response:
            page = response.read().decode()
    assert 'id="run-export"' in page and 'id="run-import"' in page
    assert 'accept=".surmaprun"' in page
    assert "/export" in page and "'/runs/import'" in page


def test_the_cli_exports_and_imports_a_run(tmp_path: Path) -> None:
    # Given a recorded run
    with a_console(tmp_path) as console:
        run_id = a_recorded_run(console)
    archive = tmp_path / "cli.surmaprun"
    target = tmp_path / "elsewhere" / "history.db"

    # When the CLI exports it, then imports it into another history
    exported = subprocess.run(
        [
            sys.executable,
            "-m",
            "surmap.demo.run_archive",
            "export",
            run_id,
            str(archive),
            "--history-db",
            str(tmp_path / "history.db"),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    imported = subprocess.run(
        [
            sys.executable,
            "-m",
            "surmap.demo.run_archive",
            "import",
            str(archive),
            "--history-db",
            str(target),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )

    # Then both succeed and say what they did
    assert exported.returncode == 0, exported.stderr
    assert imported.returncode == 0, imported.stderr
    assert run_id in exported.stdout and str(archive) in exported.stdout
    assert f"imported {run_id}" in imported.stdout
    assert rows_of(target, run_id) == rows_of(tmp_path / "history.db", run_id)
