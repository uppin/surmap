# The agent shows replies from models that do not stream (Meta / Muse)

**Date:** 2026-11-04
**Fix:** Survey agent / runtime

- **Symptom.** With `meta:muse-wonder-1.0` every turn ended `turn_finished(STOP)` with no text —
  for "hi" and after a tool call — in the chat and over `StreamTurn`.
- **Cause.** `MetaResponsesChatModel` does not stream, so `astream()` yields one whole
  `AIMessage`; `surmap.agent.runtime.graph._stream_reply` returned it without writing its text as
  a `TextDelta`.
- **Fix.** The whole reply's text is written as one `TextDelta`. Streaming models are unchanged.
- **Verified** on the deployed agent (`ginas-bb`, 2026-11-04): "hi" and a `list_demos` turn reply.
- **Tests.** Two in `tests/test_agent_runtime.py` (a `ScriptedChatModel` with
  `disable_streaming=True`).
