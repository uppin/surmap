"""Which chat models the agent may use, and building one by id; plus the local Ollama model.

Every provider is a fake server on a real loopback socket (`tests/fake_meta.py`,
`tests/fake_fireworks.py`, `tests/fake_ollama.py`) reached through the adapters' real clients; the
environment is injected. The live test is gated on `SURMAP_LIVE_OLLAMA=1` with
`SURMAP_OLLAMA_MODEL` naming a tool-capable model `ollama list` holds.
"""

from __future__ import annotations

import os

import pytest
from langchain_ollama import ChatOllama
from pydantic import SecretStr

from surmap.agent.llm.fireworks import (
    DEFAULT_FIREWORKS_MODELS,
    FireworksChatModel,
    UrllibFireworksModelsTransport,
)
from surmap.agent.llm.meta import MetaResponsesChatModel
from surmap.agent.llm.registry import ChatModelRegistry, ModelInfo, UnknownModelProvider
from tests import fake_meta, fake_ollama
from tests.agent_llm_fakes import ECHO_PORTABLE_TOOL, round_trip
from tests.fake_fireworks import (
    FAKE_FIREWORKS_KEY,
    FakeFireworksScript,
    a_closed_base_url,
    serving,
)
from tests.fake_meta import FakeMetaScript
from tests.fake_ollama import FakeOllamaScript, a_closed_ollama_url

REGISTRY_KEY = "sk-registry-key"
MUSE_WONDER = ModelInfo(id="meta:muse-wonder-1.0", provider="meta", model="muse-wonder-1.0")
LLAMA = ModelInfo(id="ollama:llama3.2:3b", provider="ollama", model="llama3.2:3b")
QWEN_VL = ModelInfo(id="ollama:qwen2.5vl:7b", provider="ollama", model="qwen2.5vl:7b")
FW_LLAMA = "accounts/fireworks/models/llama-v3p3-70b-instruct"
FW_QWEN = "accounts/fireworks/models/qwen3-235b-a22b"


def on_fireworks(model: str) -> ModelInfo:
    return ModelInfo(id=f"fireworks:{model}", provider="fireworks", model=model)


def a_registry(
    *,
    environ: dict[str, str] | None = None,
    ollama: str | None = None,
    meta: str | None = None,
) -> ChatModelRegistry:
    """A registry over `environ`, the Ollama server at `ollama` (else a stopped one) and Muse at
    `meta` (else the Meta Model API, never called here)."""
    return ChatModelRegistry(
        environ={"SURMAP_OLLAMA_URL": ollama or a_closed_ollama_url(), **(environ or {})},
        meta_base_url=meta,
        fireworks_transport=UrllibFireworksModelsTransport(timeout_s=2.0),
    )


# --- available ------------------------------------------------------------------------------


def test_a_keyed_environment_lists_muse_wonder() -> None:
    # Given MODEL_API_KEY is set and no Ollama server runs
    registry = a_registry(environ={"MODEL_API_KEY": REGISTRY_KEY})

    # When the available models are listed
    listed = registry.available()

    # Then Muse Wonder is the one model
    assert listed == (MUSE_WONDER,)


def test_without_a_model_api_key_muse_is_not_listed() -> None:
    # Given no MODEL_API_KEY and an Ollama server holding llama3.2:3b
    with fake_ollama.serving(FakeOllamaScript(held_models=["llama3.2:3b"])) as ollama:
        registry = a_registry(ollama=ollama)

        # When the available models are listed
        listed = registry.available()

    # Then only the local model is offered
    assert listed == (LLAMA,)


def test_the_agent_meta_model_variable_names_the_listed_muse_model() -> None:
    # Given a keyed environment that picks Muse Spark for the agent
    registry = a_registry(
        environ={"MODEL_API_KEY": REGISTRY_KEY, "SURMAP_AGENT_META_MODEL": "muse-spark-1.3"}
    )

    # When the available models are listed
    listed = registry.available()

    # Then Muse Spark is listed in place of Muse Wonder
    assert listed == (ModelInfo(id="meta:muse-spark-1.3", provider="meta", model="muse-spark-1.3"),)


def test_muse_is_listed_before_every_model_the_ollama_server_holds() -> None:
    # Given a key and an Ollama server holding two models
    script = FakeOllamaScript(held_models=["llama3.2:3b", "qwen2.5vl:7b"])
    with fake_ollama.serving(script) as ollama:
        registry = a_registry(environ={"MODEL_API_KEY": REGISTRY_KEY}, ollama=ollama)

        # When the available models are listed
        listed = registry.available()

    # Then Muse comes first, then the local models in the server's order
    assert listed == (MUSE_WONDER, LLAMA, QWEN_VL)


def test_a_stopped_ollama_server_lists_no_local_models() -> None:
    # Given no key and an Ollama server that does not answer
    registry = a_registry(ollama=a_closed_ollama_url())

    # When the available models are listed
    listed = registry.available()

    # Then nothing is offered, and listing did not fail
    assert listed == ()


def test_the_tags_are_asked_of_the_configured_ollama_server() -> None:
    # Given SURMAP_OLLAMA_URL points at a second local server
    script = FakeOllamaScript(held_models=["llama3.2:3b"])
    with fake_ollama.serving(script) as ollama:
        registry = a_registry(environ={"SURMAP_OLLAMA_URL": ollama})

        # When the available models are listed
        registry.available()

    # Then that server's /api/tags was asked, once
    assert [(r.method, r.path) for r in script.requests] == [("GET", "/api/tags")]


# --- available: Fireworks -------------------------------------------------------------------


def test_without_a_fireworks_key_no_fireworks_model_is_listed() -> None:
    # Given a Fireworks model list but no FIREWORKS_API_KEY
    registry = a_registry(environ={"SURMAP_FIREWORKS_MODELS": FW_LLAMA})

    # When the available models are listed
    listed = registry.available()

    # Then Fireworks offers nothing
    assert listed == ()


def test_a_keyed_environment_lists_the_fireworks_models_it_names() -> None:
    # Given a key and two comma-separated model ids, one padded, plus a blank entry
    registry = a_registry(
        environ={
            "FIREWORKS_API_KEY": FAKE_FIREWORKS_KEY,
            "SURMAP_FIREWORKS_MODELS": f"{FW_LLAMA}, {FW_QWEN},",
        }
    )

    # When the available models are listed
    listed = registry.available()

    # Then both are offered, ids keeping their slashes
    assert listed == (on_fireworks(FW_LLAMA), on_fireworks(FW_QWEN))


def test_without_a_model_list_the_endpoint_s_models_are_listed_with_the_key() -> None:
    # Given a key and a Fireworks endpoint serving one model
    script = FakeFireworksScript(served_models=[FW_QWEN])
    with serving(script) as base:
        registry = a_registry(
            environ={"FIREWORKS_API_KEY": FAKE_FIREWORKS_KEY, "SURMAP_FIREWORKS_URL": base}
        )

        # When the available models are listed
        listed = registry.available()

    # Then the endpoint's model is offered, asked with the bearer key
    assert listed == (on_fireworks(FW_QWEN),)
    asked = script.requests[0]
    assert (asked.method, asked.path) == ("GET", "/v1/models")
    assert asked.header("Authorization") == f"Bearer {FAKE_FIREWORKS_KEY}"


def test_an_unreachable_endpoint_lists_the_built_in_fireworks_models() -> None:
    # Given a key and a Fireworks URL nothing listens on
    registry = a_registry(
        environ={
            "FIREWORKS_API_KEY": FAKE_FIREWORKS_KEY,
            "SURMAP_FIREWORKS_URL": a_closed_base_url(),
        }
    )

    # When the available models are listed
    listed = registry.available()

    # Then the built-in tool-capable models are offered
    assert listed == tuple(on_fireworks(model) for model in DEFAULT_FIREWORKS_MODELS)


def test_muse_comes_first_then_fireworks_then_the_local_models() -> None:
    # Given both keys and an Ollama server holding one model
    with fake_ollama.serving(FakeOllamaScript(held_models=["llama3.2:3b"])) as ollama:
        registry = a_registry(
            environ={
                "MODEL_API_KEY": REGISTRY_KEY,
                "FIREWORKS_API_KEY": FAKE_FIREWORKS_KEY,
                "SURMAP_FIREWORKS_MODELS": FW_LLAMA,
            },
            ollama=ollama,
        )

        # When the available models are listed
        listed = registry.available()

    # Then hosted models lead, Muse before Fireworks
    assert listed == (MUSE_WONDER, on_fireworks(FW_LLAMA), LLAMA)


# --- build ----------------------------------------------------------------------------------


def test_an_ollama_id_builds_chat_ollama_for_that_model() -> None:
    # Given a registry
    registry = a_registry()

    # When the id of a tagged model is built, split at its first colon only
    model = registry.build("ollama:llama3.2:3b")

    # Then it is ChatOllama for llama3.2:3b
    assert isinstance(model, ChatOllama)
    assert model.model == "llama3.2:3b"


def test_a_built_ollama_model_offers_the_agents_tools_to_ollama() -> None:
    # Given an Ollama model from the registry, on the fake Ollama server
    script = FakeOllamaScript(rounds=[fake_ollama.answering("ok")])
    with fake_ollama.serving(script) as ollama:
        model = a_registry(ollama=ollama).build("ollama:llama3.2:3b")

        # When the runtime binds echo in its provider-portable shape and a turn runs
        model.bind_tools([ECHO_PORTABLE_TOOL]).invoke("Echo surmap-ping.")

    # Then echo is the tool offered to Ollama
    assert script.last_chat.body["tools"] == [ECHO_PORTABLE_TOOL]


def test_a_built_ollama_model_talks_to_the_configured_server() -> None:
    # Given SURMAP_OLLAMA_URL points at a second local server
    script = FakeOllamaScript(rounds=[fake_ollama.answering("ok")])
    with fake_ollama.serving(script) as ollama:
        registry = a_registry(environ={"SURMAP_OLLAMA_URL": ollama})

        # When a turn runs on the Ollama model it builds
        model = registry.build("ollama:llama3.2:3b")
        model.invoke("Who is on the roof?")

    # Then that server was asked for llama3.2:3b
    assert isinstance(model, ChatOllama)
    assert (script.last_chat.path, script.last_chat.body["model"]) == ("/api/chat", "llama3.2:3b")


def test_a_meta_id_builds_muse_for_that_model() -> None:
    # Given a keyed registry
    registry = a_registry(environ={"MODEL_API_KEY": REGISTRY_KEY})

    # When a Muse Spark id is built
    model = registry.build("meta:muse-spark-1.3")

    # Then it is the Meta Responses model for muse-spark-1.3
    assert isinstance(model, MetaResponsesChatModel)
    assert model.model == "muse-spark-1.3"


def test_a_built_muse_model_answers_from_the_registry_s_base_url_with_its_key() -> None:
    # Given a keyed registry whose Muse base URL is the fake Meta server
    script = FakeMetaScript(rounds=[fake_meta.answering("Two people.")])
    with fake_meta.serving(script) as meta:
        registry = a_registry(environ={"MODEL_API_KEY": REGISTRY_KEY}, meta=meta)

        # When a turn runs on the Muse model it builds
        registry.build("meta:muse-wonder-1.0").invoke("Who is on the roof?")

    # Then the request reached that server, keyed from the registry's environment
    assert script.last_request.path == "/v1/responses"
    assert script.last_request.header("authorization") == f"Bearer {REGISTRY_KEY}"


def test_a_fireworks_id_builds_that_model_split_at_the_first_colon_only() -> None:
    # Given a keyed registry
    registry = a_registry(environ={"FIREWORKS_API_KEY": FAKE_FIREWORKS_KEY})

    # When a Fireworks id with a slashed model path is built
    model = registry.build(f"fireworks:{FW_LLAMA}")

    # Then it is the Fireworks model for that path on the default endpoint
    assert isinstance(model, FireworksChatModel)
    assert model.model_name == FW_LLAMA
    assert model.openai_api_base == "https://api.fireworks.ai/inference/v1"


def test_a_built_fireworks_model_holds_the_registry_key_as_a_secret() -> None:
    # Given a keyed registry
    registry = a_registry(environ={"FIREWORKS_API_KEY": FAKE_FIREWORKS_KEY})

    # When a Fireworks id is built
    model = registry.build(f"fireworks:{FW_LLAMA}")

    # Then the key is the registry's, held as a secret and never shown
    assert isinstance(model, FireworksChatModel)
    assert isinstance(model.openai_api_key, SecretStr)
    assert model.openai_api_key.get_secret_value() == FAKE_FIREWORKS_KEY
    assert FAKE_FIREWORKS_KEY not in repr(model)


def test_a_built_fireworks_model_talks_to_the_configured_url() -> None:
    # Given SURMAP_FIREWORKS_URL points at a local stub
    registry = a_registry(
        environ={
            "FIREWORKS_API_KEY": FAKE_FIREWORKS_KEY,
            "SURMAP_FIREWORKS_URL": "http://127.0.0.1:8999/v1/",
        }
    )

    # When a Fireworks id is built
    model = registry.build(f"fireworks:{FW_LLAMA}")

    # Then that model is served from there
    assert isinstance(model, FireworksChatModel)
    assert model.openai_api_base == "http://127.0.0.1:8999/v1"


def test_an_unknown_provider_is_refused_by_name() -> None:
    # Given a registry
    registry = a_registry()

    # When a Baseten id is built, then it is refused naming the provider
    with pytest.raises(UnknownModelProvider, match="baseten"):
        registry.build("baseten:muse-spark-open")


# --- live -----------------------------------------------------------------------------------


@pytest.mark.skipif(
    os.environ.get("SURMAP_LIVE_OLLAMA") != "1" or not os.environ.get("SURMAP_OLLAMA_MODEL"),
    reason="set SURMAP_LIVE_OLLAMA=1 and SURMAP_OLLAMA_MODEL to call a local Ollama model",
)
def test_a_live_ollama_turn_calls_echo() -> None:
    # Given the operator's tool-capable Ollama model, built through the registry
    model = ChatModelRegistry().build(f"ollama:{os.environ['SURMAP_OLLAMA_MODEL']}")

    # When it is offered echo and then given the result of its call
    trip = round_trip(model)

    # Then it called echo and answered with what echo returned
    assert trip.call.tool_calls[0]["name"] == "echo"
    assert "surmap-ping" in trip.answer.text
