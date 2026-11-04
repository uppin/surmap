# Agent state persists across Modal container restarts

**Date:** 2026-11-04
**Feature:** Survey agent / persistence; Modal / `surmap-agent`

- **Conversations.** New `--conversations-db`: `SqliteConversationStore`
  (`surmap.agent.runtime.session`, behind the existing `ConversationStore` protocol)
  keeps each conversation's message history, model and `GetConversation` replay in one
  SQLite file; `ChatHub` archives every event and restores a conversation on first use
  after a restart. Without the flag, conversations stay in memory as before. Running
  turns and jobs do not survive.
- **Files on the Volume.** The Modal agent command (`surmap.survey.modal_hosting`)
  now names its state explicitly under `/cache` (Volume `surmap-agent-cache`):
  `--history-db demo-history.db`, `--sim-dir simulation/` (`simulation.sqlite` +
  `library/`), and the usage log follows `--cache-dir` to `usage.jsonl` unless
  `$SURMAP_USAGE_LOG` is set — so spend budgets stop resetting at every restart.
  Durability is Modal's background commits plus the shutdown commit; the single
  container (`max_containers=1`) is SQLite's only writer.
- **Other apps unchanged.** The CM5 (live-stream state) and the station/SAM
  (checkpoint already on `surmap-sam3`) hold nothing else worth persisting.
- **Tests.** `tests/test_agent_conversation_persistence.py` (9: store reopen,
  isolation, hub restart), one command test in `tests/test_modal_survey_apps.py`.

Docs: [docs/modal.md](../../modal.md) §5, [docs/agent.md](../../agent.md) (*Limits*, flags).
Not yet deployed: `modal deploy` + a live restart check on `ginas-bb` still to run.
