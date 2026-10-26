# The deferred-answer record — `docs/<area>/deferred-answers/` and `<package>/docs/deferred-answers/`

A question the agent would have asked the developer, but did not because the run was under `#yolo`
(`.agents/skills/behaviour-modifiers/references/yolo.md`). The record holds the options, what the
agent picked, what its supervisor made of it, and what was built on the pick. One file per question.

A TODO is work that was **not done**. A deferred answer is a decision that **was made**, by the
agent, and that nobody has reviewed yet. The work built on it is in the code. The record is how the
developer finds the decision, and how they find what to redo if they disagree.

## Where it lives

| Kind | The question is about | Directory |
|---|---|---|
| **Product** | *what* — a requirement, the visible behaviour, copy, a name the user sees, the scope of a slice | `docs/<area>/deferred-answers/` — the product area that owns the WHAT (`docs/AGENTS.md`) |
| **Technical** | *how* — a design, a structure, a library, an API shape inside the code, a test seam | `<package>/docs/deferred-answers/` — the package the answer is built into |

A Technical answer built into several packages is owned by the one whose code depends on it most,
and every other package is named in `**Packages:**`, exactly like a TODO's
(`todo-record.md` § *Which package owns the file*). A Product answer for a cross-area change lives
with the owning area, as the changeset does.

Both directories are written directly, never through a changeset. A record lives only until the
developer reviews it, which is usually after the PR has merged and the changeset is gone
(`README.md` § *NEVER*, the deferred-work exception).

## Filename

`YYYY-MM-DD-<short-slug>.md`, the date the question came up. If the name is taken, append `-2`. A
deferred answer is an **event**, like a TODO: a second question on the same subject is a second
file.

## Template

```markdown
# YYYY-MM-DD — <the question, in a few words>

**Kind:** Product | Technical
**Source:** `docs/<area>/1-WIP/YYYY-MM-DD-<changeset>.md` (PR #NNNN, stack `#<slug>` node K/N)
**Asked by:** `/green` row 3 — `[G]` n3, haiku · xhigh
**Packages:** surmap, surmap   ← Technical only
**Status:** Awaiting supervisor | Awaiting review
**Decision:** c) sidecar file — supervisor's pick (refined)

## Question

<The question as the developer would have been asked it, with the context they need to answer it
without opening the code.>

## Options as asked

| | Option | Consequence |
|---|---|---|
| a) | … | … |
| b) **(recommended)** | … | … |

**Asker's pick:** b) — <why>

## Supervisor review

**Reviewed by:** `/yolo-pr-stack` orchestrator, opus · high
**Verdict:** Answered | Refined

<When refined, the options as the supervisor rewrote them, in the same table, with its
recommendation marked.>

**Supervisor's pick:** c) — <why, and what it knew that the asker did not>

## What was built on it

<Every file, symbol and commit that depends on the pick, so an override knows what to redo:
`path:line`, commit SHAs, tests that pin the behaviour.>

## To override

<For each option not picked: what changes, roughly how much, and anything that would have to be
undone, such as a migration, a published contract or a user-visible string.>
```

*Supervisor review* is present only when the question was relayed. Without a supervisor the record
has no such section and `**Decision:**` is the asker's pick. *Options as asked* is **never edited**
after the relay. The developer reviews both versions.

## Lifecycle

A record is **open until the developer answers it**. That usually happens after the run, often after
the wrap or the merge, since open deferred answers do not gate Approve or Land. The developer
answers when asked: by `/review-deferred-answers` (any scope, any time), or in the interview of an
interactive plan whose Step 2b finds the record in its path. **Every answered record is deleted**,
whatever the answer:

- **Confirmed** — `git rm` the record in a commit whose message quotes the developer's answer.
- **Overridden** — `git rm` the record as well. When the override needs code to change, the same
  commit writes a TODO record (`todo-record.md`, `**Category:** Overridden answer`) that quotes the
  answer and lists what to redo from *What was built on it*. Or the change is made now, on a branch.
  Either way, the override's remaining work lives in the TODO or the PR, never in this record.
- **Superseded** — the code the answer was built into was removed or rewritten for another reason.
  Delete the record in that commit and say why. This is the only deletion that needs no answer.
- **Skipped** — the record stays as it is.

The history entries that cited the record (`/wrap-context-docs` step 7c) are never revised. The
deletion commit says what the answer was, and `git log --diff-filter=D -- <path>` finds it from the
path the entry gives.

There is no `Reviewed` state, for the same reason a TODO has no `Resolved` state: the directory
listing **is** the open list. Every file in it is a question still waiting for the developer.

## Who writes and reads it

| Who | Does |
|---|---|
| any command under `#yolo` | writes the record at the moment it would have asked, adds its row to the changeset's `## Deferred Answers` section (`pr-lifecycle/references/changeset.md` §13.5), and commits both with the work that follows from the pick |
| a supervisor (`/yolo-pr-stack` orchestrator) | writes nothing on the branch itself. It sends the *Supervisor review* to the asker, which pastes it in |
| the end-of-turn summary, the PR body | list every record this turn or PR wrote (`behaviour-modifiers/references/yolo.md` § 4) |
| `/wrap-context-docs` step 7c | carries each row of the changeset's `## Deferred Answers` into the history entries: Product into the area's `changelog/` entry, Technical into the package's `docs/changesets/` entry. The record itself is left open |
| planning Step 2b | reads open records for the packages and areas a change touches, and gives each one a verdict in the changeset's `## Prerequisites` → `### Open Deferred Answers`. An unreviewed decision in the path of new work is ℹ at least, and ⛔ when the new work would build further on a pick the developer may still override (`planning-cross-check.md`) |
| `/review-deferred-answers` | asks the developer the open records in its scope, deletes each one they answer, and turns an override that needs code into a TODO record |
| `/pr-wrap` | checks that every record this PR added is listed in the PR body's `## Deferred answers` section. It never deletes one, because only the developer's review closes a record |

## Querying

```bash
ls docs/*/deferred-answers/ */*/docs/deferred-answers/ 2>/dev/null        # everything awaiting review
grep -rl 'Kind:\*\* Product' docs/*/deferred-answers/ 2>/dev/null          # product decisions only
grep -rl -F 'PR #3812' docs/*/deferred-answers/ */*/docs/deferred-answers/ 2>/dev/null   # one PR's
grep -rl '^## Supervisor review' docs/*/deferred-answers/ */*/docs/deferred-answers/ 2>/dev/null   # relayed ones
mb=$(git merge-base origin/master HEAD)
git diff --diff-filter=A --name-only "$mb" -- 'docs/*/deferred-answers/*.md' '*/docs/deferred-answers/*.md'   # this branch's
```
