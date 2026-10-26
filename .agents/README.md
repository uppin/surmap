# Agents Guide

`.agents/` is the **single canonical home** for this repo's assistant guidance.
Muse reads the same files through the symlinks in `.muse/`:

- `.muse/skills` → `../.agents/skills`
- `.muse/commands` → `../.agents/commands`

Write changes **here**, never in `.muse/` — a regular file appearing in either
of those directories is unmigrated drift.

## Layout

- `.agents/commands/*.md` → slash-command entrypoints (`/green`, `/pr-wrap`, `/plan-red`, …)
- `.agents/skills/*/SKILL.md` → reusable workflows; `references/` holds supporting guidance
- `.agents/mcp.json` → repo-local MCP configuration reference (generic servers only)

## Provenance

Imported from another project's `.agents/` tree and genericized for SurMap:
product, company and internal-infrastructure names were replaced with generic
equivalents (`CI`, `E2E framework`, `Roadmap tracker`,
`surmap.*` artifacts, `<service-host>` hosts). Workflows that were built
around a specific product carry a **Genericized import** note — substitute
SurMap's equivalents (see `README.md` and `docs/architecture.md`) before
acting on them. Stack-specific references were repointed to SurMap's stack:
Python 3.11+, uv, pytest, Ruff, mypy (strict).

Entries whose names referenced a specific product or internal system were
renamed to generic equivalents on import (for example CI, E2E, design-system,
roadmap and product-report names). Cross-references were updated to match.

## How To Use

- Start with a skill in `.agents/skills/` when the task matches an existing workflow.
- Use `.agents/commands/*.md` when you want a specific command by name.
- Treat skill-local `references/` folders as supporting guidance, not standalone features.
- Ground stack decisions in `skills/tech-stack/`; it defers to `README.md`,
  `docs/architecture.md` and `pyproject.toml` when they disagree.

## Harness-specific instructions

Some steps only make sense with a subagent layer. They are written as a
conditional — delegate when the harness offers subagents, otherwise apply
the same behaviour directly:

> **With subagents**: delegate to the named subagent.
> **Without**: apply the fixes yourself — the `testing` / `tdd` /
> `code-cleaning` skills fold in the same behaviour.

Never delete a harness's mechanism to make a file portable; scope it instead.
