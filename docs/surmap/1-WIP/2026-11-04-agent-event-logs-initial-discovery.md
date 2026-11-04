# Initial Discovery: greppable agent server logs

## Combined Conclusions

- In production (`modal app logs surmap-agent`) the agent writes only Hypercorn access lines
  (`POST …/StreamTurn -> 200 OK`); a turn that ends with no reply (the 2026-11-04 Muse bug) left
  no trace of its reason, tools or length. The only module logger is `agent/tools/station.py`.
- Every runtime event of every turn — user and job-event turns — passes through
  `hub._record(conversation, turn_id, event)` (`hub.py:235`); a user turn opens with
  `_record_user_message` (`hub.py:247`), a job turn with its first `_record`. `Conversation`
  (`hub.py:52`) carries `model_id`. Events: `ToolCallStarted(call_id, tool, …)`,
  `ToolCallFinished(call_id, tool, outcome)` with `Completed | Detached | Failed(error)`,
  `TextDelta(text)`, `TurnFinished(reason)`, `TurnError(message)`.
- Sign-in and refusals happen in `server/routes.py` (`sign_in`, `serve`) and
  `server/app.py::_with_session`; station transitions in `tools/station*.py`.
- Modal keeps a container's stdout/stderr: lines written there are what `modal app logs` greps.
