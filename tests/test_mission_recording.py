"""Record live model calls once and replay them offline. No network."""

import importlib.util
import json
import urllib.request
from collections.abc import Mapping
from pathlib import Path
from typing import Protocol, cast

import pytest

from surmap.mission import demo
from surmap.mission.demo import (
    default_recording_dir,
    replay_model_calls,
    run_live_mission,
    run_recorded_mission,
)
from surmap.mission.recording import (
    CALLS_FILE,
    MANIFEST_FILE,
    CallRecorder,
    RecordingError,
    load_recording,
    read_calls,
)
from surmap.slam.base import FrameResult
from surmap.types import Pose, StereoFramePair, Vec3

_CAPTURE = Path(__file__).parent / "fixtures" / "sitl_capture_tiny"
_KEY = "LLM|1234|secret-model-key"
_SAM_LINE = (
    "<0f>0<|box;x1=0;y1=0;x2=63;y2=47;w=64;h=48;c=0.8|>"
    "<|mask;x=0;y=0;c=0.8;data=5,5,!!!!!(QO(0lu8?|>"
)


def _responses_body(text: str) -> dict[str, object]:
    return {
        "status": "completed",
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": text}],
            }
        ],
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }


class _FakeMuse:
    """Stands in for HTTPS to the Meta Responses API (Muse Wonder)."""

    def __init__(self, timeout_s: float = 60.0) -> None:
        del timeout_s

    def post_json(
        self, url: str, headers: Mapping[str, str], body: Mapping[str, object]
    ) -> Mapping[str, object]:
        del url
        assert headers["Authorization"] == f"Bearer {_KEY}"
        prompt = json.dumps(body)
        if "segmentation model should outline" in prompt:
            assert "response_format" not in body
            text = body["text"]
            assert isinstance(text, dict)
            assert text["format"]["type"] == "json_schema"
            concepts = ["collapsed building", "person", "no people", "car on the left"]
            return _responses_body(json.dumps({"concepts": concepts}))
        if "segmenter noun" in prompt:
            return _responses_body("collapsed wall survivor")
        return _responses_body(f"Scene note quoting the key {_KEY} by mistake.")


class _FakeSam:
    """Stands in for HTTPS to the Meta Responses API (SAM 3.1)."""

    def __init__(self, timeout_s: float = 60.0) -> None:
        del timeout_s

    def post(
        self, url: str, headers: Mapping[str, str], payload: Mapping[str, object]
    ) -> Mapping[str, object]:
        del url, headers, payload
        return _responses_body(_SAM_LINE)


class _Map:
    def __init__(self) -> None:
        self.frames: list[StereoFramePair] = []

    def process_frame(self, frame: StereoFramePair) -> FrameResult:
        self.frames.append(frame)
        return FrameResult(frame.frame_id, frame.t_ns, None, ())

    def flush(self) -> list[FrameResult]:
        pose = Pose(Vec3(0.0, 0.0, 0.0))
        return [FrameResult(frame.frame_id, frame.t_ns, pose, ()) for frame in self.frames]

    def map_snapshot(self) -> tuple[Vec3, ...]:
        return (Vec3(0.0, 0.0, 2.0),)

    def close(self) -> None:
        return None


def _block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("opened the network")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)


def _live_meta(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SURMAP_LIVE_META", "1")
    monkeypatch.setenv("MODEL_API_KEY", _KEY)
    monkeypatch.delenv("SURMAP_LIVE_BASETEN", raising=False)
    monkeypatch.delenv("SURMAP_LIVE_MODAL", raising=False)
    monkeypatch.delenv("SURMAP_SAM_PROMPT", raising=False)
    monkeypatch.setattr(demo, "UrllibMetaMuseTransport", _FakeMuse)
    monkeypatch.setattr(demo, "UrllibMetaTransport", _FakeSam)
    monkeypatch.setattr(demo, "open_live_map", lambda _calibration, **_kwargs: _Map())


def _record(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    _live_meta(monkeypatch)
    _block_network(monkeypatch)
    recording = tmp_path / "recording"
    run_live_mission(tmp_path / "live", _CAPTURE, record_dir=recording)
    return recording


def test_the_recorder_drops_auth_headers_hashes_media_and_scrubs_keys() -> None:
    # Given a recorder that knows one key
    recorder = CallRecorder(clock=lambda: 0.0, secrets=["sk-very-secret"], private_urls=[])
    image = "data:image/jpeg;base64," + "A" * 2000

    # When a call with that key in a header and in the response is added
    call = recorder.add(
        role="label",
        provider="baseten",
        url="https://inference.baseten.co/v1/chat/completions",
        headers={"Authorization": "Bearer sk-very-secret", "Content-Type": "application/json"},
        request={"model": "meta-models/muse-spark-open-1026", "image": image},
        response={"echo": "key sk-very-secret"},
        elapsed_s=0.5,
    )
    text = json.dumps(call.to_json())

    # Then the key, the auth header, and the image bytes are gone
    assert "sk-very-secret" not in text
    assert "Authorization" not in text
    assert "A" * 600 not in text
    assert "sha256" in text
    assert call.model == "meta-models/muse-spark-open-1026"
    assert call.recorded_at == "1970-01-01T00:00:00Z"
    assert call.source == (
        "recorded live response from meta-models/muse-spark-open-1026 at 1970-01-01T00:00:00Z"
    )


def test_a_live_run_with_record_writes_every_model_call_without_the_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # When a live Meta mission runs with --record, against fake HTTPS
    recording = _record(tmp_path, monkeypatch)

    # Then the recording names each SAM, label, and scene-note call, and holds no key
    calls = read_calls(recording / CALLS_FILE)
    roles = [call.role for call in calls]
    assert "sam" in roles
    assert "label" in roles
    assert roles[-1] == "scene_note"
    assert {call.model for call in calls} == {"sam-3.1", "muse-wonder-1.0"}
    for path in recording.iterdir():
        assert _KEY not in path.read_text(encoding="utf-8")
        assert "secret-model-key" not in path.read_text(encoding="utf-8")
    manifest = json.loads((recording / MANIFEST_FILE).read_text(encoding="utf-8"))
    assert manifest["schema"] == "surmap.model_recording.v1"
    assert manifest["capture"] == "sitl_capture_tiny"
    assert manifest["call_count"] == len(calls)


def test_replay_parses_each_recorded_response_through_its_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given a recording
    recording = load_recording(_record(tmp_path, monkeypatch))

    # When the calls are replayed with no key in the environment
    monkeypatch.delenv("MODEL_API_KEY")
    replayed = replay_model_calls(recording)

    # Then every response parsed: masks counted, labels and the note read back
    outputs = {item.call.role: item.output for item in replayed}
    sam_outputs = [item.output for item in replayed if item.call.role == "sam"]
    assert outputs["concepts"] == "person, collapsed building"
    assert "1 mask(s) for 'person'" in sam_outputs
    assert "1 mask(s) for 'collapsed building'" in sam_outputs
    assert outputs["label"] == "collapsed wall survivor"
    assert outputs["scene_note"].startswith("Scene note quoting the key <redacted>")


def test_offline_replay_labels_the_report_as_recorded_live_responses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given a recording and no live flags
    recording = _record(tmp_path, monkeypatch)
    for name in ("SURMAP_LIVE_META", "MODEL_API_KEY"):
        monkeypatch.delenv(name)

    # When the recorded mission is shown
    result = run_recorded_mission(tmp_path / "out", recording)
    report = json.loads(result.report_path.read_text(encoding="utf-8"))

    # Then the report says it is a recorded live run and labels each response
    assert report["basis"] == "recorded-live"
    assert report["model_call_source"] == "recorded-live"
    assert report["recorded_at"].endswith("Z")
    sources = [call["source"] for call in report["model_calls"]]
    assert sources
    assert all(source.startswith("recorded live response from ") for source in sources)
    assert any("muse-wonder-1.0" in source for source in sources)
    assert result.metrics.basis == "recorded-live"
    assert result.snapshot_path.is_file()


def test_a_fixture_report_says_its_outputs_are_fixtures(tmp_path: Path) -> None:
    result = demo.run_offline_mission(tmp_path)
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert report["model_call_source"] == "fixture"
    assert report["basis"] == "fixtures"


def test_no_committed_recording_means_the_fixture_default_stays(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(demo, "_repo_root", lambda: tmp_path)
    assert default_recording_dir() is None
    (tmp_path / "demo" / "recordings" / "mission").mkdir(parents=True)
    (tmp_path / "demo" / "recordings" / "mission" / MANIFEST_FILE).write_text("{}")
    assert default_recording_dir() == tmp_path / "demo" / "recordings" / "mission"


def test_a_manifest_of_the_wrong_schema_is_refused(tmp_path: Path) -> None:
    (tmp_path / MANIFEST_FILE).write_text(json.dumps({"schema": "other"}))
    with pytest.raises(RecordingError):
        load_recording(tmp_path)


def test_a_recording_with_too_few_responses_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given a recording whose SAM response lines are cut out
    recording = _record(tmp_path, monkeypatch)
    calls_path = recording / CALLS_FILE
    lines = [
        line
        for line in calls_path.read_text(encoding="utf-8").splitlines()
        if '"role": "sam"' not in line
    ]
    calls_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Then replay still parses the rest (each role replays its own queue)
    replayed = replay_model_calls(load_recording(recording))
    assert all(item.call.role != "sam" for item in replayed)


class _Cli(Protocol):
    def main(self, argv: list[str]) -> int: ...


def _script() -> _Cli:
    path = Path("scripts/mission_demo.py")
    spec = importlib.util.spec_from_file_location("mission_demo_cli_recording", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return cast(_Cli, module)


def test_record_without_live_is_refused(tmp_path: Path) -> None:
    assert _script().main(["--record", str(tmp_path), "--no-viewer"]) == 2


def test_the_cli_replays_a_named_recording_offline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Given a recording and no live flags
    recording = _record(tmp_path, monkeypatch)
    monkeypatch.delenv("SURMAP_LIVE_META")
    monkeypatch.delenv("MODEL_API_KEY")
    capsys.readouterr()

    # When the CLI runs offline against it
    code = _script().main(
        ["--recording", str(recording), "--output", str(tmp_path / "out"), "--no-viewer"]
    )
    printed = capsys.readouterr().out

    # Then it says the run is recorded and names each recorded response
    assert code == 0
    assert "recorded live run" in printed
    assert "recorded live response from muse-wonder-1.0" in printed


def test_fixtures_flag_ignores_a_recording(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    recording = _record(tmp_path, monkeypatch)
    monkeypatch.setattr(demo, "_repo_root", lambda: Path.cwd())
    capsys.readouterr()
    code = _script().main(
        [
            "--fixtures",
            "--recording",
            str(recording),
            "--output",
            str(tmp_path / "out"),
            "--no-viewer",
        ]
    )
    assert code == 0
    assert "computed from fixtures" in capsys.readouterr().out
