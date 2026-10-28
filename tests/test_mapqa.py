"""Ask the map: questions over a semantic-map snapshot, answered by Meta's model API."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from pathlib import Path

import pytest

from surmap.mapqa import (
    EmptyModelOutput,
    HighlightPoint,
    InvalidMapAnswer,
    MapQa,
    ModelApiKeyMissing,
    ModelUsage,
    SnapshotError,
    WonderFullRefused,
    load_snapshot,
    main,
    start_mapqa_server,
)
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


def test_demo_snapshot_is_a_civilian_rescue_scene() -> None:
    # Given the checked-in disaster snapshot
    text = EXAMPLE.read_text(encoding="utf-8").lower()

    # Then it describes a humanitarian scene and nothing military
    assert "collapsed" in text
    assert "roof" in text
    assert "blocked" in text
    assert "vehicle" in text
    assert "soldier" not in text
    assert "rifle" not in text
    assert "missile" not in text
    assert "artillery" not in text
    assert "weapon" not in text
    assert "military" not in text


def test_loader_reads_the_demo_snapshot_layers() -> None:
    # Given the demo file
    snapshot = load_snapshot(EXAMPLE)

    # Then landmarks and the moving person stay in their own layers
    assert snapshot.origin is not None
    assert snapshot.origin.lat == 37.0
    assert [item.id for item in snapshot.landmarks] == ["1", "2", "4"]
    assert [item.id for item in snapshot.dynamic] == ["3"]
    assert snapshot.dynamic[0].label == "person"
    assert snapshot.dynamic[0].motion == "moving"
    assert snapshot.landmarks[0].xyz.x == 18.0
    assert snapshot.landmarks[0].mask_points is None


def test_loader_rejects_a_snapshot_with_the_wrong_schema(tmp_path: Path) -> None:
    # Given a file that claims a different schema
    path = tmp_path / "map.json"
    path.write_text(
        json.dumps({"schema": "other", "origin": None, "landmarks": [], "dynamic": []}),
        encoding="utf-8",
    )

    # When it is loaded
    with pytest.raises(SnapshotError, match="surmap.semantic_map_snapshot.v1"):
        load_snapshot(path)


def test_ask_sends_muse_wonder_and_returns_cited_landmarks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given a map and a reply that cites the person
    monkeypatch.delenv("SURMAP_MAPQA_MODEL", raising=False)
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    transport = RecordingTransport(
        [
            responses_reply(
                answer_json(
                    "A person is waving from the roof.",
                    ["3"],
                    [(37.11, -122.21)],
                )
            )
        ]
    )
    asked = MapQa(rescue_map(), api_key="test-key", transport=transport, usage_ledger=None)

    # When a responder asks where the person is
    answer = asked.ask("Where is the person who needs rescue?")

    # Then the call is Muse Wonder at high effort, and the citation is returned
    url, headers, _body = transport.calls[0]
    body = request_json(transport)
    assert url == RESPONSES_URL
    assert headers["Authorization"] == "Bearer test-key"
    assert body["model"] == "muse-wonder-1.0"
    assert body["reasoning"] == {"effort": "high"}
    assert isinstance(body["max_output_tokens"], int)
    assert body["max_output_tokens"] >= 8192
    assert isinstance(body["input"], str)
    assert "Where is the person who needs rescue?" in body["input"]
    assert "person" in body["input"]
    assert answer.answer == "A person is waving from the roof."
    assert answer.landmark_ids == ("3",)
    assert answer.highlight_points == (HighlightPoint(37.11, -122.21),)


def test_ask_uses_the_model_and_key_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given the env selects the model and the key
    monkeypatch.setenv("SURMAP_MAPQA_MODEL", "muse-spark-1.3")
    monkeypatch.setenv("MODEL_API_KEY", "env-key")
    transport = RecordingTransport(
        [responses_reply(answer_json("The van is at the curb.", ["4"], [(37.2, -122.3)]))]
    )
    van = MapSnapshot(None, (feature("4", "vehicle", lat=37.2, lon=-122.3),), ())

    # When the question is asked without a constructor key
    MapQa(van, transport=transport, usage_ledger=None).ask("Where is the van?")

    # Then those env values are what was sent
    assert request_json(transport)["model"] == "muse-spark-1.3"
    assert transport.calls[0][1]["Authorization"] == "Bearer env-key"


def test_ask_refuses_a_wonder_full_model_before_any_request() -> None:
    # Given a transport that would fail if it were called
    transport = RecordingTransport([])

    # When the configured model is Muse Wonder Full
    with pytest.raises(WonderFullRefused, match="wonder-full"):
        MapQa(
            rescue_map(),
            api_key="test-key",
            model="muse-wonder-full",
            transport=transport,
            usage_ledger=None,
        )

    # Then nothing is posted
    assert transport.calls == []


def test_ask_refuses_wonder_full_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given the env names Wonder Full with a space in the label
    monkeypatch.setenv("SURMAP_MAPQA_MODEL", "Muse Wonder Full")
    transport = RecordingTransport([])

    # When a client is built from that env
    with pytest.raises(WonderFullRefused):
        MapQa(rescue_map(), api_key="test-key", transport=transport, usage_ledger=None)

    # Then the model is refused before a request
    assert transport.calls == []


def test_max_output_tokens_below_8192_is_rejected() -> None:
    # When the completion budget is below the reasoning floor
    with pytest.raises(ValueError, match="8192"):
        MapQa(
            rescue_map(),
            api_key="test-key",
            transport=RecordingTransport([]),
            usage_ledger=None,
            max_output_tokens=8191,
        )


def test_ask_retries_once_when_the_first_reply_has_no_text() -> None:
    # Given an empty first reply and a citation on the retry
    transport = RecordingTransport(
        [
            empty_responses_reply(),
            responses_reply(answer_json("The road is blocked.", ["2"], [(37.0, -122.0)])),
        ]
    )
    road = MapSnapshot(None, (feature("2", "blocked road", lat=37.0, lon=-122.0),), ())
    seen: list[str] = []

    def before_call(model: str, payload: Mapping[str, object]) -> None:
        seen.append(model)
        assert payload["reasoning"] == {"effort": "high"}

    # When the question is asked
    answer = client(road, transport, before_call=before_call).ask("What blocks access?")

    # Then the same request is sent twice and the second text is kept
    assert len(transport.calls) == 2
    assert transport.calls[0][0] == RESPONSES_URL
    assert transport.calls[1][2] == transport.calls[0][2]
    assert seen == ["muse-wonder-1.0", "muse-wonder-1.0"]
    assert answer.landmark_ids == ("2",)


def test_ask_raises_when_the_retry_is_also_empty() -> None:
    # Given two empty replies
    transport = RecordingTransport([empty_responses_reply(), empty_responses_reply()])

    # When the question is asked
    with pytest.raises(EmptyModelOutput):
        client(rescue_map(), transport).ask("Where is the person?")

    # Then it stopped after the single retry
    assert len(transport.calls) == 2


def test_ask_rejects_an_unknown_landmark_id() -> None:
    # Given a reply that cites an id the map does not have
    transport = RecordingTransport(
        [responses_reply(answer_json("Somewhere else.", ["99"], [(37.1, -122.2)]))]
    )

    # When the answer is validated
    with pytest.raises(InvalidMapAnswer, match="99"):
        client(rescue_map(), transport).ask("Where is the person?")


def test_ask_rejects_a_reply_that_is_not_json() -> None:
    # Given prose instead of one JSON object
    transport = RecordingTransport([responses_reply("The person is on the roof.")])

    # When the answer is parsed
    with pytest.raises(InvalidMapAnswer, match="JSON"):
        client(rescue_map(), transport).ask("Where is the person?")


def test_ask_rejects_a_geolocated_citation_with_no_highlight() -> None:
    # Given a cited person and an empty highlight list
    transport = RecordingTransport(
        [responses_reply(answer_json("On the roof.", ["3"], []))]
    )

    # When the answer is validated
    with pytest.raises(InvalidMapAnswer, match="highlight"):
        client(rescue_map(), transport).ask("Where is the person?")


def test_ask_accepts_a_dynamic_person_id() -> None:
    # Given a reply that cites the moving person
    transport = RecordingTransport(
        [
            responses_reply(
                answer_json("Waving from the roof.", ["3", "1"], [(37.11, -122.21), (37.1, -122.2)])
            )
        ]
    )

    # When the question is asked
    answer = client(rescue_map(), transport).ask("Who needs rescue, and which building?")

    # Then both the dynamic id and the landmark id are kept
    assert answer.landmark_ids == ("3", "1")
    assert answer.highlight_points[0].lat == 37.11
    assert answer.highlight_points[1].lon == -122.2


def test_ask_reports_token_usage_including_reasoning_tokens() -> None:
    # Given a reply with a reasoning-token breakdown
    transport = RecordingTransport(
        [
            responses_reply(
                answer_json("On the roof.", ["3"], [(37.11, -122.21)]),
                input_tokens=40,
                output_tokens=18,
                reasoning_tokens=9,
            )
        ]
    )
    seen: list[ModelUsage] = []

    # When the question is asked
    client(rescue_map(), transport, on_usage=seen.append).ask("Where is the person?")

    # Then the hook sees input, output, and reasoning tokens
    assert seen == [ModelUsage("muse-wonder-1.0", 40, 18, 9)]


def test_ask_records_a_usage_ledger_when_surmap_usage_is_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given a stand-in for the UsageLedger module from the credits PR
    import sys
    import types

    records: list[object] = []
    checked: list[str] = []

    class UsageRecord:
        def __init__(
            self,
            provider: str,
            model: str,
            input_tokens: int,
            output_tokens: int,
            reasoning_tokens: int | None,
            t_unix: float,
        ) -> None:
            self.provider = provider
            self.model = model
            self.input_tokens = input_tokens
            self.output_tokens = output_tokens
            self.reasoning_tokens = reasoning_tokens
            self.t_unix = t_unix

    class UsageLedger:
        def check(self, provider: str) -> None:
            checked.append(provider)

        def __call__(self, record: object) -> None:
            records.append(record)

    module = types.ModuleType("surmap.usage")
    setattr(module, "UsageRecord", UsageRecord)
    setattr(module, "UsageLedger", UsageLedger)
    monkeypatch.setitem(sys.modules, "surmap.usage", module)
    transport = RecordingTransport(
        [
            responses_reply(
                answer_json("On the roof.", ["3"], [(37.11, -122.21)]),
                input_tokens=40,
                output_tokens=18,
                reasoning_tokens=9,
            )
        ]
    )

    # When the question is asked with that ledger
    client(
        rescue_map(),
        transport,
        usage_ledger=UsageLedger(),
        clock=lambda: 1_700_000_000.0,
    ).ask("Where is the person?")

    # Then the ledger was checked and the record matches the response usage
    assert checked == ["meta"]
    recorded = records[0]
    assert isinstance(recorded, UsageRecord)
    assert recorded.provider == "meta"
    assert recorded.model == "muse-wonder-1.0"
    assert recorded.input_tokens == 40
    assert recorded.output_tokens == 18
    assert recorded.reasoning_tokens == 9
    assert recorded.t_unix == 1_700_000_000.0


def test_report_returns_the_markdown_situation_report() -> None:
    # Given a markdown report from the model
    report = "# Situation\n\nA person (id 3) is on the roof.\n"
    transport = RecordingTransport([responses_reply(report)])

    # When the situation report is requested
    text = client(rescue_map(), transport).report()

    # Then the markdown is returned unchanged and the prompt asked for a report
    assert text == report
    body = request_json(transport)
    assert isinstance(body["instructions"], str)
    assert "Markdown" in body["instructions"]
    assert "person" in str(body["input"])


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


def test_missing_api_key_raises_before_any_request(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given no key in the constructor or the environment
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    transport = RecordingTransport([responses_reply(answer_json("x", ["3"], [(1.0, 2.0)]))])

    # When a question is asked
    with pytest.raises(ModelApiKeyMissing, match="MODEL_API_KEY"):
        client(rescue_map(), transport, api_key=None).ask("Where is the person?")

    # Then the transport was not used
    assert transport.calls == []


def test_cli_ask_prints_the_json_contract(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
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


def test_cli_ask_voice_prints_the_answer(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
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


def _post(url: str, payload: dict[str, object]) -> tuple[int, dict[str, object], dict[str, str]]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request) as response:
            parsed: object = json.loads(response.read().decode())
            assert isinstance(parsed, dict)
            headers = {key.lower(): value for key, value in response.headers.items()}
            return response.status, {str(key): value for key, value in parsed.items()}, headers
    except urllib.error.HTTPError as exc:
        parsed = json.loads(exc.read().decode())
        assert isinstance(parsed, dict)
        headers = {key.lower(): value for key, value in exc.headers.items()}
        return exc.code, {str(key): value for key, value in parsed.items()}, headers


def test_post_ask_returns_the_viewer_contract() -> None:
    # Given a server bound to the rescue map
    transport = RecordingTransport(
        [responses_reply(answer_json("On the roof.", ["3"], [(37.11, -122.21)]))]
    )
    server = start_mapqa_server(
        client(rescue_map(), transport),
        host="127.0.0.1",
        port=0,
    )

    # When the viewer posts a question
    try:
        status, body, headers = _post(server.url + "/ask", {"question": "Where is the person?"})
    finally:
        server.close()

    # Then the response is the ask contract and a browser on another origin may read it
    assert status == 200
    assert body == {
        "answer": "On the roof.",
        "landmark_ids": ["3"],
        "highlight_points": [{"lat": 37.11, "lon": -122.21}],
    }
    assert headers["access-control-allow-origin"] == "*"


def test_post_ask_loads_snapshot_path(tmp_path: Path) -> None:
    # Given a second snapshot whose only id is the van
    path = tmp_path / "van.json"
    path.write_text(EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    transport = RecordingTransport(
        [responses_reply(answer_json("The van is at the curb.", ["4"], [(36.9, -121.9)]))]
    )
    server = start_mapqa_server(client(rescue_map(), transport), host="127.0.0.1", port=0)

    # When the viewer names that file
    try:
        status, body, _headers = _post(
            server.url + "/ask",
            {"question": "Where is the vehicle?", "snapshot_path": str(path)},
        )
    finally:
        server.close()

    # Then the citation is validated against that file
    assert status == 200
    assert body["landmark_ids"] == ["4"]
    assert "vehicle" in str(request_json(transport)["input"])


def test_post_ask_rejects_a_missing_question() -> None:
    # Given a running server
    transport = RecordingTransport([])
    server = start_mapqa_server(client(rescue_map(), transport), host="127.0.0.1", port=0)

    # When the body has no question
    try:
        status, body, _headers = _post(server.url + "/ask", {})
    finally:
        server.close()

    # Then the viewer gets a client error and the model is not called
    assert status == 400
    assert body["error"]
    assert transport.calls == []


@pytest.mark.skipif(
    os.environ.get("SURMAP_LIVE_META") != "1",
    reason="set SURMAP_LIVE_META=1 to call the Meta Model API",
)
def test_live_ask_prints_the_map_answer() -> None:
    # Given the demo snapshot and a real MODEL_API_KEY
    asked = MapQa(EXAMPLE)

    # When a responder asks where the person is
    answer = asked.ask("Where is the person who may need rescue, and what blocks the road?")

    # Then the validated answer is printed for the operator
    print(json.dumps(answer.as_dict(), indent=2))
    assert answer.answer.strip()
    assert answer.landmark_ids
    assert answer.highlight_points
