# Survey agent skill support (`surmap.agent.skills`)

**Date:** 2026-11-03
**Type:** Feature
**Packages:** surmap

Added agent skills: reviewed `SKILL.md` instruction documents (a `name` and one-line
`description` in front matter, one directory per skill) that the model discovers with a
new `list_skills` tool and reads one at a time with `load_skill`, so a skill body costs
context only when chosen and arrives as an ordinary tool result, never as an addition to
the shared system prompt. `SkillCatalogue` serves the tree shipped in the package
(`src/surmap/agent/skills/`) plus an overlay directory (`AgentServerConfig.skills_dir`,
`$SURMAP_AGENT_SKILLS_DIR`) that wins on a name collision; listing is sorted by name,
a skill missing a name or description is refused, a body over 64 KiB is refused whole,
and a skill name cannot escape the skills directory. The first shipped skill,
`using-the-map`, teaches the map tools (objects, camera, routes, layers, scenes,
revisions, and the drawn-path-never-a-flight-plan rule). `SYSTEM_PROMPT` points the
model at the skill tools. `docs/agent.md` documents the mechanism.

Tests: 15 new in `tests/test_agent_skills.py` and `tests/test_agent_skill_tools.py`
(catalogue listing/loading/overlay/guards, the bound tools, and a scripted-model turn
that lists and loads the shipped skill), plus the tool-offering assertion in
`tests/test_agent_server_app.py` extended by the two new tools. Full suite 1701 passed,
33 skipped; ruff, ruff format and strict mypy clean.
