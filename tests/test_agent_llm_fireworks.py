"""Fireworks chat models over the fake Fireworks provider on a real loopback socket.

The adapter's real client sends real bytes to `tests/fake_fireworks.py`; nothing leaves loopback.
The live test is gated on `SURMAP_LIVE_FIREWORKS=1` and reads `FIREWORKS_API_KEY` from the shell
or the project `.env`.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage

from surmap.agent.llm.fireworks import (
    FireworksChatModel,
    FireworksError,
    fireworks_base_url,
    fireworks_chat_model,
)
from surmap.env import load_env
from surmap.usage import BudgetExceeded, UsageLedger, UsageRecord
from tests.agent_llm_fakes import ECHO_PARAMETERS, ECHO_PORTABLE_TOOL, round_trip
from tests.fake_fireworks import (
    FAKE_FIREWORKS_KEY,
    FAKE_FIREWORKS_MODEL,
    FakeFireworksScript,
    answering,
    calling,
    serving,
)

QUESTION = "what demos can you run?"


def a_fireworks_model(
    base_url: str,
    *,
    usage_sink: UsageLedger | None = None,
    before_call: UsageLedger | None = None,
    api_key: str = FAKE_FIREWORKS_KEY,
) -> FireworksChatModel:
    """The Fireworks model on the fake, keyed with the fake key, never retrying."""
    return fireworks_chat_model(
        FAKE_FIREWORKS_MODEL,
        api_key=api_key,
        base_url=base_url,
        usage_sink=usage_sink,
        before_call=before_call.check if before_call is not None else None,
        max_retries=0,
    )


async def streamed(model: FireworksChatModel, text: str) -> AIMessageChunk:
    """The whole streamed reply, its chunks added as the runtime adds them."""
    whole: AIMessageChunk | None = None
    async for piece in model.bind_tools([ECHO_PORTABLE_TOOL]).astream([HumanMessage(text)]):
        assert isinstance(piece, AIMessageChunk)
        whole = piece if whole is None else whole + piece
    assert whole is not None, "nothing was streamed"
    return whole


class RecordingSink:
    def __init__(self) -> None:
        self.records: list[UsageRecord] = []

    def __call__(self, record: UsageRecord) -> None:
        self.records.append(record)


# --- the request ------------------------------------------------------------------------------


def test_a_turn_posts_the_model_id_to_the_chat_completions_path_with_the_bearer_key() -> None:
    # Given the fake answering with text
    script = FakeFireworksScript(rounds=[answering("Two scenes are ready.")])
    with serving(script) as base:
        # When one turn runs
        a_fireworks_model(base).invoke(QUESTION)

    # Then it posted the model id to /v1/chat/completions with the key as a bearer token
    request = script.last_chat
    assert (request.method, request.path) == ("POST", "/v1/chat/completions")
    assert request.body["model"] == FAKE_FIREWORKS_MODEL
    assert request.header("authorization") == f"Bearer {FAKE_FIREWORKS_KEY}"


def test_bound_tools_are_sent_in_the_openai_tools_shape() -> None:
    # Given the fake answering with text
    script = FakeFireworksScript(rounds=[answering("ok")])
    with serving(script) as base:
        # When the runtime binds echo in its portable shape and a turn runs
        a_fireworks_model(base).bind_tools([ECHO_PORTABLE_TOOL]).invoke(QUESTION)

    # Then echo was offered as an OpenAI function tool
    assert script.last_chat.body["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "echo",
                "description": "Repeat the text back.",
                "parameters": ECHO_PARAMETERS,
            },
        }
    ]


# --- the reply --------------------------------------------------------------------------------


def test_a_tool_calls_reply_becomes_the_messages_tool_calls() -> None:
    # Given the fake calling echo
    script = FakeFireworksScript(rounds=[calling("echo", "call-1", text="surmap-ping")])
    with serving(script) as base:
        # When one turn runs
        reply = a_fireworks_model(base).bind_tools([ECHO_PORTABLE_TOOL]).invoke(QUESTION)

    # Then the caller sees echo's call with parsed arguments
    assert isinstance(reply, AIMessage)
    assert [(c["name"], c["id"], c["args"]) for c in reply.tool_calls] == [
        ("echo", "call-1", {"text": "surmap-ping"})
    ]


async def test_a_streamed_tool_call_arrives_whole_once_the_chunks_are_added() -> None:
    # Given the fake calling echo over SSE
    script = FakeFireworksScript(rounds=[calling("echo", "call-1", text="surmap-ping")])
    with serving(script) as base:
        # When the runtime streams the reply
        whole = await streamed(a_fireworks_model(base), QUESTION)

    # Then the request streamed, and the added chunks carry echo's call
    assert script.last_chat.body["stream"] is True
    assert [(c["name"], c["args"]) for c in whole.tool_calls] == [("echo", {"text": "surmap-ping"})]


async def test_streamed_text_arrives_as_the_answer() -> None:
    # Given the fake answering with text over SSE
    script = FakeFireworksScript(rounds=[answering("The tiny scene is ready.")])
    with serving(script) as base:
        # When the runtime streams the reply
        whole = await streamed(a_fireworks_model(base), QUESTION)

    # Then the text is the answer
    assert whole.text == "The tiny scene is ready."


# --- usage and budget -------------------------------------------------------------------------


def test_a_response_s_usage_is_recorded_under_fireworks() -> None:
    # Given the fake answering with 30 prompt and 4 completion tokens
    sink = RecordingSink()
    script = FakeFireworksScript(rounds=[answering("ok", prompt_tokens=30, completion_tokens=4)])
    with serving(script) as base:
        # When one turn runs
        fireworks_chat_model(
            FAKE_FIREWORKS_MODEL, api_key=FAKE_FIREWORKS_KEY, base_url=base, usage_sink=sink
        ).invoke(QUESTION)

    # Then one record names Fireworks, the model and the counts
    assert [(r.provider, r.model, r.input_tokens, r.output_tokens) for r in sink.records] == [
        ("fireworks", FAKE_FIREWORKS_MODEL, 30, 4)
    ]


async def test_a_streamed_response_s_usage_is_recorded_once(tmp_path: Path) -> None:
    # Given a ledger and the fake answering over SSE
    ledger = UsageLedger(tmp_path / "usage.jsonl")
    script = FakeFireworksScript(rounds=[answering("ok", prompt_tokens=30, completion_tokens=4)])
    with serving(script) as base:
        # When the runtime streams one reply
        await streamed(a_fireworks_model(base, usage_sink=ledger), QUESTION)

    # Then usage was asked for, and the ledger counts that one call and its tokens
    assert script.last_chat.body["stream_options"] == {"include_usage": True}
    assert (ledger.calls("fireworks"), ledger.total_tokens("fireworks")) == (1, 34)


def test_a_spent_budget_refuses_before_any_request(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given a Fireworks budget of zero calls
    monkeypatch.setenv("SURMAP_BUDGET_FIREWORKS_CALLS", "0")
    ledger = UsageLedger(tmp_path / "usage.jsonl")
    script = FakeFireworksScript(rounds=[answering("ok")])
    with serving(script) as base:
        model = a_fireworks_model(base, usage_sink=ledger, before_call=ledger)

        # When the agent calls it, then the budget refuses
        with pytest.raises(BudgetExceeded):
            model.invoke(QUESTION)

    # And nothing reached Fireworks
    assert script.chat_requests == []


# --- errors and the key -----------------------------------------------------------------------


def test_a_401_reads_as_a_key_problem_and_does_not_contain_the_key() -> None:
    # Given the fake refusing the key
    script = FakeFireworksScript(status=401)
    with serving(script) as base:
        # When one turn runs, then it fails naming the variable to check
        with pytest.raises(FireworksError, match="FIREWORKS_API_KEY") as raised:
            a_fireworks_model(base).invoke(QUESTION)

    # And the error carries the status but not the key
    assert "401" in str(raised.value)
    assert FAKE_FIREWORKS_KEY not in str(raised.value)
    assert raised.value.__cause__ is None


async def test_a_500_names_its_status_and_not_the_key() -> None:
    # Given the fake failing
    script = FakeFireworksScript(status=500)
    with serving(script) as base:
        # When the runtime streams a turn, then it fails with the status
        with pytest.raises(FireworksError, match="500") as raised:
            await streamed(a_fireworks_model(base), QUESTION)

    # And neither the error nor its context holds the key
    assert FAKE_FIREWORKS_KEY not in str(raised.value)
    assert raised.value.__cause__ is None


def test_a_missing_key_is_refused_before_any_request() -> None:
    # Given a Fireworks model without a key
    script = FakeFireworksScript(rounds=[answering("ok")])
    with serving(script) as base:
        model = a_fireworks_model(base, api_key="  ")

        # When one turn runs, then it is refused naming the variable
        with pytest.raises(FireworksError, match="FIREWORKS_API_KEY is not set"):
            model.invoke(QUESTION)

    # And nothing was sent
    assert script.requests == []


def test_a_cleartext_url_off_loopback_is_refused() -> None:
    # When the base URL is plain http on another host, then it is refused
    with pytest.raises(FireworksError, match="https"):
        fireworks_base_url("http://fireworks.example.net/inference/v1")


def test_the_model_s_repr_never_shows_the_key() -> None:
    # Given a keyed Fireworks model (no request is made)
    model = fireworks_chat_model(FAKE_FIREWORKS_MODEL, api_key=FAKE_FIREWORKS_KEY)

    # When it is printed, then the key is not in it
    assert FAKE_FIREWORKS_KEY not in repr(model)


# --- live -------------------------------------------------------------------------------------


@pytest.mark.skipif(
    os.environ.get("SURMAP_LIVE_FIREWORKS") != "1",
    reason="set SURMAP_LIVE_FIREWORKS=1 (and FIREWORKS_API_KEY in the shell or .env) to call it",
)
def test_a_live_fireworks_turn_calls_echo_and_answers_with_its_result() -> None:
    # Given a Fireworks model keyed from the shell or the project .env, recording credits
    load_env()
    key = os.environ.get("FIREWORKS_API_KEY", "").strip()
    if not key:
        pytest.skip("FIREWORKS_API_KEY is not set in the shell or .env")
    model = fireworks_chat_model(
        os.environ.get("SURMAP_FIREWORKS_MODEL", FAKE_FIREWORKS_MODEL),
        api_key=key,
        base_url=os.environ.get("SURMAP_FIREWORKS_URL") or None,
        usage_sink=UsageLedger(),
    )

    # When it is offered echo and then given the result of its call
    trip = round_trip(model)

    # Then it called echo and answered with what echo returned
    assert trip.call.tool_calls[0]["name"] == "echo"
    assert "surmap-ping" in trip.answer.text
