# Survey agent — chat UI - PRD

**Date**: 2026-11-03
**PRD Type**: Enhancement

## Affected Features

- **Primary Feature**: Survey agent (new, `docs/agent.md` created at wrap) — the browser chat

## Summary

A shadcn/ui chat in `web/agent-chat` that talks to the agent server: a transcript with streamed
replies, tool-call steps, a jobs panel showing each call's execution policy, a steering box usable
while the agent works, frame and crop images inline, a 3D preview of object geometry, and a model
picker (Muse, Ollama).

## Background

The developer asked for a shadcn agentic chat. The toolchain lands in n6; the server in n8.

## Proposed Changes

### What's Changing

- **Transcript**: messages as a discriminated union (`user | assistant | tool | job_notice | steer | error`); assistant text streams from `text_delta`; Markdown rendering.
- **Tool steps**: one collapsible row per tool call — name, arguments, status icon (running, done,
  failed, detached), duration, the execution policy used (`SYNC 30 s → DETACH`), result preview;
  `get_frame` results show the image; `get_object_geometry` results show a three.js preview of the
  GLB (`geometry_uri`).
- **Jobs panel**: running and finished jobs with tool, status, elapsed time, `Cancel`.
- **Composer**: while a turn runs the input stays enabled and sends **Steer** (button label
  "Steer"); idle it starts a turn. A `Stop` button cancels the turn.
- **Model picker** from `ListModels`; **conversation**: one per tab, restored from `GetConversation`
  after a reload; a `WatchConversation` stream shows job-event turns while idle.
- **Settings**: server URL (default `http://127.0.0.1:8780`).

### What's Staying the Same

- Demo console and viewer pages.

## Impact Analysis

### Technical Impact

Adds `three` and `react-markdown` to `web/agent-chat`.

### User Impact

`npm run dev` in `web/agent-chat` plus `python -m surmap.agent` gives a working chat.

## Implementation Plan

See the changeset `2026-11-03-agent-chat-ui.md`.

## Acceptance Criteria

1. Sending a message streams the reply and renders each tool call as a step with its policy.
2. Typing during a running turn sends `Steer`, shows a steer marker, and the detached call moves to the jobs panel.
3. A job-event turn arriving on the watch stream renders as a notice and a reply.
4. `Stop` cancels the turn.
5. A frame tool result shows its image; a geometry result shows a 3D preview.
6. The model picker lists the server's models and sends the chosen id.

## References

### Affected Features (Complete List)

- Survey agent (new)
