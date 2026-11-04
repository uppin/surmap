# Initial Discovery: the agent shows no reply from the Meta (Muse) model

## Combined Conclusions

- Deployed and local agents with `meta:muse-wonder-1.0`: a turn ends `turn_finished(STOP)` with no
  `text_delta` — for "hi" and after a tool call. Reproduces on `main` (2026-11-04).
- The model answers: `MetaResponsesChatModel().invoke("hi")` → "Hi there! 👋 How can I help you
  today?". It implements no `_stream`, so `astream()` yields one whole `AIMessage`.
- `surmap.agent.runtime.graph._stream_reply` writes `TextDelta`s only for `AIMessageChunk`s and
  returns a whole `AIMessage` without writing its text, so the turn's stream never carries it.
- Tests missed it: `tests/agent_fakes.ScriptedChatModel` streams word by word;
  `disable_streaming=True` on it reproduces the Meta model's whole-message `astream`.
