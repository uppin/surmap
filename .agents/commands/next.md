---
description: Run exactly one [wf] row of the changeset - the first row not done, with that row's command and tags - then end with the step's summary
---
## Next — run one `[wf]` row

`/next` is the same as invoking the next row's command by hand — the runner in
`.agents/skills/pr-lifecycle/SKILL.md` § *Runners*. This file adds only how the row is picked.

1. **Resolve the changeset and grep its rows** (step contract, steps 1–2). After the wrap, read
   them from the PR body, or from the wrap commit's message until a PR exists, as step 1 *After the
   wrap* says. None or more than one changeset, and no wrapped PR for the branch → end the turn
   naming the candidates.
2. **Take the next row** — the skill's next-row grep (first ⬜, ⏳ or ⛔).
   - ⬜ or ⏳ → run it; a ⏳ row resumes at its first open TODO.
   - ⛔ → run it only when this invocation carries the developer's answer to that halt (in
     `$ARGUMENTS` or the conversation). Otherwise do nothing and end the turn reporting the halt:
     its **Result** and the options it lists.
   - Every row ✅ or ➖ → the rows are done; run the post-wrap step, `/fix-pr`, end to end
     (`pr-lifecycle` skill § *Post-wrap*). It has no row and `/next` writes none. Approve and Land
     are `/yolo`'s alone.
3. **Run the row's command by following that command's file end to end**, with the
   row's tags plus any tags in this invocation (`/next #composer` adds `#composer` to the row's
   own). The command closes its row and ends with its own summary; `/next` adds nothing to it.

`/next` runs one row, never two. When a command owns several consecutive rows (`/plan-red` owns
Plan and Red), the command's own file decides whether it closes them in one run.

## Rules

- Never edit the rows yourself beyond what the row's command does.
- `#skipreview` and `#automerge` are never posted by `/next`.
