---
name: repo-maintenance
description: Maintain repository-level knowledge, operational docs, and local tooling context. Use when the user wants to update repo guidance, create or capture knowledge-base material, inspect MCP server setup, test MCP servers, or triage a technical backlog item.
---

# Repo Maintenance

Handle cross-cutting repository upkeep.

## Workflow

1. Determine whether the task is documentation, tooling, or backlog oriented.
Choose the smallest repo-wide action that satisfies the request.

2. Keep repo knowledge current.
Create or update KB entries, preserve important conversation context when asked, and refresh rule or guidance material carefully.

3. Inspect local MCP/tooling health.
Check what MCP servers exist, whether they work, and where the setup is likely to fail.

4. Support technical backlog triage.
Turn vague follow-up work into concrete items with enough context to act on later.

## Use These Source Prompts

- `.agents/commands/create-kb.md`
- `.agents/commands/persist-full-conversation.md`
- `.agents/commands/update-all-rules.md`
- `.agents/commands/tech-backlog.md`
- `.agents/commands/inspect-ide-mcp-servers.md`
- `.agents/commands/test-mcp.md`

## References

Read these only when needed:

- `references/ALL-RULES.md`
- `references/logging.md`
