"""Shared builders for Ask the map tests. Not collected by pytest."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from pathlib import Path

from surmap.mapqa import MapQa, ModelUsage
from surmap.mapqa.snapshot import MapFeature, MapObservation, MapOrigin, MapSnapshot, Xyz

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "mapqa-disaster-snapshot.json"
RESPONSES_URL = "https://api.meta.ai/v1/responses"
TRANSCRIBE_URL = "https://api.meta.ai/v1/asr/transcribe"


class RecordingTransport:
    """Stands in for the Meta HTTP client. Replies are returned in order."""

    def __init__(self, replies: list[bytes]) -> None:
        self._replies = list(replies)
        self.calls: list[tuple[str, dict[str, str], bytes]] = []

    def post(self, url: str, headers: Mapping[str, str], body: bytes) -> bytes:
        self.calls.append((url, dict(headers), body))
        if not self._replies:
            raise AssertionError(f"no reply left for {url}")
        return self._replies.pop(0)


def feature(
    feature_id: str,
    label: str,
    *,
    lat: float | None = 37.1,
    lon: float | None = -122.2,
    motion: str = "static",
    description: str = "",
) -> MapFeature:
    xyz = Xyz(1.0, 2.0, 0.0)
    return MapFeature(
        feature_id,
        xyz,
        lat,
        lon,
        12.0 if lat is not None else None,
        label,
        description or label,
        "surmap.demo",
        motion,
        1_100_000_000,
        1_000_000_000,
        100_000_000,
        (MapObservation(1_100_000_000, xyz),),
        None,
    )


def rescue_map() -> MapSnapshot:
    """A collapsed block with a person on the roof."""
    return MapSnapshot(
        MapOrigin(1_000_000_000, 37.0, -122.0, 12.0, 3.0),
        (feature("1", "collapsed building"),),
        (feature("3", "person", lat=37.11, lon=-122.21, motion="moving"),),
    )


def answer_json(
    answer: str,
    landmark_ids: list[str],
    points: list[tuple[float, float]],
) -> str:
    return json.dumps(
        {
            "answer": answer,
            "landmark_ids": landmark_ids,
            "highlight_points": [{"lat": lat, "lon": lon} for lat, lon in points],
        }
    )


def responses_reply(
    text: str,
    *,
    input_tokens: int = 11,
    output_tokens: int = 22,
    reasoning_tokens: int = 7,
) -> bytes:
    return json.dumps(
        {
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": text}],
                }
            ],
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "output_tokens_details": {"reasoning_tokens": reasoning_tokens},
            },
        }
    ).encode()


def empty_responses_reply() -> bytes:
    return json.dumps(
        {
            "output": [],
            "usage": {
                "input_tokens": 4,
                "output_tokens": 3,
                "output_tokens_details": {"reasoning_tokens": 3},
            },
        }
    ).encode()


def transcribe_reply(transcript: str) -> bytes:
    return json.dumps(
        {
            "sessionId": "test-session",
            "transcript": transcript,
            "audioDurationMs": 1200,
            "turns": [],
        }
    ).encode()


def client(
    snapshot: MapSnapshot,
    transport: RecordingTransport,
    *,
    model: str | None = "muse-wonder-1.0",
    api_key: str | None = "test-key",
    before_call: Callable[[str, Mapping[str, object]], None] | None = None,
    on_usage: Callable[[ModelUsage], None] | None = None,
    usage_ledger: object | None = None,
    max_output_tokens: int = 8192,
    clock: Callable[[], float] | None = None,
) -> MapQa:
    return MapQa(
        snapshot,
        api_key=api_key,
        model=model,
        transport=transport,
        before_call=before_call,
        on_usage=on_usage,
        usage_ledger=usage_ledger,
        max_output_tokens=max_output_tokens,
        clock=clock,
    )


def request_json(transport: RecordingTransport, index: int = 0) -> dict[str, object]:
    parsed: object = json.loads(transport.calls[index][2])
    assert isinstance(parsed, dict)
    return {str(key): value for key, value in parsed.items()}
