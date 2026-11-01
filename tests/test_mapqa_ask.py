"""Text questions, reports, retries, citations, and usage hooks."""

from __future__ import annotations

from collections.abc import Mapping

import pytest

from surmap.mapqa import (
    EmptyModelOutput,
    HighlightPoint,
    InvalidMapAnswer,
    MapQa,
    ModelApiKeyMissing,
    ModelUsage,
    WonderFullRefused,
)
from surmap.mapqa.snapshot import MapSnapshot
from tests.mapqa_fakes import (
    RESPONSES_URL,
    RecordingTransport,
    answer_json,
    client,
    empty_responses_reply,
    feature,
    request_json,
    rescue_map,
    responses_reply,
)


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
    transport = RecordingTransport([responses_reply(answer_json("On the roof.", ["3"], []))])

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
    module.__dict__.update({"UsageRecord": UsageRecord, "UsageLedger": UsageLedger})
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


def test_missing_api_key_raises_before_any_request(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given no key in the constructor or the environment
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    transport = RecordingTransport([responses_reply(answer_json("x", ["3"], [(1.0, 2.0)]))])

    # When a question is asked
    with pytest.raises(ModelApiKeyMissing, match="MODEL_API_KEY"):
        client(rescue_map(), transport, api_key=None).ask("Where is the person?")

    # Then the transport was not used
    assert transport.calls == []
