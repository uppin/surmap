"""The agent's persisted state: conversations in SQLite, so a container restart keeps them.

A restart is a new `SqliteConversationStore` (and a new `ChatHub`) over the same file —
exactly what a fresh Modal container does when it mounts the agent's Volume. The model is
n4's `ScriptedChatModel`; no tools are bound, so only persistence is under test.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from surmap.agent.__main__ import config_from_args
from surmap.agent.llm.registry import ModelInfo
from surmap.agent.proto import chat_pb2
from surmap.agent.runtime.session import SqliteConversationStore
from surmap.agent.server.app import AgentServerConfig, conversation_store, usage_log_path
from surmap.agent.server.hub import ChatHub
from tests.agent_fakes import ScriptedChatModel, answer
from tests.agent_server_fakes import SCRIPTED_MODEL_ID

CONVERSATION = "conv-restart"


def a_store(path: Path) -> SqliteConversationStore:
    return SqliteConversationStore(path)


def a_hub(store: SqliteConversationStore, model: ScriptedChatModel) -> ChatHub:
    return ChatHub(
        model_factory=lambda _model_id: model,
        tools=lambda _runner: [],
        models=lambda: [ModelInfo(SCRIPTED_MODEL_ID, "ollama", "scripted")],
        default_model_id=SCRIPTED_MODEL_ID,
        store=store,
    )


def test_a_stores_history_survives_being_reopened(tmp_path: Path) -> None:
    # Given a conversation with a human message, a tool call and its answer, stored on disk
    db_path = tmp_path / "conversations.sqlite"
    store = a_store(db_path)
    store.append(
        CONVERSATION,
        [
            HumanMessage(content="run the demo", additional_kwargs={"surmap_kind": "steer"}),
            AIMessage(
                content="",
                tool_calls=[{"name": "run_demo", "args": {}, "id": "call-1", "type": "tool_call"}],
            ),
            ToolMessage(content="done", tool_call_id="call-1", name="run_demo"),
        ],
    )
    store.close()

    # When the store is reopened, as a restarted container reopens it
    reopened = a_store(db_path)

    # Then every message comes back, kinds, tool calls and ids intact
    history = reopened.history(CONVERSATION)
    assert [type(message) for message in history] == [HumanMessage, AIMessage, ToolMessage]
    assert history[0].content == "run the demo"
    assert history[0].additional_kwargs == {"surmap_kind": "steer"}
    ai_message = history[1]
    assert isinstance(ai_message, AIMessage)
    assert ai_message.tool_calls[0]["id"] == "call-1"
    tool_message = history[2]
    assert isinstance(tool_message, ToolMessage)
    assert tool_message.tool_call_id == "call-1"
    reopened.close()


def test_conversations_in_one_store_do_not_leak_into_each_other(tmp_path: Path) -> None:
    # Given two conversations in one store
    store = a_store(tmp_path / "conversations.sqlite")
    store.append("conv-a", [HumanMessage(content="for a")])
    store.append("conv-b", [HumanMessage(content="for b")])

    # Then each history holds only its own messages, and an unknown one is empty
    assert [message.content for message in store.history("conv-a")] == ["for a"]
    assert [message.content for message in store.history("conv-b")] == ["for b"]
    assert store.history("conv-never-opened") == []
    store.close()


def test_a_stores_model_and_replay_events_survive_being_reopened(tmp_path: Path) -> None:
    # Given a conversation whose model and two replay events were recorded
    db_path = tmp_path / "conversations.sqlite"
    store = a_store(db_path)
    event = chat_pb2.TurnEvent(conversation_id=CONVERSATION, turn_id="t-1", seq=1)
    store.remember_model(CONVERSATION, "ollama:scripted")
    store.record_event(CONVERSATION, event.SerializeToString())
    store.close()

    # When the store is reopened
    reopened = a_store(db_path)

    # Then the model and the event bytes come back; an unknown conversation has neither
    assert reopened.model_id(CONVERSATION) == "ollama:scripted"
    assert reopened.events(CONVERSATION) == [event.SerializeToString()]
    assert reopened.model_id("conv-never-opened") is None
    assert reopened.events("conv-never-opened") == []
    reopened.close()


async def test_a_conversation_survives_a_hub_restart(tmp_path: Path) -> None:
    # Given one turn streamed through a hub over a SQLite store
    db_path = tmp_path / "conversations.sqlite"
    first_model = ScriptedChatModel.replying(answer("first answer"))
    first_hub = a_hub(a_store(db_path), first_model)
    first_events = [
        event
        async for event in first_hub.stream_turn(CONVERSATION, "hello", model_id=SCRIPTED_MODEL_ID)
    ]
    await first_hub.close()

    # When a new hub opens over the same file, as a restarted container does
    second_model = ScriptedChatModel.replying(answer("second answer"))
    second_hub = a_hub(a_store(db_path), second_model)

    # Then the conversation is restored: replay, model and message history intact
    restored = second_hub.get(CONVERSATION)
    assert restored is not None
    assert restored.events == first_events
    assert restored.model_id == SCRIPTED_MODEL_ID

    # And the next turn sees the first turn in the history the model is called with
    async for _event in second_hub.stream_turn(CONVERSATION, "again"):
        pass
    history = second_model.history_of_call(1)
    assert [message.content for message in history[:3]] == ["hello", "first answer", "again"]
    await second_hub.close()


def test_the_agent_config_carries_a_conversations_db(tmp_path: Path) -> None:
    # Given the agent command line naming a conversations DB
    db_path = tmp_path / "conversations.sqlite"

    # When the config is built from it
    config = config_from_args(["--conversations-db", str(db_path)])

    # Then the config carries the path, and the store it builds is the SQLite one
    assert config.conversations_db == db_path
    store = conversation_store(config)
    assert isinstance(store, SqliteConversationStore)
    store.close()


def test_a_config_with_no_conversations_db_nor_state_dir_keeps_conversations_in_memory() -> None:
    # Given a config with neither, as tests and embedders build it
    config = AgentServerConfig()

    # Then no SQLite store is built
    assert config.conversations_db is None
    assert conversation_store(config) is None


def test_the_usage_log_follows_the_cache_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given a cache dir and no `$SURMAP_USAGE_LOG`
    monkeypatch.delenv("SURMAP_USAGE_LOG", raising=False)

    # Then the ledger the server builds writes under the cache dir (the Volume, on Modal)
    assert usage_log_path(AgentServerConfig(cache_dir=tmp_path)) == tmp_path / "usage.jsonl"


def test_an_explicit_usage_log_env_still_wins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given `$SURMAP_USAGE_LOG` set and a cache dir
    configured = tmp_path / "credits.jsonl"
    monkeypatch.setenv("SURMAP_USAGE_LOG", str(configured))

    # Then the configured path wins over the cache dir
    assert usage_log_path(AgentServerConfig(cache_dir=tmp_path / "cache")) == configured


def test_without_a_cache_dir_the_usage_log_stays_in_the_home_surmap_dir(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given neither `$SURMAP_USAGE_LOG` nor a cache dir
    monkeypatch.delenv("SURMAP_USAGE_LOG", raising=False)

    # Then the ledger keeps its State A home (local runs are unchanged)
    assert usage_log_path(AgentServerConfig()) == Path.home() / ".surmap" / "usage.jsonl"
