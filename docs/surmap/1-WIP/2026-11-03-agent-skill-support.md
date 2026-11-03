# Changeset: Agent skill support

**Date**: 2026-11-03
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 3 — one package (`surmap.agent`), a new catalogue module plus tool wiring, integration tests over the in-memory host

## Workflow

- [wf 1] ✅ 2026-11-03 `/plan-red` Plan — changeset, initial discovery · this file + discovery companion
  - [x] Changeset and discovery companion written
- [wf 2] ✅ 2026-11-03 `/plan-red` Red — acceptance and failing lower-tier tests, committed · 15 tests red at import (no `surmap.agent.skills`), then green
  - [x] Catalogue tests: listing, loading, overlay precedence, guards, size cap
  - [x] Tool tests: `list_skills` / `load_skill` bound tools end to end
  - [x] Server test: a turn can list and load the shipped `using-the-map` skill
- [wf 3] ✅ 2026-11-03 `/green` Green — implement until every red test passes · 15 passed in `tests/test_agent_skills.py` + `tests/test_agent_skill_tools.py`
  - [x] `SkillCatalogue` with builtin + overlay roots
  - [x] `list_skills` / `load_skill` as bound tools in every conversation
  - [x] First skill `using-the-map` shipped under `src/surmap/agent/skills/`
  - [x] `SYSTEM_PROMPT` points the model at the skill tools
- [wf 4] ✅ 2026-11-03 `/pr-wrap` Wrap — validate, clean up, verification, docs · gates green; history entry written; PR opened ready
  - [x] Verification executed — result recorded
  - [x] `docs/agent.md` — skill support and the shipped skill documented
  - [x] Changeset and discovery companion deleted; rows carried into the PR body

## Initial Discovery

Full codebase exploration that grounded this plan: [initial-discovery.md](./2026-11-03-agent-skill-support-initial-discovery.md).

State A below is distilled from that file. Do not duplicate grep traces or file dumps here.

## Summary

The survey agent gains skills: reviewed instruction documents the model discovers with a
`list_skills` tool (names and one-line descriptions only) and reads one at a time with
`load_skill`, so a skill's body costs context only when the model chooses it. The first
shipped skill, `using-the-map`, teaches the map tools. Skills ship in the package and a
deployment may overlay its own.

## Background

Everything telling the agent how to behave is the `SYSTEM_PROMPT` constant in
`server/app.py`. Adding guidance means editing and redeploying that text, and a catalogue
pushed wholesale into every turn would cost more context than the conversations it helps.
Skills fix both: guidance lives in reviewed `SKILL.md` files, listed cheaply and loaded on
demand as ordinary tool results (never appended to the shared system prompt, so a loaded
skill is not sticky for the process and can be re-read or ignored per conversation).

## Scope

- **Implementation**: `SkillCatalogue` (discovery, listing, guarded loading), the
  `list_skills` / `load_skill` bound tools, hub wiring, `AgentServerConfig` skill roots,
  and the shipped `using-the-map` skill.
- **Testing**: catalogue unit tests, tool-level tests, and a server test proving a scripted
  model can list and load the shipped skill in a real turn.
- **Documentation**: `docs/agent.md` gains the skill mechanism and catalogue.

## Technical Changes

### State A (Current)

- Tools are exactly the `SurveyTools`, `MapTools` and `AgentJobs` proto contracts, bound
  per conversation by `agent_tools` over the conversation's `JobRunner`.
- Behavioural guidance is the `SYSTEM_PROMPT` constant only; there is no skill concept.

### State B (Target)

- `src/surmap/agent/skills/` (package): `Skill` (name, description), `SkillCatalogue` with a
  builtin root (the package's shipped `skills/` tree, via `importlib.resources`) and an
  optional overlay root (a directory of skill subdirectories; `SURMAP_AGENT_SKILLS_DIR`
  or `AgentServerConfig.skills_dir`). The overlay wins on a name collision. Listing is
  sorted by name; a skill whose front matter lacks a name or description is refused.
  Loading returns the body in full, refuses bodies over 64 KiB, and refuses any name that
  escapes the skills directory. No root configured at all raises `SkillsUnavailableError`;
  a configured-but-missing directory lists nothing.
- `list_skills` / `load_skill` are `BoundTool`s (contracts built directly, SYNC · 10 s ·
  FAIL) appended to every conversation's tools in `build_agent_description`; the model
  calls them like any other tool and the results arrive as tool results.
- `src/surmap/agent/skills/using-the-map/SKILL.md`: the first skill — how to use the map
  tools (objects, camera, routes, layers, scenes, revisions, and the display-only rule).
- `SYSTEM_PROMPT` tells the model the skill tools exist and to load a skill before the
  work it describes.

### Delta (What's Changing)

#### surmap

- **New package**: `src/surmap/agent/skills/` — catalogue, front-matter parsing, guards,
  skill tool contracts and binding, plus the shipped skill tree.
- **Wiring**: `server/app.py` builds the catalogue and adds the skill tools to the hub's
  tool factory; `AgentServerConfig.skills_dir` and `SURMAP_AGENT_SKILLS_DIR` configure the
  overlay root.
- **Content**: `src/surmap/agent/skills/using-the-map/SKILL.md`.
- **Docs**: `docs/agent.md` skill section.

## Verification

**Method:** V1-fail→pass — new tests fail before the change (no catalogue, no skill tools, no shipped skill) and pass after.
**Command:** `uv run pytest -q tests/test_agent_skills.py tests/test_agent_skill_tools.py` plus the full gates `uv run ruff check src tests`, `uv run ruff format --check src tests`, `uv run mypy`, `uv run pytest -q`
**Before:** the new test files fail at import/collection (the implementation is missing).
**After:** every new test passes and the full suite, ruff and strict mypy stay green.

**Result (2026-11-03):** `uv run pytest -q` — 1701 passed, 33 skipped (one existing
tool-listing test extended to the new tool set); `uv run ruff check src tests`,
`uv run ruff format --check src tests` and `uv run mypy` (strict, 384 files) all clean.

## Testing Plan

**Primary Test Approach:** Unit tests for the catalogue against temporary skill trees
(listing shape, overlay precedence, malformed front matter, path escape, size cap), tool
tests that run `list_skills`/`load_skill` through a `JobRunner` as the graph does, and one
server-level test where a `ScriptedChatModel` lists and loads the shipped `using-the-map`
skill inside a real streamed turn. Fluent Given/When/Then style per the `fluent-tests`
skill; fakes only at the existing seams.
