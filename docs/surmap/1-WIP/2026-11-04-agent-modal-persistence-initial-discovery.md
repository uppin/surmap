# Initial Discovery: Agent state persistence on Modal

**Changeset**: [2026-11-04-agent-modal-persistence.md](./2026-11-04-agent-modal-persistence.md)
**Date**: 2026-11-04
**Passes**: 1

## Combined Conclusions

The deployed Modal apps are `surmap-agent` (`src/surmap/agent/modal_agent_app.py`),
`surmap-cm5-sim`, `surmap-station` and `surmap-sam` (`docs/modal.md` §5). Only the agent
holds SQLite state, so it is the only app in scope (developer's choice, 2026-11-04).

State A, per app:

- **Agent** — mounts Volume `surmap-agent-cache` at `/cache` (`AGENT_CACHE`) and passes
  `--cache-dir /cache`, so `demo-history.db` (default `cache_dir / "demo-history.db"` in
  `make_demo_server`), the dataset cache, `agent-geometry/` and — when the simulation rig
  is on — `simulation.sqlite` + `library/` already land on the Volume. Nobody calls
  `volume.commit()`; Modal's background commits (every few seconds) plus the final commit
  on container shutdown are what persist them. Two things do **not** persist: chat
  conversations (`ChatHub` docstring: "Conversations live in memory and end with the
  process"; each session gets an `InMemoryConversationStore`, and `GetConversation`
  replays the in-memory `Conversation.events` list), and the usage ledger
  (`UsageLedger()` defaults to `~/.surmap/usage.jsonl` or `$SURMAP_USAGE_LOG`, so spend
  budgets reset at every container restart).
- **CM5** — no Volume; the streaming RTAB-Map backend's state belongs to a live survey
  stream whose WebSocket dies with the container, so there is nothing resumable to persist.
- **Station / SAM** — already persist the SAM 3.1 checkpoint + HF cache on Volume
  `surmap-sam3` at `/models`; otherwise stateless.

The seam for conversations already exists: `AgentSession` takes a `ConversationStore`
protocol (`history` / `append`) and `InMemoryConversationStore` is its only implementation.
`langchain_core.messages.message_to_dict` / `messages_from_dict` round-trip Human/AI/Tool
messages including `additional_kwargs` kind tags and tool calls (verified in a probe), so a
SQLite store needs no new serialization. The hub additionally needs each conversation's
`model_id` and its replay events (`chat_pb2.TurnEvent` protobuf bytes) in the same file.
All agent containers are `max_containers=1`, so a single-writer SQLite file on the Volume
is safe; durability relies on Modal background commits (developer's choice).

## Exploration 1: Modal apps, agent state and the conversation seam — 2026-11-04

**Agent**: parent Grep/Glob/Read
**Scope**: `src/surmap/agent/`, `src/surmap/survey/modal_*`, `docs/modal.md`, tests

### Sequence

1. Read `src/surmap/agent/modal_agent_app.py`, `src/surmap/survey/modal_cm5_app.py`,
   `modal_station_app.py`, `modal_sam_app.py` — which Volumes each app mounts today.
2. Read `src/surmap/survey/modal_hosting.py` — `agent_command()` (the tested seam the app
   files run) and its path constants.
3. Read `src/surmap/agent/__main__.py` — the agent CLI (`--history-db`, `--cache-dir`,
   `--sim-dir`, `--web-dist`; no conversation-store flag).
4. Grep `history_db|cache_dir|sim_dir|ScenarioStore` in `src/surmap/agent/server/app.py` —
   defaults: history `<cache>/demo-history.db`, sim `<cache>/simulation`, geometry
   `<cache>/agent-geometry`; `UsageLedger()` built with no path in `build_agent_description`.
5. Read `src/surmap/agent/server/hub.py` and `src/surmap/agent/runtime/session.py` —
   `ConversationStore` protocol, `InMemoryConversationStore`, in-memory `events` replay.
6. Read `src/surmap/demo/history.py` / `src/surmap/simulation/scenario_store.py` heads —
   the repo's SQLite patterns (lock + one connection; WAL in the scenario store).
7. Probe: `message_to_dict` / `messages_from_dict` round-trip of Human/AI(tool_calls)/
   Tool messages — kinds, tool calls and ids preserved.

### Grep / glob

| Tool | Pattern / glob | Path scope | Notable hits |
|---|---|---|---|
| Grep | `sqlite\|Volume\|volumes=` | `src/` | agent cache Volume; SAM/station model Volume; no CM5 Volume |
| Grep | `Path.home()\|\.surmap` | `src/surmap/agent` | usage log default only (`surmap/usage.py`, via `server/app.py`) |
| Grep | `InMemoryConversationStore` | `src/ tests/` | `hub.py` `_open`, `subagents.py`, test fakes |

### Inspected files

#### `src/surmap/agent/server/hub.py`

**Why**: where conversations, their events and their stores are created.
**Excerpt**: `_open()` builds `AgentSession(..., store=InMemoryConversationStore())`;
`_record()` appends the proto event to `conversation.events` with `seq=len(events)+1`.

#### `src/surmap/survey/modal_hosting.py`

**Why**: the tested seam for what the deployed agent runs.
**Excerpt**: `agent_command()` passes `--station modal --web-dist … --cache-dir /cache`
and nothing else stateful; constants `AGENT_CACHE = "/cache"`, `AGENT_PORT = 8780`.
