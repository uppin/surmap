---
name: pr-lifecycle
description: >-
  The lifecycle of a PR and its planning documents, for every kind of change: how the PRD and changeset start in `1-WIP/` (classification, place, discovery companion, header, the `[wf]` rows, the body each kind requires — templates in references/changeset.md, references/prd.md, references/restructure.md), how the work moves while the PR is a draft, and the draft → ready-for-review transition, whose mandatory step is wrapping the docs. Also the workflow contract every development command follows — one `- [wf <n>]` line per step so one grep gives the state; commands run only their own row, never name a successor, never stop for review, halt the row ⛔ when the developer is needed, and end with a summary — with the presets, the step contract, the halt rules, the post-wrap procedures that carry no row (checks and threads, approve, land), the runners (`/next`, `/yolo`) and the summary format. Use when starting, planning, resuming or wrapping a change, readying a PR, running any step command, or asking where a change stands or what runs next.
---

# PR lifecycle — from planning documents to a PR ready for review

A changeset carries what a command needs to make progress: its `[wf]` rows — the steps, **in
order** — and nested under each row the TODOs that step works through. No command decides what
runs after it. A command finds its own row, works through that row's TODOs, records the result in
the row, and ends the turn with a summary. Whoever advances the work — the
developer, `/next` or `/yolo` — reads the next row from the same place.

## Start a changeset

Every command that creates a changeset follows these steps and points here rather than restating
them. The sections themselves are specified in `references/changeset.md`.

1. **Classify the change.** The `(Type, Behaviour)` pair (`references/changeset.md` §1) picks the
   preset (§ *Presets*) and the template: `references/restructure.md` for Refactor · preserves,
   `references/changeset.md` for every other kind.
2. **Place it.** `docs/<area>/1-WIP/YYYY-MM-DD-<slug>.md`, in the owning area's `1-WIP/`
   (`docs/AGENTS.md`); a cross-area change lives with the owning product and references the others.
3. **Discovery first.** Write `<slug>-initial-discovery.md` from the exploration before the
   changeset (`references/initial-discovery.md`).
4. **Header.** Title, `Date`, `Status: 🚧 In Progress`, `Type`, `Behaviour`, and `Complexity` with
   the signals that set it (`references/changeset.md` §1).
5. **`## Workflow`.** The preset's `[wf]` rows (§ *Workflow rows*), adjusted to the change: the
   creating command's own row ⏳, rows the branch already holds ✅ with their evidence, rows that
   cannot apply ➖ with the reason — and under each row the plan-derived TODOs it will work
   through (milestones under Green, wrap-time obligations under Wrap).
6. **The body the template requires for the kind** — always `## Initial Discovery`, State A /
   State B / Delta and `## Verification`; `## Prerequisites` when the deferred-work cross-check
   found anything; `## Deferred Answers` once a `#yolo` run records one
   (`references/changeset.md` §13.5); `## Stack Context` for a stack node.
7. **Commit** the changeset and its companion with the creating row's work.

## Lifecycle — draft to ready for review

The PRD and the changeset live exactly as long as the PR is a draft.

| Stage | PR | Planning documents |
|---|---|---|
| Planned | none yet, or draft | PRD (when the kind needs one), changeset and discovery companion in `docs/<area>/1-WIP/`; nothing stable links into `1-WIP/` (`docs/AGENTS.md`) |
| In progress | draft | the `[wf]` rows and their TODOs say where it stands; `## Prerequisites` Outcomes fill in |
| Ready for review | ready | **wrapped** — nothing of this PR's left in `1-WIP/` |
| Merged | merged | stable docs and history entries only |

**Draft → ready requires the wrap, with no exception.** A PR leaves draft only once its own
documents are wrapped and that wrap is pushed:

1. Every TODO under the Wrap row done, *Verification executed — result recorded* among them.
2. The `/wrap-context-docs` procedure: State B into the package and feature docs, the PRD applied
   to its feature docs with a changelog entry (`references/prd.md` § *PRD Lifecycle*), the history
   entry written, and the PRD, changeset and discovery companion deleted
   (`references/changeset.md` § *Changeset Lifecycle*).
3. The `[wf]` rows carried into the wrap commit message and the PR body.
4. Then `gh pr ready` — per PR, and bottom-up in a stack, so a predecessor's docs leave `1-WIP/`
   before its successors'.

The Wrap row does all four: steps 8–9 of `/pr-wrap` wrap, push, and then open the PR ready (or
ready the existing draft), so the order holds. Opening the PR is the wrap's last act, not a row of
its own. `.github/workflows/docs-wip-wrap-check.yml` enforces it: a ready
PR that still adds or modifies files under `docs/**/1-WIP/` fails. A PR that stays a draft is not
wrapped, a wrap never waits for the merge, and an ad-hoc PR with no planning documents has nothing
to wrap.

## Workflow rows — one line per step, its TODOs nested under it

Each step is one `[wf]` line, and every checkbox the step has to get through is nested under it.
The rows **and** their TODOs are the changeset's whole progress record — no other section carries a
checkbox — so the state is one grep away and a row resumes where it stopped:

```markdown
- [wf 1] ✅ 2026-10-22 `/plan-red` Plan — PRD, changeset, initial discovery · PRD + this file
- [wf 2] ✅ 2026-10-22 `/plan-red` Red — acceptance and failing lower-tier tests · 14 red @ `abc1234`
- [wf 3] ⏳ `/green` Green — implement until every red test passes ·
  - [x] Parser handles chunked sessions
  - [ ] Saga emits `REQUEST_TOKEN_ASSEMBLY` once per asset
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded
  - [ ] `docs/mapping-pipeline/…/feature.md` — API table updated
```

``- [wf <n>] <status> `<Run with>` <Step> · <Result>`` — the number orders the rows, the status is
one of the five below, the backticked command (with any tags, `` `/green #composer` ``) runs it,
and after ` · ` comes one line of evidence. Under it, `  - [ ] …` / `  - [x] …` (two spaces): only
open and done, because the PR description renders them as GitHub task items. The rows sit together
under `## Workflow`, directly after the header metadata.

**The rows end at Wrap.** What follows the wrap — opening the PR, checks and threads, `/yolo`'s
approval and landing — is a procedure, never a row, and carries no TODO (§ *Post-wrap*).

```bash
grep -E '^(- \[wf |  - \[[ x]\] )' "$cs"                     # every row and TODO, in order
grep -m1 -E '^- \[wf [0-9]+\] (⬜|⏳|⛔)' "$cs"                 # the next row to run
awk -v r='[wf 4]' 'index($0,"- "r)==1{on=1;next} /^- \[wf /{on=0} on&&/^  - \[ \] /' "$cs"   # row 4's open TODOs
grep -rE '^- \[wf [0-9]+\] (⏳|⛔)' docs/*/1-WIP/              # every in-flight change
gh pr view "$N" --json body -q .body | grep -E '^(- \[wf |  - \[[ x]\] )'   # after the wrap
```

**Where the TODOs come from.** The planner writes the plan-derived ones under the row that does
them — implementation milestones under Green, the wrap-time obligations (the old Final Checklist,
always including *Verification executed — result recorded*) under Wrap. A command whose own
procedure has several steps **seeds** its checklist (its file's *Row TODOs*) under its row when the
row starts, after the planner's items, and ticks each as it completes it.

**Optional steps are planned, not assumed.** Where a command's *Row TODOs* mark steps optional
(`/pr-wrap`'s test-quality, production-readiness, clean-code and code-issue passes), the planner
writes the ones this change needs under the row — plainly when it must run, or marked
`(optional)` with the condition when the command should decide from what it finds; a small UI fix
plans none. The command seeds only its always-run steps, skips optional ones nobody planned, runs
or skips each `(optional)` one (a skip is ticked `— skipped: <reason>`, so the row can still close),
and may **add** one as a new TODO when the change's scope grew during the run. Every skip and
addition goes under **Decided without review** with the reason. It never drops a planned TODO.

| Status | Meaning |
|---|---|
| ⬜ | pending |
| ⏳ | in progress — a command is running this row, or a run ended with TODOs still open |
| ✅ `<date>` | done: every TODO under it is `[x]`; the Result says what it produced (commit SHA, counts, PR number) |
| ⛔ | halted — the Result says why and lists the developer's options (§ *Halts*) |
| ➖ | does not apply to this change; the Result says why |

- **The Result** is one line of evidence, never a narrative and never a step pointer — the TODOs
  say where the row stands. Detail belongs in the section the step owns (`## Validation Results`,
  `## Prerequisites` Outcomes, `## Verification`).
- **The rows and TODOs are the developer's to change.** Adding, removing, reordering or renumbering
  a row, swapping its command (`/green` → `/green-100`), or adding, removing or unticking a TODO is
  an edit to the changeset, and commands follow it as written. A command edits only its own row and
  its TODOs, except the resets in step 3.
- The command names an existing command or skill, and its tags are read as if they were in the
  invocation. What each tag means is defined once, in the `behaviour-modifiers` skill
  (`.agents/skills/behaviour-modifiers/SKILL.md`).

## PR description — the rows and TODOs kept in sync

Once a PR exists, its description carries a `## Workflow` section: the rows and their TODOs,
verbatim (the first grep above). A reviewer sees progress on the PR page, and GitHub counts the
nested items as tasks (*x of y*).

**Sync whenever progress moves**: a step that ticks a TODO or closes its row rewrites that section
in the same turn, replacing everything from `## Workflow` to the next `## ` and leaving the rest of
the description alone (`gh api -X PATCH "repos/$repo/pulls/$N" -F body=@<file>`). After the wrap
the description is the only copy left, and the Wrap row writes it final — every row ✅ or ➖, every
TODO ticked. Nothing post-wrap adds a row or a TODO to it; a re-run of a row (`/pr-wrap` after new
commits) is the only edit.

A PR whose branch adds deferred-answer records (a `#yolo` run) also carries a
`## Deferred answers` section, the table from `behaviour-modifiers/references/yolo.md` § 4, synced
the same way in the same turn.

## Presets

The planner writes the preset for the changeset's `(Type, Behaviour)` pair (`pr-lifecycle/references/changeset.md` §1
names the pair), numbered from 1, then the Wrap row numbered on, and adjusts it to the change: a
row that cannot apply is written ➖ with the reason, never left out. The preset is a starting point.
The rows in the changeset are what runs.

| Preset — kind | Step | Run with |
|---|---|---|
| **feature** — Feature · adds; contract change (Migration · changes); Architecture Change · adds / changes | Plan — PRD, changeset, initial discovery | `/plan-red` |
| | Red — acceptance and failing lower-tier tests, committed | `/plan-red` |
| | Green — implement until every red test passes | `/green` |
| **bugfix** — Bug Fix · changes | Plan — changeset (PRD only when user-visible), initial discovery | `/plan-red` |
| | Red — reproduction test, committed | `/plan-red` |
| | Green — fix until the reproduction passes | `/green` |
| **restructure** — Refactor · preserves; Architecture Change · preserves, when the move is expressible as refactoring intents | Plan — restructure changeset, recorded baseline, `plan.jsonl` | `/code-restructuring` |
| | Restructure — apply the plan, baseline still green | `/code-restructuring` |
| **migration** — mechanical Migration · preserves; Architecture Change · preserves, otherwise | Plan — changeset, recorded baseline, initial discovery | `/plan-tdd-migration` |
| | Preservation tests — green against the baseline, committed | `/plan-tdd-migration` |
| | Migrate — preservation tests still green | `/plan-tdd-migration` |
| **rebalance** — Test Rebalance · preserves | Measure and plan — test shape, deletions, replacements | `/plan-test-rebalance` |
| | Red — replacement tests, committed | `/plan-red` |
| | Green — replacements pass, equivalence proven, e2e deleted | `/green-100` |
| **infra** — Infra · toolchain · configuration · preserves | Plan — changeset with a V3 `## Verification` and its before-output | `/plan-ft-dev` |
| | Implement — the recorded command produces the planned after-output | `/green` |
| **test-style** — Test Style · preserves (a suite migrated to fluent) | Plan — changeset with a V2 `## Verification`: each suite's titles, count, coverage and fluent score before | `/plan-ft-dev` |
| | Migrate — the same tests green, coverage not lower, every suite ≥ 8 (`testing/references/fluent-style.md`) | `/green` |
| **stash** — an item on a Roadmap tracker page (`roadmap-driven-development` skill) | Plan and red — changeset with `## Stash Tracker` and its publish TODOs, failing tests | `/roadmap-red` |
| | Green — implement until every red test passes | `/green` |
| **last row** — every preset ends with it | Wrap — validate, clean up, verification, docs, then open the PR ready (a stash publishes its ready marker once the PR is ready) | `/pr-wrap` |

## Post-wrap — procedures, not rows

Once the Wrap row is ✅ the rows are done and the PR is open and ready. What happens after that is
implicit in having a PR, so it is never planned as a row and never carries a TODO — not in the
changeset, not in the wrap commit, not in the PR description. Each procedure reads its state from
GitHub (the head SHA, its checks, its threads, the comments already posted), so a re-run picks up
where the last one stopped without a checkbox to tell it:

| Procedure | Run with | When |
|-----------|----------|------|
| Checks and threads — fix until green on the head SHA, then the readiness check | `/fix-pr` | whenever checks fail or threads arrive; `/next` runs it once every row is done |
| Approve — `#skipreview` once every gate holds | `/yolo` | every `/yolo` run, after `/fix-pr` |
| Land — wait for stack predecessors, then `#automerge` or `merge-async` | `/yolo` | only with `#automerge` in that invocation |

A post-wrap halt has no row to write ⛔ into: it is the summary's **⛔ Needs you**, and the
developer answers by invoking the procedure again with their decision. Approve and Land act on
GitHub on the developer's behalf, so they come from the invocation, never from a changeset line
(`.agents/commands/yolo.md`).

## Step contract

Every command a row names follows these steps. A command's own file links this
section and says only what is specific to it.

1. **Resolve the changeset.** Use the one named in the invocation, else the `docs/<area>/1-WIP/`
   changeset this branch added or modified versus its base. If more than one resolves, halt
   (§ *Halts*) and name the candidates.
   - **After the wrap.** The Wrap step deletes the changeset and copies its rows into the wrap
     commit message and the PR body. Those copies **are** the resolved changeset from then on: a
     branch with no `1-WIP/` changeset whose wrap commit (`git log --diff-filter=D`, step 8 of
     `/pr-wrap`) or PR body carries `[wf]` rows resolves to them, the PR body first. Wrap is the
     last row, so after it a runner reads them there to see that every row is done, and a re-run
     of a row (`/pr-wrap` after the developer added commits) reads and edits them there.
   - **No changeset at all** — no `1-WIP/` changeset and no carried rows. `/pr` also serves
     ad-hoc branches, where it runs without a row and says so in the summary. Every other step
     command halts. (`/fix-pr` never has a row.)
2. **Grep the rows** (§ *Workflow rows*). If the changeset has none — planned before this
   contract, or still carrying the old `| # | Step | Run with | Status | Result |` table — write the
   rows now from the preset for its `(Type, Behaviour)` pair, carrying over any statuses the old
   table had. Mark ✅ only the rows whose work the branch demonstrably holds — a red commit, green
   tests, an open PR — each with that evidence, and say in the turn summary that the rows were
   backfilled.
   - **Rows after Wrap** (PR, Checks and threads, Approve, Land — planned before the rows ended at
     Wrap) are deleted with their TODOs, from the changeset or, after the wrap, from the PR body;
     the summary says so. A pre-review obligation one of them carried is `/fix-pr` Step 7's work;
     an open `Stash:` ready publish is made before the row is deleted (`/fix-pr` Step 0).
   - **A legacy changeset** (no `Behaviour`, no workflow table, progress kept in `## Scope`,
     milestones, acceptance tests, a `## TODO` or `## Final Checklist`) is **converted** first:
     - **The pair.** `Behaviour` follows from `Type` where only one fits (Feature → adds, Bug Fix →
       changes, Refactor · Infra · Test Rebalance → preserves). It is written into the header with
       `(backfilled)`. A `Migration` or `Architecture Change`, or no `Type`, has no single answer.
       Then halt ⛔ asking for the pair (under `#yolo`, a deferred answer read from what the diff
       does to observable behaviour).
     - **The obligations.** Every checkbox moves under the row that does it, as a nested TODO, its
       state kept (`[~]` becomes `[ ]`): Scope deliverables, milestones and acceptance tests under
       the Green row, `## TODO` and Final Checklist items under the Wrap row (or under the row their
       text names). The old checkbox sections lose their boxes, so the rows stay the only progress
       record. Nothing is dropped. An item no row can own halts ⛔ naming it.
     - **The summary** lists the conversion under **Decided without review**: the pair, and the
       count of TODOs moved per row.
3. **Find this command's row.** It is eligible when every row above it is ✅ or ➖. When it is not
   eligible, do none of the command's work. End the turn with a summary naming the first row that
   is not done and its `Run with`. When the command owns several consecutive rows (`/plan-red`
   owns Plan and Red), it runs them in order, closing each before starting the next.
   - A ⛔ row is eligible again. The developer's answer arrives as this invocation's arguments or
     in the conversation. Record the answer in **Result** before acting on it.
   - A ✅ row may be run again (a second `/pr-wrap` after the developer added commits). If the re-run pushes
     commits, every ✅ row below it is reset to ⬜ and its TODOs unticked, because they described
     an older tip.
4. **Mark the row ⏳ and seed its TODOs** — the command's *Row TODOs*, under the planner's items,
   when the row does not carry them yet.
5. **Work through the open TODOs in order, ticking each `[x]` as it is done.** A row that is
   re-run — after a ⛔, or a run that ended mid-way — **resumes at its first open TODO**: ticked
   items are done and are not redone, unless the developer unticked them. Fill `## Prerequisites`
   Outcomes and `## Validation Results` as the work produces them; they are the TODOs' detail.
6. **Close the row.** ✅ only when no TODO under it is open, with today's date and one line of
   evidence; ⛔ with the reason and the options (its open TODOs stay open); or ➖ with why it does
   not apply. The changeset edit is committed with the step's own work. A step that commits nothing
   else commits the changeset alone. When a PR exists, sync its description (§ *PR description*).
7. **End the turn with the summary** (§ *Summary*).

## Halts — instead of asking

A step command never asks a question in the middle of its work and never waits for approval.
Something that needs the developer **halts the row**: write ⛔ with the reason and the options,
commit the changeset, and end the turn with the summary. The developer answers by invoking the
command again (or `/next`) with their decision.

| What used to happen mid-turn | What happens now |
|---|---|
| A review of the step's output — acceptance tests, changeset, applied cleanups, a file split, TODO dispositions | **Removed.** The step goes ahead and lists in the summary under **Decided without review** what the review would have shown |
| A safety stop — broken build, an ancestor stub, nothing red, a leak or unplanned deletions, the same check red on a third push | **⛔ halt**, with the evidence in **Result** |
| A deferral of planned scope | **⛔ halt**. Planned scope is never deferred without the developer's word, and a halt is how that word is asked for. The options are *finish it*, *defer with blocker X* (the TODO record then quotes the decision) or *re-plan* |
| An action the repo reserves for the developer — a new dependency, deleting a file the plan did not name, retriggering CI, a merge | **⛔ halt** that names the action. An explicit invocation argument (`#automerge`) is the decision for the action it names |
| Requirements interviews during planning, **before** the plan is written | **Kept.** Questions that gather input are not review gates |

**Under `#yolo` nothing is asked at all.** A requirements interview, or a ⛔ whose options are all
actions the agent may take itself, becomes a **deferred answer**: recorded, relayed to a supervisor
when there is one, picked, built on and listed in the summary. A halt that asks for the developer's
word (a deferral of planned scope), a safety stop and a reserved action stay halts. The full table
is in `.agents/skills/behaviour-modifiers/references/yolo.md` § 1.

Unplanned follow-up work found along the way is not a halt: record it as a TODO
(`.agents/skills/deferred-work/SKILL.md`) and list it in the summary.

## Commands use procedures, never route

A command may use another command's procedure as one of its own steps — `/pr-wrap` runs the
`/validate-changes` analysis, and a stack branch runs `/pr-stack-rebase` before any work. That
call returns to the caller. What a command never does is decide what runs **after** it: no
"Next: run `/x`", no "go back to `/x`", no "do not run `/y` yet". It closes its row ✅ or ⛔ and
the rows carry on. Where a step finds that an earlier row's work is incomplete (validation
finds gaps against the plan), it halts its own row and names the earlier row in **Result**.

## Runners

- **`/next`** runs exactly one step: the first row that is not ✅ or ➖, with that row's
  `Run with` command and tags. It is the same as invoking that command by hand. Once every row is
  done it runs `/fix-pr`, the post-wrap step.
  `.agents/commands/next.md`
- **`/yolo`** runs the rows in order until every row is ✅ or ➖, or one halts. It then runs the
  post-wrap procedures: `/fix-pr`, **Approve** (`#skipreview`), and with `#automerge` in the
  invocation **Land**. It implies `#yolo` for the whole run.
  `.agents/commands/yolo.md`

Both grep the rows fresh before every step, so a developer edit between steps is honoured.

## Summary

Every step command ends its turn with this summary, and it replaces every review gate the step
used to have:

```markdown
## <command> — <changeset basename>

**Row <k> <step>**: ✅ <evidence> | ⛔ <reason>

### Done
- <what the step did, with commits and counts>

### Decided without review
- <each decision a review gate used to put to the developer: tests written, cleanups applied,
  files split, TODO dispositions, deferrals recorded>

### Deferred answers  (only under #yolo)
| Record | Kind | Question | Asker's pick | Supervisor | Decision |
|--------|------|----------|--------------|------------|----------|
| <path> | Product / Technical | … | … | — / Answered / Refined → … | … |

### ⛔ Needs you  (only when halted)
- <the decision, and the options a) … b) …>

### Next row
<k+1> <step> — `<Run with>` (or: every row is done — post-wrap, `/fix-pr`)
```

Failing tests and open items are marked ❌ / ⚠️ as everywhere else (`README.md` § *ALWAYS*).
The heading names every modifier the step ran under (`## /green #yolo #composer — …`).
