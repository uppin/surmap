"""Voice questions: transcribe, then ask."""

from __future__ import annotations

from pathlib import Path

from surmap.mapqa.snapshot import MapSnapshot
from tests.mapqa_fakes import (
    RESPONSES_URL,
    TRANSCRIBE_URL,
    RecordingTransport,
    answer_json,
    client,
    feature,
    request_json,
    rescue_map,
    responses_reply,
    transcribe_reply,
)


def test_ask_voice_transcribes_then_asks_the_transcript(tmp_path: Path) -> None:
    # Given a short recording and a transcript that names the person
    audio = tmp_path / "question.wav"
    audio.write_bytes(b"RIFFfake-wav")
    transport = RecordingTransport(
        [
            transcribe_reply("Where is the person on the roof?"),
            responses_reply(answer_json("On the roof.", ["3"], [(37.11, -122.21)])),
        ]
    )

    # When the recording is asked
    answer = client(rescue_map(), transport).ask_voice(audio)

    # Then Muse Voice Transcribe runs first and the transcript is the question
    assert transport.calls[0][0] == TRANSCRIBE_URL
    assert b"muse-voice-transcribe-1.0" in transport.calls[0][2]
    assert b"RIFFfake-wav" in transport.calls[0][2]
    assert b"WAV" in transport.calls[0][2]
    assert "multipart/form-data" in transport.calls[0][1]["Content-Type"]
    asked = request_json(transport, 1)
    assert asked["model"] == "muse-wonder-1.0"
    assert isinstance(asked["input"], str)
    assert "Where is the person on the roof?" in asked["input"]
    assert answer.landmark_ids == ("3",)


def test_ask_voice_retries_a_blank_transcript_once(tmp_path: Path) -> None:
    # Given a blank transcript and then a real one
    audio = tmp_path / "question.wav"
    audio.write_bytes(b"RIFFfake-wav")
    transport = RecordingTransport(
        [
            transcribe_reply("  "),
            transcribe_reply("Where is the van?"),
            responses_reply(answer_json("At the curb.", ["4"], [(37.2, -122.3)])),
        ]
    )
    van = MapSnapshot(None, (feature("4", "vehicle", lat=37.2, lon=-122.3),), ())

    # When the recording is asked
    answer = client(van, transport).ask_voice(audio)

    # Then transcription was retried once before the map question
    assert transport.calls[0][0] == TRANSCRIBE_URL
    assert transport.calls[1][0] == TRANSCRIBE_URL
    assert transport.calls[2][0] == RESPONSES_URL
    assert answer.answer == "At the curb."
