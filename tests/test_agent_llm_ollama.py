"""Local Ollama chat models and the model listing over the fake Ollama server on loopback.

`ChatOllama` (→ `ollama` → `httpx`) and `UrllibOllamaTagsTransport` send real bytes to
`tests/fake_ollama.py`; no Ollama server is needed. The live round trip is in
`tests/test_agent_llm_registry.py`, gated on `SURMAP_LIVE_OLLAMA=1`.
"""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage

from surmap.agent.llm.ollama import UrllibOllamaTagsTransport, ollama_chat_model, ollama_models
from tests.agent_llm_fakes import ECHO_PORTABLE_TOOL
from tests.fake_ollama import FakeOllamaScript, OllamaRound, answering, calling, serving

LLAMA = "llama3.2:3b"
QUESTION = "what demos can you run?"


async def streamed(base_url: str, text: str) -> AIMessageChunk:
    """The whole streamed reply of llama3.2:3b with echo bound, its chunks added."""
    model = ollama_chat_model(LLAMA, base_url=base_url).bind_tools([ECHO_PORTABLE_TOOL])
    whole: AIMessageChunk | None = None
    async for piece in model.astream([HumanMessage(text)]):
        assert isinstance(piece, AIMessageChunk)
        whole = piece if whole is None else whole + piece
    assert whole is not None, "nothing was streamed"
    return whole


# --- the request ------------------------------------------------------------------------------


def test_a_turn_posts_the_model_and_the_question_to_api_chat() -> None:
    # Given the fake answering with text
    script = FakeOllamaScript(rounds=[answering("Two scenes are ready.")])
    with serving(script) as base:
        # When one turn runs on llama3.2:3b
        ollama_chat_model(LLAMA, base_url=base).invoke(QUESTION)

    # Then it posted that model and the question to /api/chat, streaming
    request = script.last_chat
    assert (request.method, request.path) == ("POST", "/api/chat")
    assert (request.body["model"], request.body["stream"]) == (LLAMA, True)
    assert request.body["messages"] == [{"role": "user", "content": QUESTION}]


def test_no_key_is_sent_to_the_local_server() -> None:
    # Given the fake answering with text
    script = FakeOllamaScript(rounds=[answering("ok")])
    with serving(script) as base:
        # When one turn runs
        ollama_chat_model(LLAMA, base_url=base).invoke(QUESTION)

    # Then the request carries no Authorization header
    assert script.last_chat.header("authorization") is None


def test_the_runtimes_portable_tool_is_sent_as_an_ollama_function_tool() -> None:
    # Given the fake answering with text
    script = FakeOllamaScript(rounds=[answering("ok")])
    with serving(script) as base:
        # When the runtime binds echo in its provider-portable shape and a turn runs
        ollama_chat_model(LLAMA, base_url=base).bind_tools([ECHO_PORTABLE_TOOL]).invoke(QUESTION)

    # Then echo is the one function tool offered to Ollama
    assert script.last_chat.body["tools"] == [ECHO_PORTABLE_TOOL]


def test_a_tool_result_is_sent_back_as_a_tool_message() -> None:
    # Given a history in which the model called echo and the tool answered it
    call = AIMessage(content="", tool_calls=[{"name": "echo", "args": {"text": "hi"}, "id": "c1"}])
    history = [HumanMessage("Echo hi."), call, ToolMessage(content="hi", tool_call_id="c1")]
    script = FakeOllamaScript(rounds=[answering("It returned hi.")])
    with serving(script) as base:
        # When the next turn runs
        ollama_chat_model(LLAMA, base_url=base).bind_tools([ECHO_PORTABLE_TOOL]).invoke(history)

    # Then the call went back as the assistant's tool call, and its result as a tool message
    messages = script.last_chat.body["messages"]
    assert isinstance(messages, list)
    assert [m["role"] for m in messages] == ["user", "assistant", "tool"]
    assert messages[1]["tool_calls"][0]["function"] == {"name": "echo", "arguments": {"text": "hi"}}
    assert messages[2]["content"] == "hi"


# --- the reply --------------------------------------------------------------------------------


async def test_a_streamed_tool_call_reaches_the_caller_with_its_arguments() -> None:
    # Given the fake calling echo over newline-delimited JSON
    script = FakeOllamaScript(rounds=[calling("echo", text="surmap-ping")])
    with serving(script) as base:
        # When the runtime streams the reply
        whole = await streamed(base, QUESTION)

    # Then the added chunks carry echo's call with its arguments and an id to answer it by
    assert [(c["name"], c["args"]) for c in whole.tool_calls] == [("echo", {"text": "surmap-ping"})]
    assert whole.tool_calls[0]["id"]


async def test_streamed_text_arrives_as_the_answer_with_its_token_counts() -> None:
    # Given the fake answering in text with 30 prompt and 4 completion tokens
    script = FakeOllamaScript(
        rounds=[OllamaRound(content="The tiny scene is ready.", prompt_eval_count=30, eval_count=4)]
    )
    with serving(script) as base:
        # When the runtime streams the reply
        whole = await streamed(base, QUESTION)

    # Then the text is the answer and the counts are its usage
    assert whole.text == "The tiny scene is ready."
    assert whole.usage_metadata is not None
    assert (whole.usage_metadata["input_tokens"], whole.usage_metadata["output_tokens"]) == (30, 4)


def test_a_whole_reply_is_read_when_streaming_is_off() -> None:
    # Given the fake calling echo
    script = FakeOllamaScript(rounds=[calling("echo", text="surmap-ping")])
    with serving(script) as base:
        # When one turn runs with streaming off
        model = ollama_chat_model(LLAMA, base_url=base).bind_tools([ECHO_PORTABLE_TOOL])
        reply = model.invoke(QUESTION, stream=False)

    # Then the request did not stream, and the whole reply's tool call reached the caller
    assert script.last_chat.body["stream"] is False
    assert [(c["name"], c["args"]) for c in reply.tool_calls] == [("echo", {"text": "surmap-ping"})]


# --- the model listing ------------------------------------------------------------------------


def test_ollama_models_names_what_api_tags_lists_in_server_order() -> None:
    # Given an Ollama server holding two models
    script = FakeOllamaScript(held_models=["qwen2.5vl:7b", LLAMA])
    with serving(script) as base:
        # When its models are read
        names = ollama_models(UrllibOllamaTagsTransport(), base_url=base)

    # Then both names come back in the server's order, from one GET /api/tags
    assert names == ("qwen2.5vl:7b", LLAMA)
    assert [(r.method, r.path) for r in script.requests] == [("GET", "/api/tags")]


def test_a_failing_tags_endpoint_lists_no_models() -> None:
    # Given an Ollama server whose /api/tags fails
    script = FakeOllamaScript(held_models=[LLAMA], tags_status=500)
    with serving(script) as base:
        # When its models are read
        names = ollama_models(UrllibOllamaTagsTransport(), base_url=base)

    # Then nothing is listed, and listing did not fail
    assert names == ()


def test_an_ollama_model_defaults_to_the_loopback_server(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given SURMAP_OLLAMA_URL is not set
    monkeypatch.delenv("SURMAP_OLLAMA_URL", raising=False)

    # When an Ollama chat model is made
    model = ollama_chat_model(LLAMA)

    # Then it talks to Ollama's loopback default
    assert model.base_url == "http://127.0.0.1:11434"
