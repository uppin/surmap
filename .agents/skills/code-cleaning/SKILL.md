---
name: code-cleaning
description: Refine implementation, clean up documentation progress, and wrap a change into its final ready-to-share state. Use when the main feature work is done and the user wants cleanup, context docs updated, or a PR-wrap style finish before review.
---

# Code Cleaning

Tighten the implementation and bring docs and finish-state workflow up to date.

The `refactor` behaviour is folded into this skill. On Muse the `refactor` subagent
(`.muse/agents/refactor.md`) still exists and remains the preferred way to apply fixes there;
elsewhere this skill carries the same behaviour directly.

## Workflow

1. Refine the implementation.
Apply user feedback, remove rough edges, and address clean-code issues before handoff. Inside
`/pr-wrap` that is every issue the validators report, Minor included.

2. Keep context docs current.
Update in-progress documentation with actual implementation progress and decisions.

3. Perform wrap-up cleanup.
Use the PR-wrap style finish when the change is already close and needs coordinated cleanup, validation, and final context updates.
`/pr-wrap` owns the changeset's **Wrap** row (`.agents/skills/pr-lifecycle/SKILL.md`) and
decides cleanups, file splits, code issues and TODO dispositions itself.

4. Finalize docs at the correct stage.
Stable package docs should only be updated during the wrap/finalization step, not during early planning.
`/wrap-context-docs` also deletes `{changeset-slug}-initial-discovery.md` next to the changeset —
that file is planning evidence, not State B.
Deleting the changeset deletes its `[wf]` rows too; `/pr-wrap` step 8 carries the rows, with their TODOs, into
the wrap commit's message and the PR body. Wrap is the last row; nothing after it adds a row or a TODO.

## Use These Source Prompts

- `.agents/commands/refine.md`
- `.agents/commands/update-context-docs.md`
- `.agents/commands/wrap-context-docs.md`
- `.agents/commands/pr-wrap.md`

## Guardrails

- Prefer small, justified cleanup over churn.
- Cleanups keep behaviour unchanged. A bug found while cleaning is reported and fixed separately,
  never folded into a cleanup.
- Keep the doc workflow aligned with repo rules.
