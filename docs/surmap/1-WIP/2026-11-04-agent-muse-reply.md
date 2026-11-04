# Changeset: The agent shows a non-streaming model's reply

**Date**: 2026-11-04
**Status**: 🚧 In Progress
**Type**: Bug Fix
**Behaviour**: changes
**Complexity**: 1 — one function, one test file

## Workflow

- [wf 1] ✅ 2026-11-04 `/plan-red` Plan — changeset, initial discovery · this file + discovery companion
- [wf 2] ✅ 2026-11-04 `/plan-red` Red — reproduction test, committed · 2 red: `'' == 'Hi there! How can I help?'`, `'' == 'The demo ran as run-7.'`
  - [x] A non-streaming model's answer reaches the turn as text
  - [x] … also after a tool call
- [wf 3] ⬜ `/green` Green — fix until the reproduction passes ·
  - [ ] `_stream_reply` writes a whole reply's text as a `TextDelta`
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded (V1; V4 on the deployed agent)
  - [ ] Changelog entry
  - [ ] Lint and quality gates green

## Initial Discovery

[initial-discovery.md](./2026-11-04-agent-muse-reply-initial-discovery.md).

## Technical Changes

### State A (Current)

`_stream_reply` returns a whole `AIMessage` from `astream()` without a `TextDelta`: Muse replies
never reach the chat (history has them, the stream does not).

### State B (Target)

The whole reply's text is written as one `TextDelta` before it is returned.

## Verification

**Method:** V1-fail→pass; V4 — a turn on the deployed agent streams a reply.
**Command:** `uv run pytest -q tests/test_agent_runtime.py -k does_not_stream`
**Before:** 2 failed (no text).
**After:** 2 passed.
**Approved:** the developer, 2026-11-04 ("create a PR with a fix and deploy it").
