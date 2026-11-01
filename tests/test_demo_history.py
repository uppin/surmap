"""Generic test console: runs persisted to SQLite, history scrub, 3D cloud pane."""

import base64
import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

from surmap.demo.history import RunHistoryStore
from surmap.demo.server import DemoPlayer, make_demo_server
from tests.test_demo import FakeLiveBackend, _odom_with, _prepared_tiny

JPEG = b"\xff\xd8fake-jpeg\xff\xd9"


def a_store(tmp_path: Path) -> RunHistoryStore:
    return RunHistoryStore(tmp_path / "history.db")


def test_a_persisted_run_returns_the_cloud_as_it_was_at_each_frame(tmp_path: Path) -> None:
    # Given a run whose cloud grew between its two frames
    store = a_store(tmp_path)
    run_id = store.create_run("tiny-test", "Tiny Test", total_frames=2)
    store.record_frame(
        run_id,
        index=0,
        frame_id=1,
        t_ns=100,
        jpeg=JPEG,
        overlay=[{"x": 10.0, "y": 20.0, "d": 1.0, "c": "#ff5a3c"}],
        camera={"x": 0.0, "z": 0.0, "dx": 0.0, "dz": 1.0, "fov_deg": 78.8},
    )
    store.record_map(
        run_id,
        frame_id=1,
        points=[[1.0, 2.0, 5.0]],
        colors=[[10, 20, 30]],
        trajectory_xy=[[0.0, 0.0]],
        extent=[0.0, 1.0, 0.0, 5.0],
        cloud_points=1,
        keyframes=1,
        odom_state="tracking",
    )
    store.record_frame(run_id, index=1, frame_id=2, t_ns=200, jpeg=JPEG, overlay=[], camera=None)
    store.record_map(
        run_id,
        frame_id=2,
        points=[[1.0, 2.0, 5.0], [3.0, 4.0, 6.0]],
        colors=[[10, 20, 30], [40, 50, 60]],
        trajectory_xy=[[0.0, 0.0], [0.5, 2.0]],
        extent=[0.0, 3.0, 0.0, 6.0],
        cloud_points=2,
        keyframes=2,
        odom_state="tracking",
    )
    store.finish_run(run_id)

    # When the history is rewound to the first frame, then wound forward
    first = store.snapshot_at(run_id, 0)
    second = store.snapshot_at(run_id, 1)

    # Then each moment shows its own frame, overlay points and cloud
    assert first is not None and second is not None
    assert base64.b64decode(str(first["image_b64"])) == JPEG
    assert first["overlay"] == [{"x": 10.0, "y": 20.0, "d": 1.0, "c": "#ff5a3c"}]
    first_cloud = first["cloud"]
    second_cloud = second["cloud"]
    assert isinstance(first_cloud, dict) and isinstance(second_cloud, dict)
    assert first_cloud["points"] == [[1.0, 2.0, 5.0]]
    assert second_cloud["points"] == [[1.0, 2.0, 5.0], [3.0, 4.0, 6.0]]
    assert second_cloud["colors"] == [[10, 20, 30], [40, 50, 60]]


def test_rewinding_before_any_map_shows_no_cloud_and_unknown_seq_is_none(
    tmp_path: Path,
) -> None:
    # Given a run with one frame and no map yet
    store = a_store(tmp_path)
    run_id = store.create_run("tiny-test", "Tiny Test", total_frames=1)
    store.record_frame(run_id, index=0, frame_id=1, t_ns=100, jpeg=JPEG, overlay=[], camera=None)

    # When its only moment is read, and one past the end
    snapshot = store.snapshot_at(run_id, 0)

    # Then the frame is there with no cloud, and the unknown moment is None
    assert snapshot is not None and snapshot["cloud"] is None
    assert store.snapshot_at(run_id, 99) is None
    assert store.snapshot_at("no-such-run", 0) is None


def test_runs_survive_reopening_the_database_and_are_listed(tmp_path: Path) -> None:
    # Given a finished run in a database file
    store = a_store(tmp_path)
    run_id = store.create_run("tiny-test", "Tiny Test", total_frames=2)
    store.record_frame(run_id, index=0, frame_id=1, t_ns=100, jpeg=JPEG, overlay=[], camera=None)
    store.finish_run(run_id)

    # When the database is reopened
    reopened = a_store(tmp_path)
    runs = reopened.list_runs()

    # Then the run is listed with its persisted frame count and status
    assert len(runs) == 1
    assert runs[0]["run_id"] == run_id
    assert runs[0]["dataset_id"] == "tiny-test"
    assert runs[0]["status"] == "completed"
    assert runs[0]["frame_count"] == 1
    timeline = reopened.timeline(run_id)
    assert [entry["frame_id"] for entry in timeline] == [1]


def test_map_events_carry_sampled_cloud_points_for_the_3d_view(tmp_path: Path) -> None:
    # Given a live backend with a two-point coloured cloud
    fake = FakeLiveBackend(
        cloud=[((1.0, 2.0, 5.0), (10, 20, 30)), ((3.0, 4.0, 6.0), (40, 50, 60))],
        odometry={1: _odom_with(), 2: _odom_with()},
    )
    player = DemoPlayer(_prepared_tiny(tmp_path), fps=1000.0, backend_factory=lambda: fake)

    # When playback runs
    events = list(player.events())

    # Then map and final events carry the raw points the browser draws in 3D
    map_event = next(event for event in events if event.kind == "map")
    assert map_event.data["points"] == [[1.0, 2.0, 5.0], [3.0, 4.0, 6.0]]
    assert map_event.data["point_colors"] == [[10, 20, 30], [40, 50, 60]]
    final = events[-1]
    assert final.kind == "final"
    assert final.data["points"] == [[1.0, 2.0, 5.0], [3.0, 4.0, 6.0]]


def get_json(url: str) -> dict[str, object]:
    with urllib.request.urlopen(url, timeout=10) as response:
        loaded: dict[str, object] = json.loads(response.read())
        return loaded


def status_of(url: str) -> int:
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            return int(response.status)
    except urllib.error.HTTPError as error:
        return int(error.code)


def test_the_server_persists_a_streamed_run_and_serves_it_back_for_scrubbing(
    tmp_path: Path,
) -> None:
    # Given the test console serving a two-frame scene
    prepared = _prepared_tiny(tmp_path)
    history_db = tmp_path / "history.db"
    server = make_demo_server(
        prepared, host="127.0.0.1", port=0, with_rtabmap=False, history_db=history_db
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = str(server.server_address[0]), int(server.server_address[1])
    base = f"http://{host}:{port}"
    try:
        # When a viewer plays the scene to the end
        with urllib.request.urlopen(f"{base}/stream", timeout=10) as response:
            body = response.read().decode()

        # Then the stream announced its persisted run, and the run is listed
        assert "event: run" in body
        runs = get_json(f"{base}/runs")["runs"]
        assert isinstance(runs, list) and len(runs) == 1
        run = runs[0]
        assert isinstance(run, dict)
        assert run["dataset_id"] == "tiny-test" and run["frame_count"] == 2
        run_id = str(run["run_id"])

        # When the run is rewound to its first frame over HTTP
        snapshot = get_json(f"{base}/runs/{run_id}/snapshot?seq=0")

        # Then that moment's image and overlay come back, ready to display
        assert snapshot["frame_id"] == 1
        assert base64.b64decode(str(snapshot["image_b64"]))
        detail = get_json(f"{base}/runs/{run_id}")
        timeline = detail["timeline"]
        assert isinstance(timeline, list) and [t["frame_id"] for t in timeline] == [1, 2]
        assert status_of(f"{base}/runs/nope/snapshot?seq=0") == 404
        assert status_of(f"{base}/runs/{run_id}/snapshot?seq=99") == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_the_test_console_page_offers_history_and_ptz_cloud_controls(tmp_path: Path) -> None:
    # Given the test console page for a scene
    prepared = _prepared_tiny(tmp_path)
    server = make_demo_server(
        prepared,
        host="127.0.0.1",
        port=0,
        with_rtabmap=False,
        history_db=tmp_path / "history.db",
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = str(server.server_address[0]), int(server.server_address[1])
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/", timeout=5) as response:
            page = response.read().decode()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    # Then it is a generic test console with a scrub timeline, a runs
    # picker, and a resizable, fullscreenable point cloud with PTZ controls
    assert "SurMap Test Console" in page
    assert 'id="history-slider"' in page
    assert 'id="history-back"' in page and 'id="history-forward"' in page
    assert 'id="history-live"' in page and 'id="run-select"' in page
    assert 'id="cloud"' in page and 'id="cloud-fullscreen"' in page
    assert 'id="cloud-reset"' in page
    for control in ("pan-left", "pan-right", "tilt-up", "tilt-down", "zoom-in", "zoom-out"):
        assert f'data-ptz="{control}"' in page
    assert "cloud-pane" in page and "resize" in page
