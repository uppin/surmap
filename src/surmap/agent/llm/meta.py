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

import asyncio
import json
import os
import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Literal, cast

from langchain_core.callbacks import AsyncCallbackManagerForLLMRun, CallbackManagerForLLMRun
from langchain_core.language_models import LanguageModelInput
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    InvalidToolCall,
    SystemMessage,
    ToolCall,
    ToolMessage,
    UsageMetadata,
)
from langchain_core.messages.ai import OutputTokenDetails
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import Field, SecretStr, SkipValidation

from surmap.labelling.meta_muse import (
    META_MODEL_API_BASE_URL,
    MetaMuseSceneError,
    MetaMuseTransport,
    UrllibMetaMuseTransport,
)
from surmap.usage import UsageRecord, UsageSink

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

_KEY_ENV = "MODEL_API_KEY"
_REPLY_ATTEMPTS = 2
"""One request, then one retry when Muse returns neither text nor a tool call."""


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
        if tool_choice is not None:
            raise ValueError("MetaResponsesChatModel does not send tool_choice; Muse decides")
        return self.bind(tools=[_responses_tool(tool) for tool in tools], **kwargs)

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        headers = {"Authorization": f"Bearer {self._bearer()}"}
        base = self.base_url.rstrip("/")
        offered = cast(Sequence[Mapping[str, object]], kwargs.get("tools") or ())
        body = responses_request(
            messages,
            offered,
            model=self.model,
            effort=self.reasoning_effort,
            max_output_tokens=self.max_output_tokens,
        )
        for _ in range(_REPLY_ATTEMPTS):
            message = self._reply(f"{base}/responses", headers, body)
            if message.content or message.tool_calls or message.invalid_tool_calls:
                return ChatResult(generations=[ChatGeneration(message=message)])
        raise MetaResponsesError(
            f"Meta Responses returned no output text or tool call after {_REPLY_ATTEMPTS} attempts"
        )

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        sync_run = run_manager.get_sync() if run_manager is not None else None
        return await asyncio.to_thread(self._generate, messages, stop, sync_run, **kwargs)

    def _bearer(self) -> str:
        configured = (
            self.api_key.get_secret_value()
            if self.api_key is not None
            else os.environ.get(_KEY_ENV, "")
        )
        key = configured.strip()
        if not key:
            raise MetaResponsesError(f"{_KEY_ENV} is not set")
        return key

    def _reply(self, url: str, headers: Mapping[str, str], body: Mapping[str, object]) -> AIMessage:
        transport = self.transport if self.transport is not None else UrllibMetaMuseTransport()
        try:
            payload = transport.post_json(url, headers, body)
        except MetaMuseSceneError as exc:
            raise MetaResponsesError(str(exc)) from exc
        self._record_usage(payload)
        return parse_responses(payload, requested_model=self.model)

    def _record_usage(self, payload: Mapping[str, object]) -> None:
        counts = _token_counts(payload.get("usage"))
        if self.usage_sink is None or counts is None:
            return
        input_tokens, output_tokens, reasoning_tokens = counts
        self.usage_sink(
            UsageRecord(
                provider=META_PROVIDER,
                model=self.model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                reasoning_tokens=reasoning_tokens,
                t_unix=time.time(),
            )
        )


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
    instructions = [_text(m.content) for m in messages if isinstance(m, SystemMessage)]
    items: list[dict[str, object]] = []
    for message in messages:
        if not isinstance(message, SystemMessage):
            items.extend(_input_items(message))
    body: dict[str, object] = {"model": model}
    if instructions:
        body["instructions"] = "\n\n".join(instructions)
    body["input"] = items
    if tools:
        body["tools"] = [dict(tool) for tool in tools]
    body["stream"] = False
    body["reasoning"] = {"effort": effort}
    body["max_output_tokens"] = max_output_tokens
    return body


def parse_responses(body: Mapping[str, object], *, requested_model: str) -> AIMessage:
    """The `AIMessage` a Responses body carries; `requested_model` names it when the body does not.

    Raises `MetaResponsesError` when the body has no `output` list.
    """
    output = body.get("output")
    if not isinstance(output, list):
        raise MetaResponsesError("Meta Responses body has no output list")
    texts: list[str] = []
    tool_calls: list[ToolCall] = []
    invalid_calls: list[InvalidToolCall] = []
    for item in output:
        if not isinstance(item, Mapping):
            continue
        if item.get("type") == "message":
            texts.extend(_output_texts(item))
        elif item.get("type") == "function_call":
            name = str(item.get("name", ""))
            call_id = item.get("call_id")
            call_id_text = call_id if isinstance(call_id, str) else None
            args = _arguments(item.get("arguments"))
            if args is None:
                raw = item.get("arguments")
                invalid_calls.append(
                    InvalidToolCall(
                        type="invalid_tool_call",
                        name=name,
                        args=raw if isinstance(raw, str) else None,
                        id=call_id_text,
                        error="function arguments are not a JSON object",
                    )
                )
            else:
                tool_calls.append(ToolCall(name=name, args=args, id=call_id_text, type="tool_call"))
    model_name = body.get("model")
    return AIMessage(
        content="".join(texts).strip(),
        tool_calls=tool_calls,
        invalid_tool_calls=invalid_calls,
        usage_metadata=_usage_metadata(body.get("usage")),
        response_metadata={
            "model_name": model_name if isinstance(model_name, str) else requested_model
        },
    )


def _responses_tool(
    tool: dict[str, Any] | type | Callable[..., Any] | BaseTool,
) -> dict[str, object]:
    """A bound tool as a flat Responses function tool."""
    function = cast(Mapping[str, object], convert_to_openai_tool(tool)["function"])
    return {
        "type": "function",
        "name": function["name"],
        "description": function.get("description", ""),
        "parameters": function.get("parameters", {"type": "object", "properties": {}}),
        "strict": False,
    }


def _input_items(message: BaseMessage) -> list[dict[str, object]]:
    """The Responses input items one LangChain message becomes, in order."""
    if isinstance(message, HumanMessage):
        return [{"type": "message", "role": "user", "content": _user_parts(message.content)}]
    if isinstance(message, AIMessage):
        items: list[dict[str, object]] = []
        text = _text(message.content)
        if text:
            items.append(
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": text}],
                }
            )
        for call in message.tool_calls:
            items.append(
                {
                    "type": "function_call",
                    "call_id": call["id"],
                    "name": call["name"],
                    "arguments": json.dumps(call["args"]),
                }
            )
        return items
    if isinstance(message, ToolMessage):
        return [
            {
                "type": "function_call_output",
                "call_id": message.tool_call_id,
                "output": _text(message.content),
            }
        ]
    raise ValueError(f"Meta Responses cannot send a {message.type} message")


def _user_parts(content: str | list[str | dict[str, Any]]) -> list[dict[str, object]]:
    """A human message's content as Responses `input_text` and `input_image` parts."""
    if isinstance(content, str):
        return [{"type": "input_text", "text": content}]
    parts: list[dict[str, object]] = []
    for block in content:
        if isinstance(block, str):
            parts.append({"type": "input_text", "text": block})
        elif block.get("type") == "text":
            parts.append({"type": "input_text", "text": block.get("text", "")})
        elif block.get("type") == "image":
            data_url = f"data:{block['mime_type']};base64,{block['base64']}"
            parts.append({"type": "input_image", "image_url": data_url})
        elif block.get("type") == "image_url":
            image = block["image_url"]
            parts.append(
                {
                    "type": "input_image",
                    "image_url": image["url"] if isinstance(image, dict) else image,
                }
            )
        else:
            raise ValueError(f"Meta Responses cannot send a {block.get('type')!r} content block")
    return parts


def _text(content: str | list[str | dict[str, Any]]) -> str:
    """The text of a message's content, with non-text blocks left out."""
    if isinstance(content, str):
        return content
    texts: list[str] = []
    for block in content:
        if isinstance(block, str):
            texts.append(block)
        elif block.get("type") == "text":
            texts.append(str(block.get("text", "")))
    return "".join(texts)


def _output_texts(message: Mapping[str, object]) -> list[str]:
    content = message.get("content")
    if not isinstance(content, list):
        return []
    texts: list[str] = []
    for part in content:
        if isinstance(part, Mapping) and part.get("type") == "output_text":
            text = part.get("text")
            if isinstance(text, str):
                texts.append(text)
    return texts


def _arguments(raw: object) -> dict[str, Any] | None:
    """A function call's arguments as a JSON object, or `None` when they are not one."""
    try:
        decoded: object = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError:
        return None
    return decoded if isinstance(decoded, dict) else None


def _token_counts(usage: object) -> tuple[int, int, int | None] | None:
    """Input, output and reasoning tokens of a usage block, when it has both input and output."""
    if not isinstance(usage, Mapping):
        return None
    input_tokens = _count(usage.get("input_tokens"))
    output_tokens = _count(usage.get("output_tokens"))
    if input_tokens is None or output_tokens is None:
        return None
    details = usage.get("output_tokens_details")
    reasoning = _count(details.get("reasoning_tokens")) if isinstance(details, Mapping) else None
    return input_tokens, output_tokens, reasoning


def _usage_metadata(usage: object) -> UsageMetadata | None:
    counts = _token_counts(usage)
    if counts is None:
        return None
    input_tokens, output_tokens, reasoning_tokens = counts
    metadata = UsageMetadata(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
    )
    if reasoning_tokens is not None:
        metadata["output_token_details"] = OutputTokenDetails(reasoning=reasoning_tokens)
    return metadata


def _count(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value
