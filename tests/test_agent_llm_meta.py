"""Muse chat models over the fake Meta server on a real loopback socket.

The adapter's real transport (`UrllibMetaMuseTransport`) sends real bytes to `tests/fake_meta.py`;
nothing leaves loopback. The pure request / reply mapping is pinned in
`tests/test_agent_llm_meta_mapping.py`. The live test is gated on `SURMAP_LIVE_META=1`, reads
`MODEL_API_KEY` from the shell or the project `.env`, and spends one short tool round trip.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolCall, ToolMessage
from pydantic import SecretStr

from surmap.agent.llm.meta import MetaResponsesChatModel, MetaResponsesError, ReasoningEffort
from surmap.env import load_env
from surmap.usage import BudgetExceeded, UsageLedger, UsageRecord, UsageSink
from tests.agent_llm_fakes import (
    ECHO_PORTABLE_TOOL,
    ECHO_RESPONSES_TOOL,
    ROOF_JPEG_B64,
    echo_tool,
    item_of_type,
    round_trip,
)
from tests.fake_meta import (
    FAKE_META_KEY,
    FakeMetaScript,
    answering,
    calling,
    reasoning_only,
    serving,
)

QUESTION = "Who is on the roof?"
ROOF_ANSWER = "Two people are on the roof of the collapsed block."


def a_muse_model(
    base_url: str,
    *,
    usage_sink: UsageSink | None = None,
    before_call: UsageLedger | None = None,
    model: str = "muse-wonder-1.0",
    reasoning_effort: ReasoningEffort = "medium",
    max_output_tokens: int = 8192,
) -> MetaResponsesChatModel:
    """Muse on the fake Meta server, keyed with the fake key, over its real transport."""
    return MetaResponsesChatModel(
        model=model,
        reasoning_effort=reasoning_effort,
        max_output_tokens=max_output_tokens,
        base_url=base_url,
        api_key=SecretStr(FAKE_META_KEY),
        usage_sink=usage_sink,
        before_call=before_call.check if before_call is not None else None,
    )


def the_echo_call(call_id: str = "call_echo_1", text: str = "surmap-ping") -> ToolCall:
    return ToolCall(name="echo", args={"text": text}, id=call_id, type="tool_call")


class RecordingSink:
    def __init__(self) -> None:
        self.records: list[UsageRecord] = []

    def __call__(self, record: UsageRecord) -> None:
        self.records.append(record)


# --- the request ------------------------------------------------------------------------------


def test_a_turn_is_posted_to_the_responses_path_of_the_base_url() -> None:
    # Given the fake answering with text
    script = FakeMetaScript(rounds=[answering(ROOF_ANSWER)])
    with serving(script) as base:
        # When one turn runs
        a_muse_model(base).invoke(QUESTION)

    # Then exactly one request was posted to /v1/responses
    assert [(r.method, r.path) for r in script.requests] == [("POST", "/v1/responses")]


def test_the_default_base_url_is_the_meta_model_api() -> None:
    # When Muse is made without a base URL (no request is made)
    model = MetaResponsesChatModel()

    # Then it posts to the Meta Model API
    assert model.base_url == "https://api.meta.ai/v1"


def test_the_key_travels_only_in_the_bearer_header() -> None:
    # Given the fake answering with text
    script = FakeMetaScript(rounds=[answering(ROOF_ANSWER)])
    with serving(script) as base:
        # When one turn runs
        a_muse_model(base).invoke(QUESTION)

    # Then the key is the bearer token and appears nowhere in the body
    assert script.last_request.header("authorization") == f"Bearer {FAKE_META_KEY}"
    assert FAKE_META_KEY not in json.dumps(dict(script.last_request.body))


def test_the_request_carries_the_models_effort_and_output_cap() -> None:
    # Given Muse Spark configured for low effort and a 2048-token cap
    script = FakeMetaScript(rounds=[answering(ROOF_ANSWER)])
    with serving(script) as base:
        model = a_muse_model(
            base, model="muse-spark-1.3", reasoning_effort="low", max_output_tokens=2048
        )

        # When one turn runs
        model.invoke(QUESTION)

    # Then the request names that model, effort and cap, and does not stream
    sent = script.last_request.body
    assert (sent["model"], sent["reasoning"], sent["max_output_tokens"], sent["stream"]) == (
        "muse-spark-1.3",
        {"effort": "low"},
        2048,
        False,
    )


def test_a_bound_langchain_tool_is_sent_as_a_responses_function_tool() -> None:
    # Given Muse with the echo tool bound
    script = FakeMetaScript(rounds=[answering("ok")])
    with serving(script) as base:
        # When one turn runs
        a_muse_model(base).bind_tools([echo_tool()]).invoke("Echo surmap-ping.")

    # Then echo is offered as a flat Responses function tool with its JSON schema
    assert script.last_request.body["tools"] == [ECHO_RESPONSES_TOOL]


def test_the_runtimes_portable_tool_dict_is_sent_as_a_responses_function_tool() -> None:
    # Given Muse bound to echo in the provider-portable shape the agent runtime hands over
    script = FakeMetaScript(rounds=[answering("ok")])
    with serving(script) as base:
        # When one turn runs
        a_muse_model(base).bind_tools([ECHO_PORTABLE_TOOL]).invoke("Echo surmap-ping.")

    # Then the nested function definition is flattened into a Responses function tool
    assert script.last_request.body["tools"] == [ECHO_RESPONSES_TOOL]


def test_a_tool_result_is_sent_as_a_function_call_output_with_the_call_s_id() -> None:
    # Given a history in which Muse called echo as call_7 and the tool answered it
    history = [
        HumanMessage(content="Echo hello."),
        AIMessage(content="", tool_calls=[the_echo_call("call_7", "hello")]),
        ToolMessage(content="hello", tool_call_id="call_7"),
    ]
    script = FakeMetaScript(rounds=[answering("It returned hello.")])
    with serving(script) as base:
        # When the next turn runs
        a_muse_model(base).bind_tools([echo_tool()]).invoke(history)

    # Then the posted function_call and function_call_output share call_7
    body = script.last_request.body
    assert [i["call_id"] for i in item_of_type(body, "function_call")] == ["call_7"]
    assert item_of_type(body, "function_call_output") == [
        {"type": "function_call_output", "call_id": "call_7", "output": "hello"}
    ]


def test_an_image_block_is_posted_as_an_input_image_data_url() -> None:
    # Given a question about a JPEG frame, sent as a standard image content block
    question = HumanMessage(
        content=[
            {"type": "text", "text": "What is on the roof?"},
            {"type": "image", "base64": ROOF_JPEG_B64, "mime_type": "image/jpeg"},
        ]
    )
    script = FakeMetaScript(rounds=[answering(ROOF_ANSWER)])
    with serving(script) as base:
        # When one turn runs
        a_muse_model(base).invoke([question])

    # Then the frame travels as an input_image data URL after the question text
    assert item_of_type(script.last_request.body, "message")[0]["content"] == [
        {"type": "input_text", "text": "What is on the roof?"},
        {"type": "input_image", "image_url": f"data:image/jpeg;base64,{ROOF_JPEG_B64}"},
    ]


# --- the reply --------------------------------------------------------------------------------


def test_a_turns_tool_call_reaches_the_caller_as_an_ai_message() -> None:
    # Given the fake calling echo(text="surmap-ping")
    script = FakeMetaScript(rounds=[calling("echo", "call_echo_1", text="surmap-ping")])
    with serving(script) as base:
        # When one turn runs with echo bound
        reply = a_muse_model(base).bind_tools([echo_tool()]).invoke("Echo surmap-ping.")

    # Then the caller gets that tool call to run
    assert reply.tool_calls == [the_echo_call("call_echo_1", "surmap-ping")]


def test_a_text_reply_is_the_answer_with_its_usage_metadata() -> None:
    # Given the fake answering in text: 812 in, 64 out of which 40 reasoning
    script = FakeMetaScript(rounds=[answering(ROOF_ANSWER)])
    with serving(script) as base:
        # When one turn runs
        reply = a_muse_model(base).invoke(QUESTION)

    # Then the text is the answer and the counts are on the message
    assert isinstance(reply, AIMessage)
    assert reply.content == ROOF_ANSWER
    assert reply.usage_metadata == {
        "input_tokens": 812,
        "output_tokens": 64,
        "total_tokens": 876,
        "output_token_details": {"reasoning": 40},
    }


async def test_an_async_turn_answers_like_a_sync_one() -> None:
    # Given the fake answering with text
    script = FakeMetaScript(rounds=[answering(ROOF_ANSWER)])
    with serving(script) as base:
        # When one turn runs asynchronously
        reply = await a_muse_model(base).ainvoke(QUESTION)

    # Then it answers with that text
    assert reply.content == ROOF_ANSWER


def test_an_empty_reply_is_asked_for_once_more() -> None:
    # Given the fake first spending its budget reasoning, then answering
    script = FakeMetaScript(rounds=[reasoning_only(), answering(ROOF_ANSWER)])
    with serving(script) as base:
        # When one turn runs
        reply = a_muse_model(base).invoke(QUESTION)

    # Then the second answer is returned after exactly two requests
    assert (reply.content, len(script.responses_requests)) == (ROOF_ANSWER, 2)


def test_two_empty_replies_raise_a_named_error() -> None:
    # Given the fake returning nothing, every time
    script = FakeMetaScript(rounds=[reasoning_only()])
    with serving(script) as base:
        model = a_muse_model(base)

        # When one turn runs, then it fails naming the empty output after one retry
        with pytest.raises(MetaResponsesError, match="no output"):
            model.invoke(QUESTION)

    # And it asked exactly twice
    assert len(script.responses_requests) == 2


# --- usage and budget -------------------------------------------------------------------------


def test_every_response_is_recorded_in_the_usage_ledger(tmp_path: Path) -> None:
    # Given Muse writing usage to a ledger, and the fake answering with 876 tokens
    ledger = UsageLedger(tmp_path / "usage.jsonl")
    script = FakeMetaScript(rounds=[answering(ROOF_ANSWER)])
    with serving(script) as base:
        # When one turn runs
        a_muse_model(base, usage_sink=ledger).invoke(QUESTION)

    # Then the ledger holds one Meta call of 876 tokens
    assert (ledger.calls("meta"), ledger.total_tokens("meta")) == (1, 876)


def test_a_response_s_reasoning_tokens_are_recorded_under_meta() -> None:
    # Given the fake answering with 30 in, 9 out of which 5 reasoning
    sink = RecordingSink()
    script = FakeMetaScript(
        rounds=[answering("ok", input_tokens=30, output_tokens=9, reasoning_tokens=5)]
    )
    with serving(script) as base:
        # When one turn runs
        a_muse_model(base, usage_sink=sink).invoke(QUESTION)

    # Then one record names Meta, the model and every count
    assert [
        (r.provider, r.model, r.input_tokens, r.output_tokens, r.reasoning_tokens)
        for r in sink.records
    ] == [("meta", "muse-wonder-1.0", 30, 9, 5)]


def test_a_spent_meta_budget_refuses_the_turn_before_any_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given a Meta budget of one call, spent on the fake
    monkeypatch.setenv("SURMAP_BUDGET_META_CALLS", "1")
    ledger = UsageLedger(tmp_path / "usage.jsonl")
    script = FakeMetaScript(rounds=[answering(ROOF_ANSWER)])
    with serving(script) as base:
        model = a_muse_model(base, usage_sink=ledger, before_call=ledger)
        model.invoke(QUESTION)

        # When another turn is attempted, then the budget refuses it
        with pytest.raises(BudgetExceeded):
            model.invoke(QUESTION)

    # And only the first turn reached the server
    assert len(script.responses_requests) == 1


# --- errors and the key -----------------------------------------------------------------------


def test_a_missing_key_is_refused_before_any_request(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given no MODEL_API_KEY in the environment and none given to the model
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    script = FakeMetaScript(rounds=[answering(ROOF_ANSWER)])
    with serving(script) as base:
        model = MetaResponsesChatModel(base_url=base)

        # When a turn is attempted, then it is refused by naming the missing key
        with pytest.raises(MetaResponsesError, match="MODEL_API_KEY"):
            model.invoke(QUESTION)

    # And nothing was sent
    assert script.requests == []


def test_an_error_status_names_its_status_and_not_the_key() -> None:
    # Given the fake failing every request
    script = FakeMetaScript(status=500)
    with serving(script) as base:
        # When one turn runs, then it fails with the status
        with pytest.raises(MetaResponsesError, match="HTTP 500") as raised:
            a_muse_model(base).invoke(QUESTION)

    # And the error does not hold the key
    assert FAKE_META_KEY not in str(raised.value)


# --- live -------------------------------------------------------------------------------------


@pytest.mark.skipif(
    os.environ.get("SURMAP_LIVE_META") != "1",
    reason="set SURMAP_LIVE_META=1 (and MODEL_API_KEY in the shell or .env) to call it",
)
def test_a_live_muse_turn_calls_echo_and_answers_with_its_result() -> None:
    # Given Muse on the live Responses API, keyed from MODEL_API_KEY in the shell or the
    # project .env, recording credits
    load_env()
    model = MetaResponsesChatModel(usage_sink=UsageLedger())

    # When it is offered echo and then given the result of its call
    trip = round_trip(model)

    # Then it called echo and answered with what echo returned
    assert trip.call.tool_calls[0]["name"] == "echo"
    assert "surmap-ping" in trip.answer.text
