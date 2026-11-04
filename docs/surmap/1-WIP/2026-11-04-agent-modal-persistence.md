# Changeset: Agent state persistence on Modal — SQLite DBs and conversations on the Volume

**Date**: 2026-11-04
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 3 — one package (surmap agent), a SQLite adapter seam behind an existing protocol, integration tests over a fake model

## Workflow

- [wf 1] ✅ 2026-11-04 `/plan-red` Plan — changeset, initial discovery · this file + companion; no PRD: the requirements are the developer's three answers of 2026-11-04 (agent only · files + conversations · Modal background commits)
- [wf 2] ✅ 2026-11-04 `/plan-red` Red — acceptance and failing lower-tier tests, committed · 9 new tests red on missing `SqliteConversationStore` / `AGENT_CONVERSATIONS_DB` (ImportError at collection)
- [wf 3] ✅ 2026-11-04 `/green` Green — implement until every red test passes · 26/26 in the two touched suites; full gates below
  - [x] `SqliteConversationStore`: message history, model id and replay events in one SQLite file, reopened intact
  - [x] `ChatHub` restores a conversation (events, model, history) from the store after a restart
  - [x] Agent server wiring: `--conversations-db`, explicit `--history-db` / `--sim-dir` on the Modal command, usage log under the cache dir
  - [x] `docs/modal.md` — the agent's persisted files named
- [wf 4] ⏳ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [x] Verification executed — result recorded
  - [x] `docs/modal.md` §5 agent row — State B folded in
  - [x] `docs/agent.md` — conversation persistence noted if it claims memory-only
  - [ ] Changes validated against the plan (1)
  - [ ] Test quality and fluent readability validated (2)
  - [ ] Lint, type-check and tests green on the rebased tip (7)
  - [ ] Docs wrapped, rows and TODOs carried into the wrap commit and PR body (8)

## Initial Discovery

Full codebase exploration that grounded this plan: [initial-discovery.md](./2026-11-04-agent-modal-persistence-initial-discovery.md).

State A below is distilled from that file. Do not duplicate grep traces or file dumps here.

## Summary

The deployed `surmap-agent` keeps its SQLite DBs and files on Volume `surmap-agent-cache`
explicitly (history, simulation, conversations), its chat conversations survive a container
restart through a SQLite-backed `ConversationStore`, and its usage ledger stops resetting
at every restart. Durability is Modal's background commits plus the shutdown commit; the
app stays a single container, so SQLite has one writer.

## Background

Modal containers lose their local filesystem on restart, scale-down and preemption. The
agent's demo cache already sits on a Volume, but conversations live only in process memory
and the usage log defaults to `~/.surmap/usage.jsonl`, so a restart wipes the chat history
and resets the spend budgets. The developer chose (2026-11-04): agent only (CM5/station are
stateless or already persisted), existing files **plus** conversations, and Modal's
background commits rather than explicit `volume.commit()` calls.

## Scope

- **Implementation**: `SqliteConversationStore`, `ChatHub` restore, agent CLI/config wiring,
  `modal_hosting.agent_command` state paths.
- **Testing**: store round-trip, hub restart, command/config tests — all failing first.
- **Docs**: `docs/modal.md` agent persistence; this changeset wrapped at the end.
- **Out of scope**: CM5/station Volumes, in-flight job resumption, explicit
  `volume.commit()` calls, subagent conversation persistence.

## Technical Changes

### State A (Current)

- `ChatHub._open` gives every session an `InMemoryConversationStore`; `Conversation.events`
  (the `GetConversation` replay) and `model_id` live in dicts on the hub. A restart loses
  conversations, their replay and their model history.
- `agent_command()` passes only `--cache-dir /cache`; the history DB, simulation store and
  geometry reach the Volume only through defaults. `UsageLedger()` writes
  `~/.surmap/usage.jsonl` on the ephemeral filesystem.

### State B (Target)

- `SqliteConversationStore` (behind the existing `ConversationStore` protocol) keeps, per
  conversation, the langchain message history (`message_to_dict` JSON), the `model_id` and
  the replay events (protobuf bytes) in one SQLite file, one transaction per append.
- `ChatHub` takes an optional shared store: `_record` also archives each event, and a
  conversation unknown in memory is restored (events, model, idle loop) on first use, so
  `GetConversation` and the next turn work across a restart. Without a store, behaviour is
  exactly State A.
- The agent gains `--conversations-db`; with a cache dir and no `$SURMAP_USAGE_LOG`, the
  usage log is `<cache-dir>/usage.jsonl`. The Modal command passes `--history-db`,
  `--conversations-db` and `--sim-dir` explicitly under `/cache`.

### Delta

#### surmap (agent)

- **Implementation**: new SQLite store; hub restore + event archiving; CLI/config/ledger
  wiring; `modal_hosting` path constants on the agent command.
- **API**: new `--conversations-db` flag and `AgentServerConfig.conversations_db`; no proto
  or RPC change.

## Verification

**Method:** V1-fail→pass — new tests fail on State A (no SQLite store, no restore, no flags), pass on State B
**Command:** `uv run pytest -q tests/test_agent_conversation_persistence.py tests/test_modal_survey_apps.py tests/test_agent_server_app.py` then the full gates (`ruff check`, `ruff format --check`, `mypy`, `pytest -q`)
**Before:** the 9 new tests fail at collection on State A (`ImportError: SqliteConversationStore`, `AGENT_CONVERSATIONS_DB`) — the implementation is missing, not the environment
**After:** recorded 2026-11-04 — `tests/test_agent_conversation_persistence.py` + `tests/test_modal_survey_apps.py` 26 passed; `uv run ruff check src tests` clean; `uv run ruff format --check src tests` clean (572 files); `uv run mypy` clean (518 files); `uv run pytest -q` 2258 passed, 38 skipped. Not yet deployed: `modal deploy` + a live restart check on workspace `ginas-bb` remain for the developer's go-ahead (outward-facing, billed)
