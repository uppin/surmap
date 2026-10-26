---
description: Put the open deferred answers to the developer - the questions a yolo-mode run decided instead of asking - and delete every one they answer, confirmed or overridden; an override that needs code becomes a TODO record. Scope by package, area, PR or stack; works before or after the wrap and the merge
---
## Review deferred answers — ask the questions `#yolo` did not

A `#yolo` run decides the questions it would have asked and records each one as a deferred answer
(`.agents/skills/deferred-work/references/deferred-answer-record.md`). This command is where the
developer answers them, at any time: during the PR, after the wrap, or long after the merge. **Each
record the developer answers is deleted.** A record they skip stays open.

This command exists to ask questions, so it is **not** a `[wf]` step and owns no row. It never runs
under `#yolo`, and refuses to start with one. `#ask` does not change it.

## 1. Collect

Scope from `$ARGUMENTS`: a package directory, a product area, `PR #<n>`, a stack slug, or nothing,
which means every open record.

```bash
ls docs/*/deferred-answers/*.md */*/docs/deferred-answers/*.md 2>/dev/null        # everything open
grep -rl -F 'PR #3812' docs/*/deferred-answers/ */*/docs/deferred-answers/ 2>/dev/null   # one PR's
grep -rl -F '#<stack-slug>' docs/*/deferred-answers/ */*/docs/deferred-answers/ 2>/dev/null
```

Read every record whole: *Question*, *Options as asked*, *Supervisor review*, *What was built on
it*, *To override*. Check that *What was built on it* still holds on `origin/master`: the files
exist and the behaviour is still the pick. A record whose code is gone is **superseded**. It is
listed as such and deleted without asking (step 3).

## 2. Ask

Ask in batches of up to four, with the harness's question tool where it has one
(`AskUserQuestion` on Claude Code). Product questions go first, then Technical, oldest first. Each
question:

- **The question** as the record states it, with one line of context, so the developer can answer
  without opening the code.
- **The options**: the supervisor's refined set when there is one, otherwise the asker's. The
  current decision is first and marked *(current)*. When the supervisor refined the options, the
  asker's original pick is noted in the description, so both versions are in front of the
  developer.
- **The cost of each other option**, from *To override*: what has to be redone.
- **Skip** is always possible ("Other" → *skip*). A skipped record stays open, untouched.

## 3. Apply — every answered record is deleted

| Answer | What happens |
|---|---|
| **Confirmed**, the current decision | `git rm` the record |
| **Overridden**, another option or the developer's own words | `git rm` the record. When the override needs code to change, write a TODO record in the same commit (`todo-record.md`, `**Category:** Overridden answer`) under the package the change lands in. Its *What is left* quotes the developer's answer and lists what to redo, taken from *What was built on it*, and its **Consent** line is their answer, verbatim. When the developer asks for the change now, do it on a branch through the normal planning flow instead, and write no TODO |
| **Superseded** (step 1) | `git rm` the record, naming the commit that removed the code |
| **Skipped** | nothing |

One commit for the review, on a branch from `origin/master` (never on `master`), or on the PR's
branch when the scope is an open PR. Its message lists each record with its question and outcome,
`confirmed`, `overridden → <answer>, TODO <path>` or `superseded by <sha>`, and quotes the
developer's answers. That commit is the review's history: the changelog and changeset history
entries that cited a record are never revised (`/wrap-context-docs` step 7c), and
`git log --diff-filter=D -- <record path>` finds this commit from them.

**On an open PR before its wrap**, also update the changeset's `## Deferred Answers` row with the
outcome (`→ c) (confirmed)` / `→ overridden to a)`) rather than deleting it, so the wrap carries
what shipped into the history entries. Sync the PR body's `## Deferred answers` section in the
same turn.

Push and open the PR with `/pr` when the scope was not an open PR. Ask before pushing only if the
branch is not one this command created.

## 4. Summary

```markdown
## /review-deferred-answers — <scope>

| Record | Kind | Question | Outcome |
|--------|------|----------|---------|
| `…/2026-10-23-caption-store.md` | Technical | Where do user captions persist? | ✅ confirmed c) — deleted |
| `…/2026-10-23-captions-empty-state.md` | Product | What does an empty captions list show? | ↩ overridden → illustration + CTA — deleted, TODO `…/docs/todo/2026-10-25-captions-empty-state.md` |
| `…/2026-10-22-retry-budget.md` | Technical | How many retries? | ⏭ skipped — still open |

Commit `<sha>` on `<branch>` (PR #<n>).
```

## Rules

- **Answered → deleted, whatever the answer.** An override's remaining work lives in a TODO
  record or a PR, never in the deferred-answer record.
- **Never decide for the developer.** A skipped or unanswered question stays open. This command
  never confirms a record on the developer's behalf, except a superseded one.
- **Never under `#yolo`.** Asking is the point.
- Never edit a changelog or changeset history entry to record a review. The deletion commit is the
  record.
