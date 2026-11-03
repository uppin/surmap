# 2026-11-03 — tool images reach the model as image parts, not a placeholder

**Category:** Deferred scope
**Source:** `docs/surmap/1-WIP/2026-11-03-agent-chat-server.md` (PR #84, stack `#survey-agent` node 8/9)
**Packages:** surmap
**Consent:** Supervisor decision for the n8 wrap (2026-11-03): "Tool images reach the model as a placeholder: record a TODO for the sweep (real image parts in tool results; needs runtime support)"
**Status:** Open

## What is left

`src/surmap/agent/server/binding.py` returns a tool response's `image` bytes as a `ToolImage`; the
chat stream carries the bytes (`ToolCallFinished.image` / `media_type`), but the model reads only the
text `<image/jpeg, N bytes, shown to the user>`. The runtime (`surmap.agent.runtime`, n4) builds tool
messages as JSON text; it needs to emit an image content part for a `ToolImage` (for providers that
accept images in tool results, with the placeholder kept for the rest), then the binding test asserts
the model sees the image.

## Why it could not be done now

The tool-message construction is n4's runtime module; this node does not edit it. Provider support
for images in tool results differs (Ollama, Meta Responses) and needs its own tests there.

## History

| Date | Event |
|---|---|
| 2026-11-03 | Recorded at the n8 wrap (#84); assigned to the `#survey-agent` sweep node |
