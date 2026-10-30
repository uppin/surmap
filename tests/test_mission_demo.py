"""Disaster-mission orchestration. No network and no Gazebo.

Live-map tests stand in for ``StreamingRtabmapBackend`` at the opener
seam. They do not start Docker.
"""

import json
import urllib.request
from collections.abc import Callable
from pathlib import Path

import pytest

from surmap.labelling.baseten_muse import BasetenMuseLabelClient, ObjectLabel
from surmap.labelling.meta_muse import MetaMuseSceneClient
from surmap.mission.demo import (
    MissionConfigError,
    live_map_backend,
    open_live_map,
    resolve_live_session,
    run_live_mission,
    run_offline_mission,
)
from surmap.mission.metrics import load_offline_perception
from surmap.simulation.calibration import StereoCalibrationSpec
from surmap.simulation.disaster_world import PersonGroundTruth, load_disaster_ground_truth
from surmap.slam.base import FrameResult
from surmap.survey.meta_sam import MetaSamDetector
from surmap.survey.sam import RawFrame, SamDetection
from surmap.types import Pose, StereoFramePair, Vec3
from surmap.viewer.server import make_viewer_server

_CAPTURE = Path(__file__).parent / "fixtures" / "sitl_capture_tiny"
_MAP_POINT = Vec3(0.0, 0.0, 2.0)

_QUESTION = "Where are the survivors?"


def test_offline_mission_projects_fixture_masks_and_scores_them_against_ground_truth(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given the disaster ground truth and a fixture perception spec
    _block_network(monkeypatch)
    truth = load_disaster_ground_truth()
    spec = load_offline_perception()

    # When the offline mission runs
    result = run_offline_mission(tmp_path)

    # Then masks were projected, the snapshot was written, and the score
    # uses the people array rather than a fixed count
    assert result.metrics.basis == "fixtures"
    assert result.metrics.total == len(truth.people)
    assert result.metrics.found == len(truth.people) - _skipped(truth.people, spec.skip_ids)
    assert result.metrics.mean_position_error_m == pytest.approx(spec.expected_error_m)
    assert result.metrics.time_to_first_detection_s == pytest.approx(spec.time_to_first_s)
    assert result.snapshot_path.is_file()
    assert result.report_path.is_file()
    assert (tmp_path / "euroc" / "mav0" / "cam0" / "sensor.yaml").is_file()
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert report["basis"] == "fixtures"
    assert report["total"] == len(truth.people)
    assert "fixture" in report["basis_note"].lower()


def test_offline_mission_answers_where_are_the_survivors_with_highlighted_points(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given an offline mission whose labels say survivor
    _block_network(monkeypatch)

    # When a responder asks where the survivors are
    result = run_offline_mission(tmp_path)

    # Then the answer cites those landmarks and returns their points
    assert result.ask.question == _QUESTION
    assert result.ask.landmark_ids
    assert len(result.ask.landmark_ids) == result.metrics.found
    assert result.ask.highlight_points
    assert "secret" not in result.ask.answer


def test_offline_mission_ignores_live_flags_and_does_not_open_the_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given live flags and a key that must not be logged
    _block_network(monkeypatch)
    monkeypatch.setenv("SURMAP_LIVE_META", "1")
    monkeypatch.setenv("SURMAP_LIVE_BASETEN", "1")
    monkeypatch.setenv("SURMAP_LIVE_MODAL", "1")
    monkeypatch.setenv("MODEL_API_KEY", "secret-model-key")
    monkeypatch.setenv("BASETEN_API_KEY", "secret-baseten-key")

    # When the offline mission runs
    result = run_offline_mission(tmp_path)
    text = result.report_path.read_text(encoding="utf-8")

    # Then the report stays on fixtures and the keys are absent
    assert result.metrics.basis == "fixtures"
    assert result.map_backend == "fixture-cloud"
    assert "secret-model-key" not in text
    assert "secret-baseten-key" not in text


def test_live_mode_without_a_capture_asks_for_a_sitl_capture_when_gazebo_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given no gz binary
    monkeypatch.setattr("surmap.mission.demo.gazebo_on_path", lambda: False)

    # When a live session is requested without a capture directory
    with pytest.raises(MissionConfigError, match="--capture") as raised:
        resolve_live_session(None)

    # Then the message names a SITL capture directory. That directory is
    # the dump layout, not an EuRoC tree.
    message = str(raised.value)
    assert "capture" in message
    assert "EuRoC" not in message


def test_live_mission_names_a_missing_capture_before_it_asks_for_provider_flags(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given no provider flags and a capture path that is not on disk
    monkeypatch.delenv("SURMAP_LIVE_META", raising=False)
    monkeypatch.delenv("SURMAP_LIVE_BASETEN", raising=False)
    monkeypatch.delenv("SURMAP_LIVE_MODAL", raising=False)

    # When the live mission is asked to run
    with pytest.raises(MissionConfigError, match="capture not found") as raised:
        run_live_mission(tmp_path, tmp_path / "missing-capture")

    # Then the missing directory is the error, and no provider is mentioned
    assert "SURMAP_LIVE" not in str(raised.value)


def test_live_mission_names_an_incomplete_capture_before_it_asks_for_provider_flags(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given no provider flags and a capture directory with no calibration file
    monkeypatch.delenv("SURMAP_LIVE_META", raising=False)
    monkeypatch.delenv("SURMAP_LIVE_BASETEN", raising=False)
    monkeypatch.delenv("SURMAP_LIVE_MODAL", raising=False)
    empty = tmp_path / "empty-capture"
    empty.mkdir()

    # When the live mission is asked to run
    with pytest.raises(MissionConfigError, match="calibration.json") as raised:
        run_live_mission(tmp_path / "out", empty)

    # Then the incomplete capture is the error, and no provider is mentioned
    assert "SURMAP_LIVE" not in str(raised.value)


def test_live_services_refuse_a_provider_whose_flag_is_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given no live provider flags
    monkeypatch.delenv("SURMAP_LIVE_META", raising=False)
    monkeypatch.delenv("SURMAP_LIVE_BASETEN", raising=False)
    monkeypatch.delenv("SURMAP_LIVE_MODAL", raising=False)

    # When live services are built
    from surmap.mission.demo import build_live_services

    with pytest.raises(MissionConfigError, match="SURMAP_LIVE_META"):
        build_live_services()


def test_live_map_backend_names_the_streaming_rtabmap_backend() -> None:
    # Given PR #38's streaming backend is in this tree
    backend = live_map_backend()

    # Then live mode names that backend, not the old pending hook
    assert backend == "live-rtabmap"


def test_offline_mission_does_not_open_the_streaming_backend(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given a streaming constructor that must not run
    def refuse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("offline mission opened the streaming backend")

    monkeypatch.setattr("surmap.slam.streaming.StreamingRtabmapBackend", refuse)
    _block_network(monkeypatch)

    # When the offline mission runs
    result = run_offline_mission(tmp_path)

    # Then the report stays on the fixture cloud
    assert result.metrics.basis == "fixtures"
    assert result.map_backend == "fixture-cloud"


def test_open_live_map_builds_the_streaming_backend_from_the_capture_calibration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given the disaster-block stereo calibration and a constructor that records its arguments
    calibration = StereoCalibrationSpec(
        calibration_id="gazebo-stereo-v1",
        width=64,
        height=48,
        fx=50.0,
        fy=50.0,
        cx=32.0,
        cy=24.0,
        baseline_m=0.12,
    )
    captured: dict[str, object] = {}

    class RecordingBackend:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

    monkeypatch.setattr("surmap.slam.streaming.StreamingRtabmapBackend", RecordingBackend)

    # When the live map is opened
    backend = open_live_map(calibration)

    # Then it is the streaming backend, sized and calibrated from that capture
    assert isinstance(backend, RecordingBackend)
    assert captured["width"] == 64
    assert captured["height"] == 48
    cam0 = captured["cam0_yaml"]
    cam1 = captured["cam1_yaml"]
    assert isinstance(cam0, str)
    assert isinstance(cam1, str)
    assert "intrinsics: [50.0, 50.0, 32.0, 24.0]" in cam0
    assert "intrinsics: [50.0, 50.0, 32.0, 24.0]" in cam1


def test_live_mission_projects_the_streaming_snapshot_into_the_map(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given a capture and a streaming map whose snapshot is one point in front of the camera
    _allow_live_flags(monkeypatch)
    _block_network(monkeypatch)
    recording = _RecordingMap(snapshot=(_MAP_POINT,))
    labelled: list[Vec3] = []
    monkeypatch.setattr("surmap.mission.demo.open_live_map", lambda _calibration: recording)
    monkeypatch.setattr(MetaSamDetector, "detect", _detect_person)
    monkeypatch.setattr(BasetenMuseLabelClient, "label", _remembering_label(labelled))
    monkeypatch.setattr(MetaMuseSceneClient, "note", _scene_note)

    # When the live mission runs
    result = run_live_mission(tmp_path, _CAPTURE)
    text = result.report_path.read_text(encoding="utf-8")

    # Then every capture frame was given to that map, and the claimed point is its snapshot
    assert [frame.frame_id for frame in recording.frames] == [0, 1]
    assert recording.closed
    assert labelled
    assert labelled[0].x == pytest.approx(_MAP_POINT.x)
    assert labelled[0].y == pytest.approx(_MAP_POINT.y)
    assert labelled[0].z == pytest.approx(_MAP_POINT.z)
    assert result.metrics.basis == "live"
    assert result.map_backend == "live-rtabmap"
    assert "pending-pr-38" not in text
    assert "PR #38 is not merged" not in text
    assert "secret-model-key" not in text
    assert "secret-baseten-key" not in text


def test_live_mission_says_when_the_streaming_backend_returns_no_points(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given a streaming map that finishes with an empty snapshot
    _allow_live_flags(monkeypatch)
    _block_network(monkeypatch)
    recording = _RecordingMap(snapshot=())

    async def refuse_detect(self: object, frame: RawFrame) -> tuple[SamDetection, ...]:
        del self, frame
        raise AssertionError("live mission called SAM with no map cloud")

    monkeypatch.setattr("surmap.mission.demo.open_live_map", lambda _calibration: recording)
    monkeypatch.setattr(MetaSamDetector, "detect", refuse_detect)
    monkeypatch.setattr(MetaMuseSceneClient, "note", _scene_note)

    # When the live mission runs
    result = run_live_mission(tmp_path, _CAPTURE)
    report = json.loads(result.report_path.read_text(encoding="utf-8"))

    # Then the report names the streaming backend and says positions were not estimated
    assert recording.closed
    assert result.map_backend == "live-rtabmap"
    assert result.metrics.basis == "live"
    assert report["map_backend"] == "live-rtabmap"
    assert "not estimated" in str(report["basis_note"]).lower()
    assert "secret-model-key" not in json.dumps(report)


def test_a_busy_viewer_port_is_named_without_a_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Given the offline report is ready and the viewer port is already taken
    import importlib.util
    import socket
    from typing import cast

    script = Path(__file__).resolve().parents[1] / "scripts" / "mission_demo.py"
    spec = importlib.util.spec_from_file_location("mission_demo_cli", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    main = cast(Callable[[list[str]], int], module.main)
    held = socket.socket()
    held.bind(("127.0.0.1", 0))
    held.listen(1)
    port = int(held.getsockname()[1])

    try:
        # When the demo tries to serve on that port
        code = main(["--output", str(tmp_path), "--port", str(port)])
    finally:
        held.close()
    captured = capsys.readouterr()

    # Then it exits with a message that names the port and does not dump a traceback
    assert code == 1
    assert str(port) in captured.err
    assert "Traceback" not in captured.err


def test_viewer_serves_the_impact_report_and_the_survivor_question(tmp_path: Path) -> None:
    # Given a mission report and its snapshot
    from surmap.mission.replay import MissionReplay

    result = run_offline_mission(tmp_path)
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    server = make_viewer_server(
        lambda: MissionReplay(result.snapshot_path),
        host="127.0.0.1",
        port=0,
        fps=200.0,
        impact=report,
    )
    server.timeout = 0.2
    thread_started = False
    import threading

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    thread_started = True
    try:
        host = str(server.server_address[0])
        port = int(server.server_address[1])
        base = f"http://{host}:{port}"

        # When the viewer is asked for the impact and the survivor question
        with urllib.request.urlopen(f"{base}/impact", timeout=2) as response:
            impact = json.loads(response.read().decode())
        body = json.dumps({"question": _QUESTION}).encode()
        ask_request = urllib.request.Request(
            f"{base}/ask",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(ask_request, timeout=2) as response:
            answer = json.loads(response.read().decode())
        with urllib.request.urlopen(f"{base}/", timeout=2) as response:
            page = response.read().decode()
    finally:
        if thread_started:
            server.shutdown()
            server.server_close()

    # Then the page can show the fixture metrics and the answer highlights points
    assert impact["basis"] == "fixtures"
    assert impact["total"] == result.metrics.total
    assert "impact" in page
    assert answer["landmark_ids"]
    assert answer["highlight_points"]


class _RecordingMap:
    """Stands in for ``StreamingRtabmapBackend``. Records frames and closes."""

    def __init__(self, snapshot: tuple[Vec3, ...]) -> None:
        self.frames: list[StereoFramePair] = []
        self.closed = False
        self._snapshot = snapshot

    def process_frame(self, frame: StereoFramePair) -> FrameResult:
        self.frames.append(frame)
        return FrameResult(frame.frame_id, frame.t_ns, None, ())

    def flush(self) -> list[FrameResult]:
        pose = Pose(Vec3(0.0, 0.0, 0.0))
        return [FrameResult(frame.frame_id, frame.t_ns, pose, ()) for frame in self.frames]

    def map_snapshot(self) -> tuple[Vec3, ...]:
        return self._snapshot

    def close(self) -> None:
        self.closed = True


def _allow_live_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SURMAP_LIVE_META", "1")
    monkeypatch.setenv("SURMAP_LIVE_BASETEN", "1")
    monkeypatch.delenv("SURMAP_LIVE_MODAL", raising=False)
    monkeypatch.setenv("MODEL_API_KEY", "secret-model-key")
    monkeypatch.setenv("BASETEN_API_KEY", "secret-baseten-key")


def _person_mask() -> SamDetection:
    return SamDetection(
        label="person",
        score=0.9,
        box_xyxy=(0.0, 0.0, 63.0, 47.0),
        mask_polygon=((0.0, 0.0), (63.0, 0.0), (63.0, 47.0), (0.0, 47.0)),
        track_id=None,
    )


async def _detect_person(self: object, frame: RawFrame) -> tuple[SamDetection, ...]:
    del self, frame
    return (_person_mask(),)


def _remembering_label(
    labelled: list[Vec3],
) -> Callable[[object, bytes, str, Vec3], ObjectLabel]:
    def label(self: object, jpeg: bytes, coarse_label: str, xyz: Vec3) -> ObjectLabel:
        del self, jpeg, coarse_label
        labelled.append(xyz)
        return ObjectLabel(
            label="survivor",
            description="survivor in the disaster block",
            confidence=None,
            model_id="test-double",
            raw_text="survivor",
            map_point=xyz,
        )

    return label


def _scene_note(self: object, labels: list[str], frame_jpeg: bytes) -> str:
    del self, labels, frame_jpeg
    return "Scene note from the test double. Not a provider call."


def _block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("offline mission opened the network")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)


def _skipped(people: tuple[PersonGroundTruth, ...], skip_ids: tuple[str, ...]) -> int:
    ids = {person.id for person in people}
    return sum(1 for person_id in skip_ids if person_id in ids)
