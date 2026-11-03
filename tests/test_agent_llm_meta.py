"""Muse on the Meta Responses API as the agent's chat model: request/reply mapping, tools, usage.

Offline tests replay hand-built Responses bodies (`tests/fixtures/agent/`) through a recording
transport. The live test is gated on `SURMAP_LIVE_META=1` and spends one short tool round trip.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolCall,
    ToolMessage,
)

from surmap.agent.llm.meta import (
    MetaResponsesChatModel,
    MetaResponsesError,
    parse_responses,
    responses_request,
)
from surmap.usage import BudgetExceeded, UsageLedger
from tests.agent_llm_fakes import (
    ECHO_PORTABLE_TOOL,
    ECHO_RESPONSES_TOOL,
    FIXTURE_KEY,
    ROOF_JPEG_B64,
    RecordingMetaTransport,
    a_muse_model,
    a_recorded_reply,
    a_reply,
    echo_tool,
    input_types,
    item_of_type,
    round_trip,
)

AGENT_PROMPT = "You are SurMap's survey agent."


def the_echo_call(call_id: str = "call_echo_1", text: str = "surmap-ping") -> ToolCall:
    return ToolCall(name="echo", args={"text": text}, id=call_id, type="tool_call")


def an_echo_conversation() -> list[BaseMessage]:
    """System prompt, a question, Muse calling `echo`, its result, and Muse's answer."""
    return [
        SystemMessage(content=AGENT_PROMPT),
        HumanMessage(content="Echo surmap-ping."),
        AIMessage(content="", tool_calls=[the_echo_call()]),
        ToolMessage(content="surmap-ping", tool_call_id="call_echo_1"),
        AIMessage(content="It returned surmap-ping."),
    ]


def a_request(*messages: BaseMessage) -> dict[str, object]:
    """The Responses body for `messages` with the agent's defaults and no tools bound."""
    return responses_request(
        messages, [], model="muse-wonder-1.0", effort="medium", max_output_tokens=8192
    )


# --- request mapping ------------------------------------------------------------------------


def test_a_whole_conversation_maps_to_one_responses_request() -> None:
    # Given a conversation in which Muse called echo and answered with its result
    conversation = an_echo_conversation()

    # When it is mapped to a Responses request offering echo
    body = responses_request(
        conversation,
        [ECHO_RESPONSES_TOOL],
        model="muse-wonder-1.0",
        effort="medium",
        max_output_tokens=8192,
    )

    # Then the system prompt is the instructions and every turn is one input item, in order
    assert body == {
        "model": "muse-wonder-1.0",
        "instructions": AGENT_PROMPT,
        "input": [
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "Echo surmap-ping."}],
            },
            {
                "type": "function_call",
                "call_id": "call_echo_1",
                "name": "echo",
                "arguments": '{"text": "surmap-ping"}',
            },
            {"type": "function_call_output", "call_id": "call_echo_1", "output": "surmap-ping"},
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "It returned surmap-ping."}],
            },
        ],
        "tools": [ECHO_RESPONSES_TOOL],
        "stream": False,
        "reasoning": {"effort": "medium"},
        "max_output_tokens": 8192,
    }


def test_an_ai_tool_call_and_its_tool_result_share_one_call_id() -> None:
    # Given Muse called echo as call_7 and the tool answered that call
    history = [
        HumanMessage(content="Echo hello."),
        AIMessage(content="", tool_calls=[the_echo_call("call_7", "hello")]),
        ToolMessage(content="hello", tool_call_id="call_7"),
    ]

    # When the history is mapped to a request
    body = a_request(*history)

    # Then the function_call and its function_call_output carry the same call id
    call_ids = [item["call_id"] for item in item_of_type(body, "function_call")]
    output_ids = [item["call_id"] for item in item_of_type(body, "function_call_output")]
    assert (call_ids, output_ids) == (["call_7"], ["call_7"])


def test_ai_text_beside_tool_calls_is_sent_before_the_calls() -> None:
    # Given Muse said something and asked for two tools in one reply
    reply = AIMessage(
        content="Looking up the recorded runs first.",
        tool_calls=[
            ToolCall(name="list_runs", args={}, id="call_runs_1", type="tool_call"),
            ToolCall(name="get_run", args={"run_id": "run-7"}, id="call_run_2", type="tool_call"),
        ],
    )

    # When that reply is mapped back into a request
    body = a_request(HumanMessage(content="What did run 7 find?"), reply)

    # Then the assistant text comes first, then each call in the order Muse made them
    assert input_types(body) == ["message", "message", "function_call", "function_call"]


def test_a_human_image_block_becomes_an_input_image_data_url() -> None:
    # Given a question about a JPEG frame, sent as a standard image content block
    question = HumanMessage(
        content=[
            {"type": "text", "text": "What is on the roof?"},
            {"type": "image", "base64": ROOF_JPEG_B64, "mime_type": "image/jpeg"},
        ]
    )

    # When it is mapped to a request
    body = a_request(question)

    # Then the frame travels as an input_image data URL after the question text
    assert item_of_type(body, "message")[0]["content"] == [
        {"type": "input_text", "text": "What is on the roof?"},
        {"type": "input_image", "image_url": f"data:image/jpeg;base64,{ROOF_JPEG_B64}"},
    ]


def test_an_openai_style_image_url_part_is_sent_as_its_data_url() -> None:
    # Given a frame attached as an OpenAI-style image_url part
    data_url = f"data:image/jpeg;base64,{ROOF_JPEG_B64}"
    question = HumanMessage(content=[{"type": "image_url", "image_url": {"url": data_url}}])

    # When it is mapped to a request
    body = a_request(question)

    # Then the same data URL is sent as the input_image
    assert item_of_type(body, "message")[0]["content"] == [
        {"type": "input_image", "image_url": data_url}
    ]


def test_a_history_without_a_system_message_sends_no_instructions() -> None:
    # Given a history that is only a question
    question = HumanMessage(content="How many runs are recorded?")

    # When it is mapped to a request
    body = a_request(question)

    # Then the request has no instructions field
    assert "instructions" not in body


def test_a_request_with_no_bound_tools_sends_no_tools_field() -> None:
    # Given a question and no tools bound
    question = HumanMessage(content="How many runs are recorded?")

    # When it is mapped to a request
    body = a_request(question)

    # Then the request offers no tools at all
    assert "tools" not in body


# --- tool binding ---------------------------------------------------------------------------


def test_a_bound_langchain_tool_is_sent_as_a_responses_function_tool() -> None:
    # Given Muse with the echo tool bound
    transport = RecordingMetaTransport.replying("text")
    model = a_muse_model(transport).bind_tools([echo_tool()])

    # When one turn runs
    model.invoke("Echo surmap-ping.")

    # Then echo is offered as a flat Responses function tool with its JSON schema
    assert transport.last_body["tools"] == [ECHO_RESPONSES_TOOL]


def test_the_runtimes_portable_tool_dict_is_sent_as_a_responses_function_tool() -> None:
    # Given Muse bound to echo in the provider-portable shape the agent runtime hands over
    transport = RecordingMetaTransport.replying("text")
    model = a_muse_model(transport).bind_tools([ECHO_PORTABLE_TOOL])

    # When one turn runs
    model.invoke("Echo surmap-ping.")

    # Then the nested function definition is flattened into a Responses function tool
    assert transport.last_body["tools"] == [ECHO_RESPONSES_TOOL]


# --- reply mapping --------------------------------------------------------------------------


def test_a_text_reply_becomes_the_message_content() -> None:
    # Given the recorded reply that answers in text after reasoning
    body = a_recorded_reply("text")

    # When it is parsed
    message = parse_responses(body, requested_model="muse-wonder-1.0")

    # Then the answer is the output text, with no tool calls
    assert (message.content, message.tool_calls) == (
        "Two people are on the roof of the collapsed block.",
        [],
    )


def test_a_function_call_item_becomes_a_tool_call_with_dict_arguments() -> None:
    # Given the recorded reply that calls echo(text="surmap-ping") as call_echo_1
    body = a_recorded_reply("one_call")

    # When it is parsed
    message = parse_responses(body, requested_model="muse-wonder-1.0")

    # Then the message asks for exactly that call, with its arguments decoded
    assert message.tool_calls == [the_echo_call("call_echo_1", "surmap-ping")]


def test_two_function_calls_keep_their_order_beside_the_text() -> None:
    # Given the recorded reply that says one line and calls list_runs then get_run(run-7)
    body = a_recorded_reply("two_calls")

    # When it is parsed
    message = parse_responses(body, requested_model="muse-wonder-1.0")

    # Then the text and both calls survive, in Muse's order
    assert message.content == "Looking up the recorded runs first."
    assert [(call["id"], call["name"], call["args"]) for call in message.tool_calls] == [
        ("call_runs_1", "list_runs", {}),
        ("call_run_2", "get_run", {"run_id": "run-7"}),
    ]


def test_unparseable_arguments_become_an_invalid_tool_call() -> None:
    # Given a reply whose echo call carries arguments that are not JSON
    body = a_reply(
        {"type": "function_call", "call_id": "call_bad", "name": "echo", "arguments": "{text:"}
    )

    # When it is parsed
    message = parse_responses(body, requested_model="muse-wonder-1.0")

    # Then the call is kept as invalid, with its raw arguments, instead of being dropped
    assert (message.tool_calls, [call["args"] for call in message.invalid_tool_calls]) == (
        [],
        ["{text:"],
    )


def test_usage_becomes_the_messages_usage_metadata() -> None:
    # Given the recorded text reply: 812 in, 64 out of which 40 reasoning
    body = a_recorded_reply("text")

    # When it is parsed
    message = parse_responses(body, requested_model="muse-wonder-1.0")

    # Then the token counts are on the message in LangChain's usage shape
    assert message.usage_metadata == {
        "input_tokens": 812,
        "output_tokens": 64,
        "total_tokens": 876,
        "output_token_details": {"reasoning": 40},
    }


def test_the_reply_names_the_requested_model_when_the_body_does_not() -> None:
    # Given a reply body that does not say which model answered
    body = a_reply({"type": "message", "content": [{"type": "output_text", "text": "Done."}]})

    # When it is parsed for a muse-spark-1.3 request
    message = parse_responses(body, requested_model="muse-spark-1.3")

    # Then the message is attributed to the requested model
    assert message.response_metadata["model_name"] == "muse-spark-1.3"


def test_a_body_without_an_output_list_is_refused() -> None:
    # Given an error-shaped body with no output list
    body: dict[str, object] = {"error": {"message": "tools are not supported"}}

    # When it is parsed, then a named Meta Responses error is raised
    with pytest.raises(MetaResponsesError, match="output"):
        parse_responses(body, requested_model="muse-wonder-1.0")


# --- the model end to end over a fake transport ----------------------------------------------


def test_a_turn_is_posted_to_the_meta_responses_endpoint() -> None:
    # Given Muse over a recording transport
    transport = RecordingMetaTransport.replying("text")

    # When one turn runs
    a_muse_model(transport).invoke("Who is on the roof?")

    # Then exactly one request went to the Responses endpoint
    assert transport.urls == ["https://api.meta.ai/v1/responses"]


def test_the_request_carries_the_models_effort_and_output_cap() -> None:
    # Given Muse Spark configured for low effort and a 2048-token cap
    transport = RecordingMetaTransport.replying("text")
    model = a_muse_model(
        transport, model="muse-spark-1.3", reasoning_effort="low", max_output_tokens=2048
    )

    # When one turn runs
    model.invoke("Who is on the roof?")

    # Then the request names that model, effort and cap
    sent = transport.last_body
    assert (sent["model"], sent["reasoning"], sent["max_output_tokens"]) == (
        "muse-spark-1.3",
        {"effort": "low"},
        2048,
    )


def test_the_key_travels_only_in_the_bearer_header() -> None:
    # Given Muse keyed with the fixture key
    transport = RecordingMetaTransport.replying("text")

    # When one turn runs
    a_muse_model(transport).invoke("Who is on the roof?")

    # Then the key is the bearer token and appears nowhere in the body
    assert transport.headers[0]["Authorization"] == f"Bearer {FIXTURE_KEY}"
    assert FIXTURE_KEY not in json.dumps(transport.last_body)


def test_a_missing_key_is_refused_before_any_request(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given no MODEL_API_KEY in the environment and none given to the model
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    transport = RecordingMetaTransport.replying("text")
    model = MetaResponsesChatModel(transport=transport)

    # When a turn is attempted, then it is refused by naming the missing key
    with pytest.raises(MetaResponsesError, match="MODEL_API_KEY"):
        model.invoke("Who is on the roof?")

    # And nothing was sent
    assert transport.calls == 0


def test_a_turns_tool_call_reaches_the_caller_as_an_ai_message() -> None:
    # Given Muse whose reply calls echo(text="surmap-ping")
    transport = RecordingMetaTransport.replying("one_call")

    # When one turn runs with echo bound
    reply = a_muse_model(transport).bind_tools([echo_tool()]).invoke("Echo surmap-ping.")

    # Then the caller gets that tool call to run
    assert reply.tool_calls == [the_echo_call("call_echo_1", "surmap-ping")]


def test_every_response_is_recorded_in_the_usage_ledger(tmp_path: Path) -> None:
    # Given Muse writing usage to a ledger, answering with the 876-token text reply
    ledger = UsageLedger(tmp_path / "usage.jsonl")
    transport = RecordingMetaTransport.replying("text")

    # When one turn runs
    a_muse_model(transport, usage_sink=ledger).invoke("Who is on the roof?")

    # Then the ledger holds one Meta call of 876 tokens
    assert (ledger.calls("meta"), ledger.total_tokens("meta")) == (1, 876)


def test_a_spent_meta_budget_refuses_the_turn_before_any_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given a Meta budget of one call, already spent in the ledger
    monkeypatch.setenv("SURMAP_BUDGET_META_CALLS", "1")
    ledger = UsageLedger(tmp_path / "usage.jsonl")
    spent = RecordingMetaTransport.replying("text")
    a_muse_model(spent, usage_sink=ledger).invoke("Who is on the roof?")
    transport = RecordingMetaTransport.replying("text")
    model = a_muse_model(transport, usage_sink=ledger).model_copy(
        update={"before_call": ledger.check}
    )

    # When another turn is attempted, then the budget refuses it
    with pytest.raises(BudgetExceeded):
        model.invoke("Who is on the roof?")

    # And nothing was sent
    assert transport.calls == 0


def test_an_empty_reply_is_asked_for_once_more() -> None:
    # Given Muse that first spends its budget reasoning, then answers
    transport = RecordingMetaTransport.replying("empty", "text")

    # When one turn runs
    reply = a_muse_model(transport).invoke("Who is on the roof?")

    # Then the second answer is returned after exactly two requests
    assert (reply.content, transport.calls) == (
        "Two people are on the roof of the collapsed block.",
        2,
    )


def test_two_empty_replies_raise_a_named_error() -> None:
    # Given Muse that returns nothing twice
    transport = RecordingMetaTransport.replying("empty", "empty")
    model = a_muse_model(transport)

    # When one turn runs, then it fails naming the empty output after one retry
    with pytest.raises(MetaResponsesError, match="no output"):
        model.invoke("Who is on the roof?")


async def test_an_async_turn_answers_like_a_sync_one() -> None:
    # Given Muse over a recording transport
    transport = RecordingMetaTransport.replying("text")

    # When one turn runs asynchronously
    reply = await a_muse_model(transport).ainvoke("Who is on the roof?")

    # Then it answers with the recorded text
    assert reply.content == "Two people are on the roof of the collapsed block."


# --- live -----------------------------------------------------------------------------------


@pytest.mark.skipif(
    os.environ.get("SURMAP_LIVE_META") != "1",
    reason="set SURMAP_LIVE_META=1 to call the Meta Model API",
)
def test_a_live_muse_turn_calls_echo_and_answers_with_its_result() -> None:
    # Given Muse on the live Responses API, keyed from MODEL_API_KEY, recording credits
    model = MetaResponsesChatModel(usage_sink=UsageLedger())

    # When it is offered echo and then given the result of its call
    trip = round_trip(model)

    # Then it called echo and answered with what echo returned
    assert trip.call.tool_calls[0]["name"] == "echo"
    assert "surmap-ping" in trip.answer.text
