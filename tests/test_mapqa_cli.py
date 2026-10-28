"""The ask, report, and ask-voice commands."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from surmap.mapqa import main
from tests.mapqa_fakes import (
    EXAMPLE,
    RecordingTransport,
    answer_json,
    responses_reply,
    transcribe_reply,
)


def test_cli_ask_prints_the_json_contract(capsys: pytest.CaptureFixture[str]) -> None:
    # Given the demo snapshot and a canned citation
    transport = RecordingTransport(
        [
            responses_reply(
                answer_json("A person is on the roof.", ["3"], [(37.0002173913, -121.9997930354)])
            )
        ]
    )

    # When the ask command runs
    code = main(
        ["ask", "--snapshot", str(EXAMPLE), "--question", "Where is the person?"],
        transport=transport,
        api_key="test-key",
    )

    # Then the process prints the viewer contract
    assert code == 0
    printed: object = json.loads(capsys.readouterr().out)
    assert printed == {
        "answer": "A person is on the roof.",
        "landmark_ids": ["3"],
        "highlight_points": [{"lat": 37.0002173913, "lon": -121.9997930354}],
    }


def test_cli_report_prints_markdown(capsys: pytest.CaptureFixture[str]) -> None:
    # Given a markdown reply
    report = "# Situation\n\nThe access road is blocked (id 2).\n"
    transport = RecordingTransport([responses_reply(report)])

    # When the report command runs
    code = main(
        ["report", "--snapshot", str(EXAMPLE)],
        transport=transport,
        api_key="test-key",
    )

    # Then the markdown is the whole stdout
    assert code == 0
    assert capsys.readouterr().out == report


def test_cli_ask_voice_prints_the_answer(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Given a recording whose transcript asks about the van
    audio = tmp_path / "question.wav"
    audio.write_bytes(b"RIFFfake-wav")
    transport = RecordingTransport(
        [
            transcribe_reply("Where is the vehicle?"),
            responses_reply(answer_json("The van is at the curb.", ["4"], [(36.9, -121.9)])),
        ]
    )

    # When ask-voice runs
    code = main(
        ["ask-voice", "--snapshot", str(EXAMPLE), "--audio", str(audio)],
        transport=transport,
        api_key="test-key",
    )

    # Then the printed contract cites the vehicle
    assert code == 0
    printed: object = json.loads(capsys.readouterr().out)
    assert isinstance(printed, dict)
    assert printed["landmark_ids"] == ["4"]
