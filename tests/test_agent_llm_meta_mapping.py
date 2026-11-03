"""Muse's Responses mapping as pure functions: `responses_request` and `parse_responses`.

No socket: these pin the history → request body and response body → `AIMessage` mapping exactly,
over hand-built Responses bodies (`tests/fixtures/agent/`). The model itself, over its real
transport, is tested against the fake Meta server in `tests/test_agent_llm_meta.py`.
"""

from __future__ import annotations

import pytest
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolCall,
    ToolMessage,
)

from surmap.agent.llm.meta import MetaResponsesError, parse_responses, responses_request
from tests.agent_llm_fakes import (
    ECHO_RESPONSES_TOOL,
    ROOF_JPEG_B64,
    a_recorded_reply,
    a_reply,
    input_types,
    item_of_type,
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
