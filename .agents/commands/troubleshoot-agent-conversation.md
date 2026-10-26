---
description: Reconstruct a Agent conversation from a session URL or session ID — turns, tool calls, nested RPCs, and  Request IDs — then hand off to /trace-request
---

# Troubleshoot Agent Conversation

Reconstruct what a Agent session did — user turns, tool calls (including nested `invoke_rpc` methods), assets, and the ** Request IDs** those turns used — then hand a chosen ID to `/trace-request`.

`$ARGUMENTS` is a session admin URL or UUID, optionally followed by a question.

```
/troubleshoot-agent-conversation <sessionUrl-or-sessionId> [question]
```

Examples:

- `<service-url>`
- `33145604-55e4-4879-8447-05d344ef6bcd which request IDs are icon generation?`

Peer of **`/trace-request`**: that command starts from a request ID; this one starts from a conversation and *produces* request IDs.

## Mandatory first step

Read and execute the skill (source of truth for phases, MCP tools, truncation rules, and the report template):

- `.agents/skills/troubleshoot-agent-conversation/SKILL.md`

Do not improvise a parallel procedure. Follow the skill's phases in order.

## Execution contract

1. Parse a UUID from `$ARGUMENTS` (URL or bare id) and state the question (default: reconstruct + collect request IDs).
2. Auth `@mcp-s/cli`, then query **`app-agent`** Admin APIs for session meta, tool/entry aggregates, and assets.
3. Treat large dumps as truncated (~100k). Get the complete turn → request ID list from Grafana (`Start duplexer turn for session <id>` on `surmap.onboard.session`).
4. Rebuild the conversation per-turn (`query_session_timeline` with `turnId`). For `invoke_rpc`, read `[invoke_rpc] request` `data` (`service` / `method` / `requestJson`).
5. Answer the question. List  Request IDs (`epoch.digits` only). Trace with `/trace-request` only the IDs the question needs.

## Catalog pointers

- Skill: [.agents/skills/troubleshoot-agent-conversation/SKILL.md](../skills/troubleshoot-agent-conversation/SKILL.md)
- Next hop: `/trace-request <requestId> <question>`
