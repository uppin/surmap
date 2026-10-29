"""Offline disaster-mission orchestration. No network and no Gazebo."""

import json
import urllib.request
from pathlib import Path

import pytest

from surmap.mission.demo import (
    MissionConfigError,
    live_map_backend,
    resolve_live_session,
    run_offline_mission,
)
from surmap.mission.metrics import load_offline_perception
from surmap.simulation.disaster_world import PersonGroundTruth, load_disaster_ground_truth
from surmap.viewer.server import make_viewer_server

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


def test_live_mode_without_a_capture_names_the_recorded_session_when_gazebo_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given no gz binary
    monkeypatch.setattr("surmap.mission.demo.gazebo_on_path", lambda: False)

    # When a live session is requested without a capture directory
    with pytest.raises(MissionConfigError, match="--capture"):
        resolve_live_session(None)


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


def test_live_map_hook_names_pr_38_until_the_streaming_backend_imports() -> None:
    # Given this branch does not carry the live RTAB-Map backend
    backend = live_map_backend()

    # Then the hook says the live map is waiting on that pull request
    assert backend == "pending-pr-38"


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


def _block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("offline mission opened the network")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)


def _skipped(people: tuple[PersonGroundTruth, ...], skip_ids: tuple[str, ...]) -> int:
    ids = {person.id for person in people}
    return sum(1 for person_id in skip_ids if person_id in ids)
