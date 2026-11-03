"""Muse as a LangChain chat model over the Meta Responses API, with function tools.

No stock LangChain integration speaks Meta's Responses dialect, so SurMap owns one. The mapping is
two pure functions the model composes, so the offline tests pin it exactly:

- `responses_request` turns a history into one `POST /v1/responses` body: the system message
  becomes `instructions`; human and assistant text become `message` items (`input_text` /
  `output_text` parts); an image content block becomes an `input_image` part with a `data:` URL;
  each assistant tool call becomes a `function_call` item and each `ToolMessage` a
  `function_call_output` item carrying the same `call_id`; bound tools are sent as
  `{type: "function", name, description, parameters, strict: false}`.
- `parse_responses` turns a response body back into an `AIMessage`: `output_text` parts become
  the content, `function_call` items become `tool_calls` with parsed `arguments` (unparseable
  arguments become `invalid_tool_calls`), and `usage` becomes `usage_metadata`.

The endpoint, bearer header, `reasoning.effort` and `input_image` shape were checked live on
2026-10-28 (`surmap.labelling.meta_muse`). Function tools on that endpoint are **not** verified
yet: the `function_call` item shape follows the OpenAI-style Responses API until the live check
(`SURMAP_LIVE_META=1`) confirms it.

The key is read from `MODEL_API_KEY` at call time unless one is given; it goes only into the
`Authorization` header. Every response's usage is recorded as a `UsageRecord` for provider
`meta` in the injected usage sink (normally a `surmap.usage.UsageLedger`). A response with neither
text nor tool calls is requested once more, as `surmap.mapqa.client.MetaClient.complete` does.
Streaming yields one chunk per response; the endpoint's SSE streaming is a later change.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any, Literal

from langchain_core.callbacks import AsyncCallbackManagerForLLMRun, CallbackManagerForLLMRun
from langchain_core.language_models import LanguageModelInput
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from pydantic import Field, SecretStr, SkipValidation

from surmap.labelling.meta_muse import META_MODEL_API_BASE_URL, MetaMuseTransport
from surmap.usage import UsageSink

__all__ = [
    "AGENT_META_MODEL_ENV",
    "DEFAULT_AGENT_META_MODEL",
    "META_PROVIDER",
    "MetaResponsesChatModel",
    "MetaResponsesError",
    "ReasoningEffort",
    "parse_responses",
    "responses_request",
]

META_PROVIDER = "meta"
"""The provider name usage is recorded under, and the registry id prefix."""
DEFAULT_AGENT_META_MODEL = "muse-wonder-1.0"
AGENT_META_MODEL_ENV = "SURMAP_AGENT_META_MODEL"
"""Overrides the agent's Muse model id; read by the registry."""

ReasoningEffort = Literal["low", "medium", "high"]


class MetaResponsesError(RuntimeError):
    """A Meta Responses call could not be made, or its reply could not be read."""


class MetaResponsesChatModel(BaseChatModel):
    """Muse Wonder (by default) on `POST {base_url}/responses`, with function tools bound."""

    model: str = DEFAULT_AGENT_META_MODEL
    reasoning_effort: ReasoningEffort = "medium"
    max_output_tokens: int = 8192
    base_url: str = META_MODEL_API_BASE_URL
    api_key: SecretStr | None = None
    """`None` reads `MODEL_API_KEY` at call time."""
    transport: SkipValidation[MetaMuseTransport] | None = Field(default=None, exclude=True)
    """`None` uses the stdlib transport that refuses redirects."""
    usage_sink: SkipValidation[UsageSink] | None = Field(default=None, exclude=True)
    """Receives one `UsageRecord` per response; normally a `UsageLedger`."""

    @property
    def _llm_type(self) -> str:
        return "meta-responses"

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Callable[..., Any] | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable[LanguageModelInput, AIMessage]:
        """Bind tools as Responses function tools (`{type, name, description, parameters}`).

        Accepts `BaseTool`s and the provider-portable dicts the runtime hands over
        (`{"type": "function", "function": {name, description, parameters}}`).
        """
        raise NotImplementedError  # TODO(pr-5): implement

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        raise NotImplementedError  # TODO(pr-5): implement

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        raise NotImplementedError  # TODO(pr-5): implement


def responses_request(
    messages: Sequence[BaseMessage],
    tools: Sequence[Mapping[str, object]],
    *,
    model: str,
    effort: ReasoningEffort,
    max_output_tokens: int,
) -> dict[str, object]:
    """One non-streaming Responses body for `messages`, offering `tools` (already Responses tools).

    `instructions` is present only when the history has a system message, and `tools` only when
    at least one tool is bound.
    """
    raise NotImplementedError  # TODO(pr-5): implement


def parse_responses(body: Mapping[str, object], *, requested_model: str) -> AIMessage:
    """The `AIMessage` a Responses body carries; `requested_model` names it when the body does not.

    Raises `MetaResponsesError` when the body has no `output` list.
    """
    raise NotImplementedError  # TODO(pr-5): implement
