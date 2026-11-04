# Agent state persists across a restart — one state dir, `<repo>/tmp` in dev

**Date:** 2026-11-04
**Feature:** Survey agent server

- **Bug.** After a dev restart, the chat page opened an empty conversation and lost its
  simulation pane. `python -m surmap.agent` kept conversations in memory unless
  `--conversations-db` was given, and `scripts/dev.sh` never gave it. The pane is derived from
  the conversation's replay, so it went too, even though the scenario itself was still in
  `simulation.sqlite`. The map scene (`MapSceneStore`) was in memory everywhere, Modal included.
- **State dir.** `--state-dir` / `AgentServerConfig.state_dir` holds everything a conversation
  leaves behind: `conversations.sqlite`, `map-scenes.sqlite`, `demo-history.db`, `simulation/`,
  `agent-tool-outputs/`, `agent-geometry/` and `usage.jsonl`. Each store's own flag still wins.
  The command line always sets it: `--cache-dir`, else `$SURMAP_DEMO_CACHE_DIR` or
  `~/.cache/surmap`. As a result, conversations are persistent by default. A config built with
  no state dir (tests, embedders) keeps conversations and the map scene in memory.
- **Map scenes.** `MapSceneStore(db_path=…)` saves a scene on every change: objects, routes,
  camera, loaded layers, revision and the next generated id. A reopened store reads it back.
- **Dev.** `scripts/dev.sh` passes `--state-dir <repo>/tmp/agent`, and `tmp/` is gitignored, so
  each worktree has its own state. Downloaded datasets stay in the shared cache.
- **Modal.** Unchanged command. `/cache` is the state dir, so the map scene now survives a
  container restart too.
- **Code.** `AgentServerConfig.state_dir`, `server.app.map_scene_store` / `default_state_dir`,
  `MapSceneStore.changed` / `db_path` / `close`.
- **Tests.** pytest: 11 in `test_agent_state_dir.py`, 2 in `test_dev_script.py`. Three
  CLI-default config tests were updated for the state dir.

Docs: [docs/agent.md](../../agent.md) (*Running the agent*, *Map tools and layers*),
[docs/modal.md](../../modal.md).
