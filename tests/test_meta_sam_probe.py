"""One-shot Meta SAM probe: one response saved, key never stored."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

import pytest

from surmap.survey.meta_sam import MetaSamDetector, probe_sam
from surmap.survey.sam import SamDetection
from tests.test_meta_sam import FIXTURE_KEY, ONE_OBJECT_LINE, a_jpeg_frame, a_response

REPO = Path(__file__).resolve().parent.parent


class RecordingTransport:
    def __init__(self, body: Mapping[str, object]) -> None:
        self.body = body
        self.calls = 0

    def post(
        self,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, object],
    ) -> Mapping[str, object]:
        self.calls += 1
        return self.body


def test_the_env_overrides_the_session_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given a per-session cap in the environment
    monkeypatch.setenv("SURMAP_META_SAM_MAX_CALLS", "12")
    detector = MetaSamDetector(api_key=FIXTURE_KEY, transport=RecordingTransport(a_response("")))

    # Then that cap is the one the detector enforces
    assert detector.max_calls_per_session == 12


def test_an_explicit_cap_wins_over_the_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given the env allows 12 calls and the constructor asks for 2
    monkeypatch.setenv("SURMAP_META_SAM_MAX_CALLS", "12")
    detector = MetaSamDetector(
        api_key=FIXTURE_KEY,
        transport=RecordingTransport(a_response("")),
        max_calls_per_session=2,
    )

    # Then the constructor value is the cap
    assert detector.max_calls_per_session == 2


def test_a_wonder_full_model_id_is_rejected() -> None:
    # Given the uncovered Muse Wonder Full id
    # When a detector is constructed with it
    with pytest.raises(ValueError, match="(?i)wonder-full"):
        MetaSamDetector(api_key=FIXTURE_KEY, model="Muse-Wonder-Full")


def test_a_wonder_full_model_id_with_an_underscore_is_rejected() -> None:
    # Given the underscore spelling of the uncovered id
    with pytest.raises(ValueError, match="wonder_full"):
        MetaSamDetector(api_key=FIXTURE_KEY, model="muse_wonder_full")


def test_a_model_id_may_contain_wonder() -> None:
    # Given an id that mentions wonder and is not Wonder Full
    detector = MetaSamDetector(
        api_key=FIXTURE_KEY,
        model="muse-wonder-1",
        transport=RecordingTransport(a_response("")),
    )

    # Then the detector accepts it
    assert detector.model == "muse-wonder-1"


def test_a_probe_saves_the_response_and_leaves_the_key_out(tmp_path: Path) -> None:
    # Given a canned response that echoes the bearer token
    leaked = dict(a_response(ONE_OBJECT_LINE))
    leaked["echo"] = FIXTURE_KEY
    transport = RecordingTransport(leaked)
    output = tmp_path / "meta-sam-last-response.json"

    # When one frame is probed
    detections = probe_sam(
        a_jpeg_frame(),
        prompt="person",
        output_path=output,
        api_key=FIXTURE_KEY,
        transport=transport,
    )

    # Then one detection comes back, the wire text is saved, and the key is not
    assert transport.calls == 1
    assert len(detections) == 1
    assert isinstance(detections[0], SamDetection)
    saved = output.read_text(encoding="utf-8")
    parsed = json.loads(saved)
    assert isinstance(parsed, dict)
    content = parsed["output"]
    assert isinstance(content, list)
    assert FIXTURE_KEY not in saved
    assert "[redacted]" in saved
    assert ONE_OBJECT_LINE in saved


def test_the_check_script_does_not_call_meta_without_both_env_vars() -> None:
    # Given a process environment with neither live flag nor key
    env = {"PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", "")}

    # When the check script starts
    result = subprocess.run(
        [sys.executable, "scripts/check_meta_sam.py"],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    # Then it refuses before any request
    assert result.returncode == 2
    assert "SURMAP_LIVE_META" in result.stderr
    assert "MODEL_API_KEY" in result.stderr
    assert "fixture-key" not in result.stderr
    assert "fixture-key" not in result.stdout
