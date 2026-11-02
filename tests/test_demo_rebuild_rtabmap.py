"""Rebuild RTAB-Map only: a recorded run's SAM results, a fresh live RTAB-Map run."""

import urllib.request
from pathlib import Path

from surmap.demo.history import RunHistoryStore
from surmap.demo.sam_journal import JournalSamDetector
from surmap.survey.sam import RawFrame, SamDetection
from tests.test_demo_regions import MASK
from tests.test_demo_replay import a_console, a_recorded_run, kinds

CAR = SamDetection("car", 0.9, (10.0, 10.0, 60.0, 50.0), MASK, track_id=3)


def object_count(sam: dict[str, object]) -> int:
    objects = sam["objects"]
    assert isinstance(objects, list)
    return len(objects)


def a_frame(t_ns: int) -> RawFrame:
    return RawFrame(1, t_ns, 0, 376, 240, "mjpeg", b"")


def a_run_with_sam(store: RunHistoryStore, t_ns: int, detection: SamDetection) -> str:
    run_id = store.create_run("tiny-test", "Tiny Test · SAM: car")
    store.record_event(
        run_id,
        "sam",
        {
            "frame_id": 1,
            "t_ns": t_ns,
            "objects": [
                {
                    "label": detection.label,
                    "score": detection.score,
                    "track_id": detection.track_id,
                    "box": list(detection.box_xyxy),
                    "mask_polygon": [list(point) for point in detection.mask_polygon],
                }
            ],
        },
    )
    return run_id


def test_the_journal_detector_answers_each_frame_with_its_recorded_sam_result(
    tmp_path: Path,
) -> None:
    # Given a run whose SAM found one car on the frame at t_ns 1317042515215464704
    store = RunHistoryStore(tmp_path / "history.db")
    run_id = a_run_with_sam(store, 1317042515215464704, CAR)

    # When that frame and one SAM never saw are tracked
    detector = JournalSamDetector(store, run_id)
    detector.reset()
    seen = detector.track(a_frame(1317042515215464704))
    unseen = detector.track(a_frame(1317042515318964224))

    # Then the recorded frame gets the car, the other nothing
    assert seen == (CAR,)
    assert unseen == ()


def test_rebuilding_rtabmap_runs_it_live_again_without_running_sam(tmp_path: Path) -> None:
    with a_console(tmp_path) as console:
        # Given a run recorded live with RTAB-Map and SAM
        recorded = a_recorded_run(console)
        sam_calls = console.sam.tracked

        # When its RTAB-Map part is rebuilt
        events = console.stream(f"?rebuild_rtabmap={recorded}")

        # Then RTAB-Map ran again, SAM did not, and the recorded masks streamed again
        assert len(console.backends) == 2
        assert console.sam.tracked == sam_calls
        assert [object_count(sam) for sam in kinds(events, "sam")] == [1, 1]


def test_a_rebuilt_run_is_a_new_recording_with_its_own_dense_buffer(tmp_path: Path) -> None:
    with a_console(tmp_path) as console:
        # Given a recorded run
        recorded = a_recorded_run(console)

        # When its RTAB-Map part is rebuilt
        rebuilt = str(kinds(console.stream(f"?rebuild_rtabmap={recorded}"), "run")[0]["run_id"])

        # Then it is a new recording, not a replay, with RTAB-Map's fresh dense buffer
        run = next(run for run in console.runs() if run["run_id"] == rebuilt)
        assert run["replay_of"] is None and run["frame_count"] == 2
        assert console.store.dense_frame(rebuilt, 1) is not None
        # ... and it is now the scene's cached recording
        assert console.store.latest_recording("tiny-test") == rebuilt


def test_an_unknown_run_cannot_be_rebuilt(tmp_path: Path) -> None:
    with a_console(tmp_path) as console:
        assert console.status_of("/stream?rebuild_rtabmap=nope") == 404


def test_the_console_page_offers_to_rebuild_a_runs_rtabmap(tmp_path: Path) -> None:
    with a_console(tmp_path) as console:
        with urllib.request.urlopen(f"{console.base}/", timeout=5) as response:
            page = response.read().decode()

    assert 'id="run-rebuild-rtabmap"' in page
    assert "/stream?rebuild_rtabmap=" in page
