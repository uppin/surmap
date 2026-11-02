"""Run journal: every event in order plus RTAB-Map's dense buffer, persisted for replay."""

from pathlib import Path

import numpy as np

from surmap.demo.history import RunHistoryStore
from surmap.slam.dense import DenseFrame, encode_disparity
from surmap.types import Pose, Vec3

JPEG = b"\xff\xd8frame-7\xff\xd9"
RIG: dict[str, object] = {"rig": {"size": [376, 240], "baseline": 0.11}, "display_size": [376, 240]}


def a_store(tmp_path: Path) -> RunHistoryStore:
    return RunHistoryStore(tmp_path / "history.db")


def a_dense_frame(frame_id: int, channel: int = 0) -> DenseFrame:
    disparity = np.full((4, 6), 40 + frame_id, np.uint16)
    return DenseFrame(
        frame_id, frame_id * 1000, channel, Pose(Vec3(1.0, 2.0, 3.0)), encode_disparity(disparity)
    )


def test_the_journal_returns_every_event_in_the_order_it_was_recorded(tmp_path: Path) -> None:
    # Given a run that streamed a frame, a SAM result, a map update and a surface
    store = a_store(tmp_path)
    run_id = store.create_run("tiny-test", "Tiny")
    store.record_event(run_id, "frame", {"index": 0, "frame_id": 7})
    store.record_event(run_id, "sam", {"frame_id": 7, "objects": []})
    store.record_event(run_id, "map", {"frame_id": 7, "points": [[1.0, 2.0, 3.0]]})
    store.record_event(run_id, "surface", {"frame_id": 7, "surfaces": []})

    # When its journal is read back
    journal = store.journal(run_id)

    # Then the events come back in that order, data intact
    assert [kind for kind, _ in journal] == ["frame", "sam", "map", "surface"]
    assert journal[2][1]["points"] == [[1.0, 2.0, 3.0]]


def test_render_only_images_are_not_journalled(tmp_path: Path) -> None:
    # Given a map event carrying its server-rendered cloud view
    store = a_store(tmp_path)
    run_id = store.create_run("tiny-test", "Tiny")
    store.record_event(run_id, "map", {"frame_id": 7, "cloud_png": "iVBOR...", "keyframes": 2})

    # When its journal is read back
    (_, data) = store.journal(run_id)[0]

    # Then the view is gone (a replay re-renders it) and the rest is kept
    assert data == {"frame_id": 7, "keyframes": 2}


def test_a_frames_jpeg_is_found_by_its_frame_id(tmp_path: Path) -> None:
    # Given a run that showed frame 7 as its first frame
    store = a_store(tmp_path)
    run_id = store.create_run("tiny-test", "Tiny")
    store.record_frame(run_id, index=0, frame_id=7, t_ns=700, jpeg=JPEG, overlay=[], camera=None)

    # Then frame 7's image is there and a frame never shown is not
    assert store.frame_jpeg(run_id, 7) == JPEG
    assert store.frame_jpeg(run_id, 8) is None


def test_the_rig_and_the_dense_buffer_round_trip(tmp_path: Path) -> None:
    # Given a run that journalled its rig and the disparity of frames 3 and 4
    store = a_store(tmp_path)
    run_id = store.create_run("tiny-test", "Tiny")
    store.record_rig(run_id, RIG)
    store.record_dense(run_id, a_dense_frame(3))
    store.record_dense(run_id, a_dense_frame(4, channel=1))

    # Then both come back exactly as recorded
    assert store.rig(run_id) == RIG
    assert store.dense_frames(run_id) == [a_dense_frame(3), a_dense_frame(4, channel=1)]


def test_a_run_without_a_journal_is_not_replayable(tmp_path: Path) -> None:
    # Given a run with a journal and one recorded before journals existed
    store = a_store(tmp_path)
    journalled = store.create_run("tiny-test", "Tiny")
    store.record_event(journalled, "frame", {"index": 0, "frame_id": 1})
    legacy = store.create_run("tiny-test", "Tiny")

    # Then only the journalled one is offered for replay
    assert store.get_run(journalled) == {**_listed(store, journalled), "replayable": True}
    assert _listed(store, legacy)["replayable"] is False


def test_a_replay_knows_the_run_whose_dense_buffer_it_reads(tmp_path: Path) -> None:
    # Given a live run, a replay of it, and a replay of that replay
    store = a_store(tmp_path)
    live = store.create_run("tiny-test", "Tiny")
    replay = store.create_run("tiny-test", "Replay")
    store.record_source(replay, live)
    replay_of_replay = store.create_run("tiny-test", "Replay again")
    store.record_source(replay_of_replay, replay)

    # Then each names its source, and both lead back to the live run's journal
    assert _listed(store, replay)["replay_of"] == live
    assert _listed(store, live)["replay_of"] is None
    assert store.root_run(replay_of_replay) == live
    assert store.root_run(live) == live


def _listed(store: RunHistoryStore, run_id: str) -> dict[str, object]:
    return next(run for run in store.list_runs() if run["run_id"] == run_id)


def test_a_regions_points_are_journalled_as_a_count_since_the_dense_buffer_has_them(
    tmp_path: Path,
) -> None:
    # Given a live region event with its dense points
    store = a_store(tmp_path)
    run_id = store.create_run("tiny-test", "Tiny")
    placed = {"track_id": 1, "label": "car", "status": "ok", "points": [[1.0, 2.0, 3.0]] * 3}
    store.record_event(run_id, "region", {"frame_id": 7, "regions": [placed]})

    # When its journal is read back
    (_, data) = store.journal(run_id)[0]

    # Then the region is kept with how many points it had, not the points
    assert data == {
        "frame_id": 7,
        "regions": [{"track_id": 1, "label": "car", "status": "ok", "point_count": 3}],
    }
