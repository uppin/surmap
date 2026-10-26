---
description: Comprehensive PR preparation - validate, refactor, validate cycle; apply every cleanup and file split, solve in place every code issue this PR added, decide each open TODO and list the decisions in the summary; halts the Wrap row instead of asking
---
## PR Wrap - Prepare Changes for Pull Request

Orchestrate comprehensive PR preparation through validation and refactoring cycles.

**Goal**: Ensure code is clean, maintainable, tested, and production ready.

## Workflow row

Follows the `pr-lifecycle` skill (`.agents/skills/pr-lifecycle/SKILL.md`). Owns
**Wrap**. Result: the wrap commit SHA, the file-split and code-issue counts, `docs wrapped`; the
wrap deletes the changeset, so step 8 carries the `[wf]` rows forward. Halts, beyond the skill's: gaps
against the plan (steps 1, 6 — **Result** names the incomplete implementation row, e.g. *row 3
Green: 2 acceptance criteria unimplemented*); a file split that cannot reach the same green, or a
failed split cascade (step 4); an oversized, non-fluent test file this PR grew — migrate here or
hand off is the developer's call, decided by the PR's share of the file under `/yolo` (step 4); an
Outcome nobody can determine or an unrecorded deferral (7.5a,
7.5b, 7.6); a code issue this PR added that will not close after two attempts (7.6); tests or
type-check still red with no quality fix (step 7).

**Row TODOs — which steps run is planned in the changeset.** The planner writes the Wrap row's
TODOs from this catalogue; a small UI fix does not need production-readiness or test-quality review.

- **Always** — seeded when missing, after the planner's wrap obligations: rebased, leak check passed
  (0 — stack only) · changes validated against the plan (1) · file-length gate passed (4) · final
  validation (6 — only when steps 1–5 changed code) · lint, type-check and tests green (7) ·
  prerequisites reconciled (7.5 — only with `## Prerequisites`) · every TODO row decided (7.6b) ·
  docs wrapped, rows and TODOs carried into the wrap commit and PR body (8) · stack readiness gate
  passed (9 — stack only)

Opening the PR ready, or readying the draft (step 9), is the row's closing act, not a TODO. Neither
is anything that runs after it (`pr-lifecycle` skill § *Post-wrap*): never seed or carry a TODO for
the PR, its checks or its review.
- **Always when the diff adds or edits a test file**: test quality and fluent readability
  validated (2) — the fluent bar is not optional for tests this PR wrote
- **Optional, planned per change**: test quality validated (2, when no test file changed) ·
  production readiness validated (3)
  · clean-code fixes applied (5) · code issues measured and solved in place (7.6a)

An optional step is planned one of two ways: as a plain TODO, which runs, or marked
`(optional)`, which this row decides at run time from the diff it wraps —
`  - [ ] (optional) Production readiness validated (3) — run if the diff reaches server code`.

The row runs the TODOs under it in order. It **skips an optional step nobody planned**; an
`(optional)` one it either runs and ticks, or ticks as `— skipped: <reason>`. When the change's scope
grew during the run — the diff touches production code or tests the plan did not cover, or a new
package — it may **add** an optional step as a new TODO. Every skip and addition is listed under
**Decided without review** with the reason. It never removes a planned TODO.

## Composer offload (`#composer-subagent`, `#coder`)

With `#composer-subagent` (or `#composer`) in the request, this command's work is done by the Muse
agent (`agent -p`) on the newest Composer model, driven by a Sonnet · low subagent — the
`composer-subagent` skill (`.agents/skills/composer-subagent/SKILL.md`), stage W, with the
skill's **row consent**. `#coder` does the same on a Coder workspace (`coder-remote` skill) and implies
`#composer-subagent`. The main agent readies the host (guiding the user through a missing Muse agent
CLI or login), runs the preflight, briefs the driver, reports a halt — the row's ⛔, written, committed and pushed by the Muse agent — in its
end-of-turn summary, and verifies the result. Every TODO under the row still runs; only who types changes. Step 7.6 decides without review here too, and a halt comes back as the Wrap row's ⛔.
Only on request — never chosen on the agent's own initiative. Every modifier this command honours,
`#yolo` included, is defined once in the `behaviour-modifiers` skill
(`.agents/skills/behaviour-modifiers/SKILL.md`).

## Stack Branches — read first

If this branch is part of a PR stack (`gh stack view` succeeds, or its changeset carries a
`## Stack Context` section that
lists it), the rules below apply on top of the steps.

- **Step 0 — always run `/pr-stack-rebase` first** (`.agents/commands/pr-stack-rebase.md`, this
  branch only), before any validation that reads a code diff. A ⚠-free `gh stack view` is **not** a
  skip; an already-current branch is verify-and-publish, which still counts. **No code diff may run
  while there is any risk of leaked ancestor commits** — including the nested `/validate-changes`
  in steps 1 and 6, which rebase again (cheap when current); do not skip either.
- The nested `/validate-changes` runs execute in **stack mode**: they commit and push the branch
  and return a verdict; a gap, leak or unplanned deletion halts this row (steps 1, 6).
- **Never `gh stack sync` / `gh stack rebase` from this worktree** — they cascade over the whole
  stack. `/pr-stack-rebase` is the only rebase path from here.
- **Wrapping covers this PR's stack documentation too** — its changeset, its PRD, and the shared stack
  `## Stack Context` section — all of it inside this PR's own changeset. See step 9.
- **A stacked PR goes up for review only with no WIP of its own left** — own docs wrapped, own boxes
  ticked, own `TODO(pr-<this-k>)` stubs implemented. Inherited stubs owned by
  another PR are not WIP and stay untouched — **do not delete them**.
- **Mark ready per-PR** (`gh pr ready <N>`), never `gh stack submit --open`, which flips every PR in
  the stack — including drafts still being implemented.
- **The worktree stays** — the post-wrap procedures (`/fix-pr`, `/yolo`'s Approve and Land) run
  in it. It is removed only once they are done (by `/yolo-pr-stack`'s own removal step, or by the developer), never by the Wrap row, and
  never the branch (a successor bases on it). See the worktree rules in the `pr-stack` skill
  (`.agents/skills/pr-stack/SKILL.md`).

## Prerequisites

- Current changes committed (never with `--no-verify`, never amended)
- Changeset document in context (if applicable): `docs/<area>/1-WIP/YYYY-MM-DD-*.md`
- PRD document in context (if applicable): `docs/*/1-WIP/PRD-YYYY-MM-DD-*.md`

## Steps (Execute in Order)

### 0. Stack rebase — HARD GATE (stack branches only)

Detect a stack the same way `/validate-changes` does (`gh stack view`, this branch in a changeset,
`Inherited Dependencies`). Ordinary branch → skip to step 1.

Stack branch → **required, not optional**:

1. Load the `pr-stack` skill (`.agents/skills/pr-stack/SKILL.md`).
2. Run `/pr-stack-rebase` (this branch only) — always, before step 1. Tree must be clean
   (prerequisites: current changes committed).
3. Confirm the leak check passed: `git log --oneline origin/<base>..HEAD` is **only this PR's
   commits**. If it is not, **halt the row ⛔** (leak). Do not start `/validate-changes`, do not run
   `git diff`, and do not delete extra files to shrink the diff.
4. Confirm the rebased state is **on the remote** (`git rev-parse HEAD origin/<branch>` match —
   `/pr-stack-rebase` Step 4b pushes it). If it could not be published, **halt the row ⛔**.
5. Do not proceed to step 1 until this gate passes.

### 1. Validate Changes → Refactor
Run `/validate-changes` → Fix issues found. On a stack branch this nested run rebases again before
it diffs. If it reports a leak, unplanned deletions or gaps against the plan, **halt the row ⛔** —
the repair is restoring predecessor code / rebasing (never deleting extra files), or finishing the
implementation row the gap belongs to. Name it in **Result**.

Fix **every** issue the validators in steps 1–3 report, Minor included. There is no "deferred with a
reason" escape for a cleanup.

### 2. Validate Tests → Refactor
Run `/validate-tests` → Fix test issues

**Fluent readability** (`/validate-tests` § *Fluent Readability Score*,
`.agents/skills/testing/references/fluent-style.md`). Every test this PR wrote or edited reaches
**≥ 8** with checks 3 and 9 passing, and every suite it created reaches a suite score of 8 — rewrite
until they do, at the same tier, asserting the same behaviour; there is no deferral for a test this PR
wrote. Suites this PR only added to are **not** rewritten here: the ones below 7 go to step 7.6a as
`non-fluent-tests` findings, attributed pre-existing. Report the PR's minimum score and every suite
below 7 in the summary.

**A finding is persisted, whatever was planned.** When step 2 finds a suite below 7 (or step 4
hands an oversized test file off), step 7.6a runs even if the planner did not plan it: add it to the
row as a TODO, list the addition under **Decided without review**, and let `/analyze-code-issues`
write the `non-fluent-tests` record. A finding that never becomes a record never reaches a migration.

### 3. Production Readiness → Refactor
Run `/validate-prod-ready` → Fix production readiness issues

### 4. File Length Gate → Restructure

Check every source file this PR touched against the 500-line limit (the "Source File Length" metric
of `/analyze-clean-code`) **before** quality scoring. This gate exists because per-PR growth is
invisible in a diff review: `chat_tools.py` reached 2082 lines through ~25 individually-wrapped PRs.
It covers **all** tracked extensions — including `.py` and `.rs`, which `/analyze-clean-code`'s
changed-file grep does not pass — and diffs the **whole PR range**, not `HEAD~1`:

```bash
base=$(gh pr view --json baseRefName --jq .baseRefName 2>/dev/null || echo master)
git fetch origin "$base" --quiet \
  || { echo "GATE ERROR: cannot fetch origin/$base — fix before proceeding, do not skip" >&2; exit 1; }
mb=$(git merge-base "origin/$base" HEAD) \
  || { echo "GATE ERROR: no merge-base with origin/$base — fix before proceeding, do not skip" >&2; exit 1; }
changed=$(git diff --name-status -M "$mb"..HEAD -- \
    '*.ts' '*.tsx' '*.js' '*.jsx' '*.mjs' '*.cjs' '*.mts' '*.cts' '*.rs' '*.py') \
  || { echo "GATE ERROR: git diff against $mb failed — fix before proceeding, do not skip" >&2; exit 1; }
printf '%s\n' "$changed" | while IFS=$'\t' read -r status old new; do
    [ -n "$status" ] || continue
    f=${new:-$old}                                         # R/C rows carry old<TAB>new; use the new path
    [ -f "$f" ] || continue                                # skip deletions
    now=$(wc -l < "$f" | tr -d ' ')
    was=$(git show "$mb:$old" 2>/dev/null | wc -l | tr -d ' ')   # old path at base; 0 only for true adds
    [ "$now" -ge 500 ] && printf '%s → %s\t%s\n' "$was" "$now" "$f"
  done
```

An empty or unresolvable base must **abort the gate loudly**, never let it pass vacuously — a
missing `origin/$base` with an unguarded `merge-base` yields an empty range and a silently green
gate. Renames are resolved (`--name-status -M`): an unchanged 600-line file renamed by the PR
counts as `600 → 600` (alert-only case below), not as a fake `0 → 600` crossing.

**Alert in the summary**: every file the loop prints appears in this step's output **and** in the final
summary (step 10) as a 🔴 line with its before → after line counts — a clean quality score in a later
step never absorbs or silences this alert. Then act by case:

| Case | Action |
|------|--------|
| This PR pushed the file past 500 lines | 🔴 **Decompose now** |
| File was already ≥ 500 and this PR grew it further | 🔴 **Decompose now** |
| File was already ≥ 500 but this PR did not grow it | ⚠️ Alert only — add it to the changeset's Refactoring Needed section and flag it in the summary |

**Decompose** — by language:

- **Python**: load the `code-restructuring` skill and run `uv run mypy`
  (`.agents/skills/code-restructuring/SKILL.md`) and split each breaching file into focused modules
  (< 300 lines each where practical — the ⭐⭐⭐ bucket). The skill's execution discipline applies in
  full — green baseline before, engine-driven intents, same green after.
- **Python (and any other language the skill rejects)**: there is no refactoring engine here — split
  by hand under the same discipline: green test baseline before, mechanical moves only (no behaviour
  change), imports updated, same green after.
- **A test file** (any language): **migration to fluent comes first** — it is the No. 1 priority,
  and a non-fluent test file is never split as it is (`.agents/skills/testing/references/fluent-style.md`
  § *Oversized test files come first*). Score it. At 8 or above, split it like any other file. Below
  8, **whether this PR rewrites it is the developer's decision**
  (§ *When a PR grows an oversized, non-fluent test file*): halt the row ⛔ with *a) migrate it in
  this PR* · *b) hand it to a migration PR*; under `/yolo` the PR's share of the file decides —
  ≥ one third of the legacy lines → migrate here, below → hand off. Migrating here means the whole
  file under the test-style proof (same tests green, every behaviour still asserted, coverage not
  lower), then splitting only what is still ≥ 500. Handing off means a `non-fluent-tests` record
  with `**Priority:** 1` and a history row carrying the decision, and no split. In the alert-only
  case, file that record next to the `oversized-file` one.

Unless the test file was handed to a migration PR (above — then nothing is split here), the split
lands **in this PR**: record the module layout and before → after line counts
in a Restructuring section of this PR's existing changeset. When the `code-restructuring` skill is
entered from this gate, that section **stands in for** the skill's own `Type: Refactor` changeset
(and its initial-discovery companion) — skip the skill's changeset step rather than opening a second
changeset for the same PR.

- **An oversized file is a code issue, never a TODO — and it is written to the code-issue
  convention, not just mentioned.** Whenever step 4 prints a file (decomposed, alert-only or
  deferred), `<package-dir>/docs/code-issues/` must hold its record when the step ends:
  1. Run `/analyze-code-issues` on the package; it reconciles first (step 7a–7e) and writes
     `oversized-file-<file-slug>.md` (**no date prefix**, identity is category + file + symbol).
  2. If the record exists, **update** it (7f): append a Measurement history row with before → after
     lines and this PR; `git rm` the file when the split landed (the commit message carries before → after);
     keep it `Open` when it did not. Never create a second file for the same file.
  3. If the analyzer did not surface it (step 4's line count is the detector), still write it in the
     7g format with `**Detected:**` naming `/pr-wrap` step 4, a `**Restructure:** required` line, and
     a mandatory *Verified by hand* section.
  4. Prove it, including what is not committed yet (step 4's moves and the record are usually
     uncommitted when this runs): `{ git diff --name-only "$mb" -- '*/docs/code-issues/oversized-file-*.md'; git ls-files -o --exclude-standard -- '*/docs/code-issues/oversized-file-*.md'; } | sort -u`
     lists the record for every printed file (the first half compares the working tree and index to
     `$mb`, the second finds untracked files). A printed file with no record is a failed step.
  Never write a `docs/todo/` file for a split, and never invent a TODO category for one.
- **A decomposition this PR caused is never deferred by this command.** The split lands here. When it
  cannot — the split will not reach the same green, so it is reverted — **halt the row ⛔** with the
  options *a) re-plan the split* · *b) defer with a named blocker* (the code-issue record's history
  row then quotes the developer's answer). That halt is the only way a split is deferred, besides the
  oversized non-fluent test file handed to a migration PR (above), and one more
  exception: when `/yolo-pr-stack`'s Stage W brief assigns a stack-shared file to the sweep node,
  that brief is the recorded decision, and the record's history row names the sweep node.
- A file this PR did **not** grow, but which the analyzers flag, is a
  `<package-dir>/docs/code-issues/` record and the next planner's Step 2b problem — file it and move on
  rather than splitting it here (`/analyze-code-issues` step 7).
- **On a stack branch — a file that predecessor or successor PRs also modify — split here, then
  cascade.** The rename fallout is repaired, not avoided:
  1. **Publish the split first.** This command does not otherwise push until step 9,
     `/code-restructuring` leaves its moves uncommitted, and `/pr-stack-rebase` refuses a dirty or
     unpushed worktree. So once the split is green, commit it (with the code-issue record change)
     and `git push` before any cascade.
  2. **Cascade the whole tail.** Rebase **every** layer above this branch, bottom-up, as one
     contiguous range (`/pr-stack-rebase` cascade mode over the PR range, each layer in its own
     worktree), whether or not a given layer touches the file: skipping a layer leaves its
     descendants based on the pre-split tip. Each rebased layer must reach the same green.
  3. **A failed cascade never reverts the split.** `/pr-stack-rebase` pushes layers one by one and
     stops on the first failure, so earlier successors are already published on top of the split,
     and reverting it here would leave them on a removed tip. **Halt the row ⛔** instead: **Result**
     names the layers that moved and the layer that failed and why; the split stays in place.

  Never write a `docs/todo/` split record for a stack-shared file.

### 5. Code Quality → **MUST Refactor**
Run `/analyze-clean-code` → **Immediately apply every fix identified** before moving to step 6.
Do NOT just report findings and continue. Every issue MUST be resolved in code — Critical, Major
**and Minor**. List the fixes applied under **Decided without review** in the summary.

**Cleanups preserve behaviour.** Every fix in this step is a refactor: behaviour stays the same, and
step 7's tests must stay green. A real bug found while cleaning is a separate finding — fix it in its
own commit and name it in the summary; never fold it into a cleanup. Keep each edit minimal and
limited to lines this PR added. Slop in pre-existing code goes in a `<package-dir>/docs/code-issues/`
record, not into a step-5 fix.
**On a stack branch: do not apply a cleanup that deletes predecessor-owned files, inherited stubs,
or any path this PR does not own.** Those are not dead code; they belong to another PR.

### 6. Final Validation
Re-run `/validate-changes` — ensure no new issues introduced. On a stack branch this nested run
invokes `/pr-stack-rebase` again before it diffs (verify-and-publish when already current). If it
reports a leak, unplanned deletions, or new gaps vs the plan, **halt the row ⛔** (as in step 1).

Tests or type-check still red after this step and step 7, with no quality fix available, is a
**⛔ halt** too. The answer is never a workaround.

### 7. Linting & Type Checking

Targeted runs only — lint is already changed-files scoped; type-check and test run in the affected
packages, never as a full-repo sweep:
```bash
uv run ruff check src tests
uv run pytest -q
uv run pytest -q
```

### 7.5. Reconcile the Deferred-Work Prerequisites — before wrapping

The changeset is about to be **deleted**. Its `## Prerequisites` section is the only place the
mapping from *this change* to the records it addressed is written, so this is the last point at which
that knowledge can be moved. Load the `deferred-work` skill
(`.agents/skills/deferred-work/SKILL.md`). Both records live under the package they describe:
`<package-dir>/docs/todo/` and `<package-dir>/docs/code-issues/`.

If the changeset has no `## Prerequisites` section, skip this step.

**7.5a. Every Outcome cell must be filled.** `/green` step 3.5a fills them; this is the gate.

```bash
# rows whose Outcome cell is still the planning placeholder
grep -n 'filled by `/green`' docs/<area>/1-WIP/<changeset>.md
```

A blank or placeholder Outcome is **indistinguishable from work nobody did**, and wrap treats it that
way: determine what actually happened to that item, and fill it. Do not guess from the
diff — if you cannot tell, **halt the row ⛔** and name the item.

**7.5b. Check each record matches its Outcome.** The two can drift, because `/green` writes them in
separate steps and a later refactor pass may have moved the numbers again:

| Outcome says | The record must say | If it does not |
|---|---|---|
| ✅ **Resolved** | the file is **deleted** (`git rm`), its closing line and — for a code issue — the new measurement in the commit message | delete it now |
| ◐ **Partly** | still **open**, with the improved numbers as a `Measurement history` row (or a `**Progress:**` line for a TODO) and *What is left* / *What would close it* narrowed to the remainder | update it now |
| ➖ **Unchanged** | untouched | nothing to do |
| ⛔ **Deferred** | a TODO file exists with a named blocker and the developer's recorded decision (their answer to a ⛔ halt) | **halt the row ⛔** — an unrecorded deferral is a silent scope cut, not a wrap-time detail |

**Re-measure before believing a ✅ on a code issue.** The refactor passes in steps 1–6 of this
command move exactly the numbers these records track — a file split in step 4 or a cleanup in step 5
can have closed an issue nobody credited, or brought back one whose record was deleted. Where it is cheap, re-run
the relevant `/analyze-code-issues` slice for the touched package and update the record's
`Measurement history`. Where it is not, say in the summary that the ✅ rests on green-phase numbers
rather than a re-measurement.

**A ◐ Partly is a legitimate wrap state and often the honest one.** A partial fix whose record is
deleted as ✅ Resolved is worse than no fix recorded at all: the next planner's Step 2b never sees the
remainder.

**7.5c. Delete exactly the records this PR resolved.** They live in
`<package-dir>/docs/{todo,code-issues}/`, not in `docs/<area>/1-WIP/` (which wrap empties). A ✅
Resolved row means its record is `git rm`'d in this PR. ◐ Partly and ➖ Unchanged records, and every
record the PR did not touch, stay. A ✅ row whose file is still present, or a deleted file whose row
is not ✅, is a failed step.

Report in the step-10 summary: per prerequisite, its Outcome and what happened to its record; every
record file touched; and anything left ◐ Partly or ⛔ Deferred, with a visual indicator.

### 7.6. Unresolved TODOs and code issues this PR added — decided here

**Before wrapping docs or marking ready**, every deferred-work record **this PR introduced or left
open** gets a decision. Code issues this PR added are **solved in place**; open TODO rows take this
command's own recommendation. Nothing waits for the developer: the table and every decision go into
the summary under **Decided without review**, and into the PR body. The developer did not see them
before the PR went up, so they have to be visible after.

Load the `deferred-work` skill (`.agents/skills/deferred-work/SKILL.md`).

```bash
base=$(gh pr view --json baseRefName --jq .baseRefName 2>/dev/null || echo master)
git fetch origin "$base" --quiet
mb=$(git merge-base "origin/$base" HEAD)

# Records this PR added (new files) or edited, still open
git diff --name-only --diff-filter=A "$mb"..HEAD -- '*/docs/todo/*.md' '*/docs/code-issues/*.md'
git diff --name-only "$mb"..HEAD -- '*/docs/todo/*.md' '*/docs/code-issues/*.md'
```

**7.6a. Code issues: measured, then refactored away.** This PR leaves the code no worse than it
found it. That holds for an issue added in the implementation row just as much as one added here:
the gate runs over the whole PR range (`$mb..HEAD`), not over the last step. It is measured, not
judged from the diff.

1. **Analyze and persist.** Run `/analyze-code-issues` (`.agents/skills/analyze-code-issues/SKILL.md`)
   on every package this PR touched, with coverage merged across tiers. Its step 7 **writes** the
   records to `<package-dir>/docs/code-issues/` in the record convention
   (`<category>-<file-slug>.md`, no date, `deferred-work/references/code-issue-record.md`),
   reconciling against what is there. The tool writes them; you do not hand-write a finding.
2. **Attribute each record**, using the diff against `$mb`:

   | Record | Belongs to | Action |
   |---|---|---|
   | **added** since `$mb`, or its symbol is in a file this PR created or overlaps lines this PR added or changed — **including anything the implementation row introduced** | this PR | **refactor it away now** |
   | existed at `$mb` but its numbers got worse since | this PR | **refactor it away now** |
   | existed at `$mb`, on code this PR did not touch, same numbers | pre-existing | leave the record as the analyzer wrote it and list it in the summary |
   | `non-fluent-tests` on a suite that **existed at `$mb`** — added or updated now, even though this PR added tests to the file | pre-existing (the legacy tests it scores were already there; step 2 already holds the PR's own tests to 8) | keep it, list it in the summary — it bubbles up to the stack's sweep or a softening node (`fluent-style.md` § *Migrating a suite*) |

3. **Refactor** each "this PR" record at its root: split the function or file, cover the branch at
   the tier the rhombus rule picks, remove the `any`, delete the dead code. Same discipline as step 5.
   Never use a suppression comment, a threshold tweak or an ignore list. Where the fix is a
   restructure, it goes through `/code-restructuring` with the same green before and after.
4. **Delete the record in the fixing commit.** Once the code is fixed, `git rm` its record in that
   commit and put the before → after numbers in the message. Never mark it `Resolved`, never leave it.
5. **Re-run** `/analyze-code-issues` on the touched slice. The gate passes only when it writes no
   record attributable to this PR, and
   `{ git diff --diff-filter=A --name-only "$mb" -- '*/docs/code-issues/*.md'; git ls-files -o --exclude-standard -- '*/docs/code-issues/*.md'; } | sort -u`
   is **empty** (the first half compares the working tree and index to `$mb`, the second finds
   untracked files; a record added and deleted inside the PR leaves no trace, which is the point) —
   bar `non-fluent-tests` records on suites that existed at `$mb`, which the row above attributes
   pre-existing. The check that applies the carve-out:

   ```bash
   # Records added since $mb that count against this PR — a non-fluent-tests record on a suite that
   # existed at $mb is pre-existing and is skipped. Must print nothing.
   { git diff --diff-filter=A --name-only "$mb" -- '*/docs/code-issues/*.md'
     git ls-files -o --exclude-standard -- '*/docs/code-issues/*.md'; } | sort -u | while read -r r; do
     case "$(basename "$r")" in non-fluent-tests-*)
       pkg=${r%/docs/code-issues/*}
       suite=$(sed -n 's/^\*\*Location:\*\* `\([^`]*\)`.*/\1/p' "$r")
       # a suite this PR renamed lives under its old path at $mb
       base=$(git diff -M --name-status "$mb" -- | awk -F'\t' -v n="$pkg/$suite" '$1 ~ /^R/ && $3 == n {print $2}')
       git cat-file -e "$mb:${base:-$pkg/$suite}" 2>/dev/null && continue ;;
     esac
     echo "$r"
   done
   ```
6. **Convergence:** if a record survives **two** refactor attempts, or a fix keeps creating another,
   **halt the row ⛔**. The record stays on the branch as the analyzer wrote it; **Result** says what
   was tried and why it would not close. A code issue this PR added is never filed as accepted debt
   to let the row finish.

**7.6b. TODO rows: the recommendation is the decision.** Build **one table**:

| Include | How to find it |
|---|---|
| TODO files this PR **created** that are still Open | new paths under `<package-dir>/docs/todo/` (a TODO file this PR created and also resolved is never listed — it was deleted) |
| Prerequisite rows left ◐ Partly or ⛔ Deferred | step 7.5 — even if the file pre-existed, this PR owns the remainder |
| Unchecked changeset boxes with no TODO file | a deferral that was never recorded — **halt the row ⛔**, do not wrap over it |

Decide each row by its recommendation. **Recommend, do not just enumerate**: a small remainder
inside this PR's own files usually belongs in this PR; a remainder that would grow a reviewed diff
late, or that belongs to another stack node, usually belongs in a follow-up.

| Recommendation | Effect on this command |
|---|---|
| **Solve in this PR now** | implement it here, then re-run steps 1–7.5 over the change. **At most once per run** — a second "solve now" becomes recorded debt |
| **Follow-up PR** | write the plan pointer into the TODO file (`**Progress:**` / a one-line plan pointer — whether it is stacked or off `master` after this lands) and continue |
| **Leave as recorded debt** | continue, and mark the row ⚠️ accepted debt in the summary |

An unrecorded deferral of **planned** scope is not a disposition choice: it is the skill's
planned-scope halt. `/fix-pr-stack` later reads the TODOs this step records.

**Do not bury this in the quality-score paragraph.** Lead the summary's **Decided without review**
with it when the table is non-empty:

```markdown
### Unresolved TODOs and code issues this PR added

| Kind | Path | What remains | Decision |
|---|---|---|---|
| TODO | `mapping-pipeline/…/docs/todo/YYYY-MM-DD-….md` | … | follow-up PR / ⚠️ recorded debt / solved in this PR |
| Code issue | `mapping-pipeline/…/docs/code-issues/….md` | CRAP 42 → 8 | solved in place (`abc1234`) |
```

If the table is **empty**, say so in one explicit line — *"This PR added no open TODOs or code
issues."* — so silence cannot be mistaken for a skipped step.

### 8. Update & Wrap Documentation

**This is the mandatory step of the draft → ready transition** (`pr-lifecycle` skill
§ *Lifecycle*): the PR goes up for review next, so its documents are wrapped now — never earlier,
never after merge. A PR meant to stay a draft does not run this row; the developer leaves it ⬜.
Reviewers then read the feature and dev docs the change produced, not a changeset describing a
delta.

Run the `/wrap-context-docs` procedure: transfer State B into the feature/dev docs, add the
changelog entry, delete the changeset/PRD from `1-WIP`, and delete `{slug}-initial-discovery.md`
(do not merge it into package docs). A ⛔ stop it reports (an Outcome still `(filled by /green)`, an
open TODO with no TODO file, an incomplete changeset) halts the Wrap row with its options.

**Capture what the PR body needs first.** The changeset's `## Summary` (what the branch delivers),
the verification that ran and the step 7.6 table are read **before** the wrap deletes the
changeset — and its `## Stash Tracker`, when it has one, for step 9's ready publish.

**Carry the `[wf]` rows with their TODOs.** The wrap deletes the changeset, and its `[wf]` lines
and the TODOs nested under them go with it. Close the Wrap row ✅ in their last copy and carry them
forward verbatim:

- **Into the wrap commit's message**, always — the rows and TODOs under a `Workflow:` line. Git
  keeps it, so whichever row runs next can read it from the commit that deleted the changeset
  (`git log --diff-filter=D -1 --format=%B -- docs/<area>/1-WIP/<changeset>.md`).
- **Into the PR body**, when the PR already exists (a stacked draft, or a re-run): the
  `## Workflow` section, synced per the `pr-lifecycle` skill § *PR description* — read from the
  changeset **before** it is deleted, with the Wrap row's TODOs ticked.

**A re-run after the wrap** (the developer added commits to a wrapped PR) resolves the rows from the
PR body (step contract, step 1 *After the wrap*) — there is no changeset left to delete. It sets the
Wrap row ⏳, unticks the TODOs the new commits invalidate, runs steps 1–7 over the commits since the
wrap commit, and in this step runs `/wrap-context-docs` in its *Post-wrap Mode* — the new commits'
diff is the State B source, the already-wrapped docs are the targets, and the re-wrap writes its own
history file —
in a commit declared as a wrap (`Docs-Wrap: /wrap-context-docs`). Then it closes the row ✅ in the PR body. Step 9 finds the PR
already ready and only pushes.
- **Deferred answers**, when this branch added any (a `#yolo` run): the PR body's
  `## Deferred answers` table, one row per record
  (`git diff --diff-filter=A --name-only "$mb" -- 'docs/*/deferred-answers/*.md' '*/docs/deferred-answers/*.md'`).
  The wrap never deletes a record. Only the developer's review closes one
  (`deferred-work` skill, `references/deferred-answer-record.md`).

Wrap is the last row, so this copy is final: every row ✅ or ➖, every TODO ticked. Nothing after
the wrap adds to it.

In a stack, ready and wrap **bottom-up**, so each predecessor's docs leave `1-WIP` before its
successors' — that is what the forward-only linking rule depends on.

**Before wrapping**: execute every open TODO under the Wrap row — the planner's wrap-time
obligations, formerly the Final Checklist (see `.agents/skills/pr-lifecycle/references/changeset.md` §17). This includes ProgressTable
status updates, FeatureDemo `done` flag flips, Guidelines.mdx ✅ markers, architecture-diagram
updates (the `### Architecture Diagram` spec in `## Technical Changes`, applied to the diagram file
declared in the owning `README.md`), and the
`docs/architecture.md` file. Only once none of them is open: update changeset progress and
wrap.

**No spent restructure plan may go up for review — on every branch, stacked or not.** A
`plan.jsonl` is a build input that `restructure apply` consumed; once the baseline is green again it
describes coordinates in a tree that no longer exists (`code-restructuring` step 8):

```bash
git ls-files '*/restructure/*/plan.jsonl'    # must print nothing
```

Any hit: `git rm -r` its `<package-dir>/restructure/<slug>/` directory in this PR, and record in the
restructure changeset's `## Plan` section the operation count and the commit that applied it.

### 9. Open the PR Ready — Stack Docs and Readiness Gate First on a Stack

**Every branch** ends the wrap here: the title is corrected (below), the branch pushed, and the PR
opened ready — or the existing draft marked ready. An ordinary branch skips straight to *Correct
the title*; the stack docs and the readiness gate are a stack branch's.

**Stack branch — required, not optional.** `/wrap-context-docs` runs in **Stack Mode**: it wraps only
the docs this PR owns, never touches a predecessor's or successor's documents, and keeps forward links
to successors as PR numbers rather than `1-WIP` paths.

**Nothing hands off.** This PR's stack context is a `## Stack Context` section of its own changeset,
so it is wrapped and deleted with it. There is no shared manifest, no cross-branch push, and no
"action required" notice — a wrap touches only the branch it runs on.

If this branch still carries a `docs/<area>/1-WIP/STACK-*.md`, it predates this model: fold each row into
the matching PR's changeset `## Stack Context` and delete the file rather than pushing it anywhere.

Then enforce the **readiness gate — no WIP of this PR's own may remain**:

| Check | Passes when |
|---|---|
| Own changeset wrapped out of `docs/<area>/1-WIP/` | content transferred into package docs, source deleted |
| Own `{slug}-initial-discovery.md` deleted from `docs/<area>/1-WIP/` | deleted, not merged into package docs |
| Own PRD wrapped out of `docs/*/1-WIP/` | same, or deferred with a written reason |
| No open TODO under any row before Wrap | every TODO `[x]`, or annotated **and** backed by a `<package-dir>/docs/todo/` file |
| Every `## Prerequisites` **Outcome** cell filled | ✅ resolved / ◐ partly / ➖ unchanged / ⛔ deferred — no `(filled by /green)` placeholders left (step 7.5a) |
| Every record matches its Outcome | resolved records deleted, partly-addressed updated and left open, deferred backed by a TODO file (step 7.5b) |
| Unresolved TODOs / code issues this PR added | step 7.6: code issues this PR added solved in place; **every TODO row has a decision**, listed in the summary and PR body; empty table stated explicitly |
| Deferred answers this PR added are surfaced | every added `deferred-answers/` record has its row in the changeset's `## Deferred Answers` section, the PR body's `## Deferred answers` section and the summary, and is carried into the history entries (`/wrap-context-docs` step 7c); none deleted by the wrap |
| Restructure prerequisite executed | its own commit, before any implementation commit |
| No spent restructure plan | `git ls-files '*/restructure/*/plan.jsonl'` prints nothing — every applied plan deleted (step 8) |
| `grep -rn "TODO(pr-<this-k>)" <pkg>/src` | no hits — this PR's own stubs are implemented |
| No `wip:` / `fixup!` commit left | unless the PR lands squashed |
| `/pr-stack-rebase` ran and leak check passed | `origin/<base>..HEAD` is this PR's commits only |
| No unplanned deletions | `/validate-changes` step 7a passed — predecessor-owned files/stubs still present; deleted paths map to the changeset |

**Inherited `TODO(pr-<other-k>)` stubs are NOT this PR's WIP** — they belong to the PR that owns them
and must stay untouched. Only this PR's own `k` counts.

### Correct the title before marking ready — MANDATORY

**This is the last moment the title can be fixed.** A squash merge turns it into the commit message
on `master` permanently; retitling a merged PR changes the PR page and leaves the commit untouched.
This repo already carries the evidence:

```
4c428f7bc feat(surmap-server): proto-derived tool schemas — machinery and red tests (1/6) (#2134)
177658c04 feat(surmap-training): M1c stubs + red tests — LoRA + SFT backends (#2062)
```

Both shipped working features. Re-read this PR's title and check every line:

- **It states what the branch delivers, in its finished state.** The title was written at planning,
  before the implementation existed, and green phases move scope. The changeset's `## Summary` is
  usually the corrected wording.
- **No process artifact**: `red`, `green`, `stubs`, `failing tests`, `WIP`, `phase N`, `M1c`.
- **Not a branch slug** — `pr 4 production wiring` is what a tool leaves behind when nobody replaces
  it.
- **Format** (stack PRs): `<type>(<package>): <what it delivers> (#<stack-slug> K/N)`, with `K/N`
  matching the stack's current shape.

  **Read the slug from the PR's own current title**, not from the changeset. Wrapping *deletes* the
  changeset, so by the time this step runs its `## Stack Context` may already be gone — and the same
  is true for any later `/add-to-pr-stack` or `/split-pr-to-stack` on a stack whose lower PRs have
  wrapped. The title was set with the slug at planning, which makes it the one source that survives:

  ```bash
  slug=$(gh pr view <N> --json title --jq '.title' | grep -oE '\(#[a-z0-9-]+ [0-9]+/[0-9]+\)$' \
         | grep -oE '#[a-z0-9-]+' | tr -d '#')
  ```

  If that yields nothing (the title was never set in the format), read it from this branch's
  changeset **before** the wrap step deletes it, and say so in the report.
- **Subject ≤ 100 characters** after `: `, including the trailing group — and remember GitHub
  appends ` (#<pr>)` on squash merge, so budget ~8 more characters than the title shows.

```bash
title="<type>(<package>): <what it delivers> (#<slug> <K>/<N>)"
subject="${title#*: }"
# Must ABORT, not warn: `[ … ] || echo …` succeeds, so a bare warning would fall straight through
# to the PATCH and apply the overlong title anyway.
if [ ${#subject} -gt 100 ]; then
  echo "Subject is ${#subject} chars (max 100 before GitHub appends ' (#PR)'). Shorten it." >&2
  exit 1
fi
repo=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
gh api -X PATCH "repos/$repo/pulls/<N>" -f title="$title" --jq '"#\(.number) → \(.title)"'
```

Use `gh api`, **not** `gh pr edit --title` (Projects-classic GraphQL fault in some  orgs).

Then push and open **this PR** ready:

```bash
git push origin $(git branch --show-current)
gh pr ready <N>            # an existing draft — per-PR; NEVER `gh stack submit --open`
gh stack view              # stack only: expect ○ open, no ⚠ on this branch, base still the predecessor
```

With no PR yet, open it ready with `/pr`'s *Creation of the PR* procedure (its body carries the
`## Workflow` section exactly as step 8 left it). `gh stack submit --open` would mark every PR in
the stack ready, publishing drafts still being implemented. Wrapping adds no commit to any other
branch, so no successor is left `⚠` by this step. Leave the worktree in place — `/fix-pr` runs in
it.

**A Stash-tracked change** then makes the ready publish from the `## Stash Tracker` captured in
step 8 (`roadmap-driven-development` skill § *Publish*): once `gh pr view <N> --json isDraft` is
false, `PR #<N> · ready for review` next to the item, the reconcile, and the `--resolve` ids of the
threads marked *addressed* — in manual mode, the advice in the summary. It is part of opening the
PR, so it has no TODO.

### 9.5. Readiness check — not the wrap's

Wrap does not dispatch review and does not wait for CI. The readiness check
(`check:pr-ready`) runs post-wrap, in `/fix-pr` Step 7, immediately before an exact-head review is
dispatched — it is never seeded or carried as a TODO. What the wrap owes it is the declaration: a
wrap commit declares itself with a `docs(<scope>): wrap ...` subject or a
`Docs-Wrap: /wrap-context-docs` trailer, and ordinary fix commits must not hand-edit package docs
after a wrap.

### 10. Summary
The skill's summary, in the format below: every 🔴 file-length alert from step 4, the step 7.6
table leading **Decided without review**, the PR it opened or readied (`#<N>`), and on a stack
branch the readiness-gate result. **Next row** is the next-row grep over the carried `[wf]` lines —
none after Wrap, so it names the post-wrap step, `/fix-pr`.

## Output Format

```markdown
## /pr-wrap — <changeset basename>

**Row <k> Wrap**: ✅ wrapped @ <sha> · <N> files split · <M> code issues solved | ⛔ <reason>

### Done
| Step | Action | Status |
|------|--------|--------|
| 0 | /pr-stack-rebase (stack: always, before any diff) | ✅ / n/a |
| 1 | /validate-changes → code-cleaning | ✅ |
| 2 | /validate-tests (incl. fluent score) → code-cleaning | ✅ / ➖ not planned (no test file changed) |
| 3 | /validate-prod-ready → code-cleaning | ✅ / ➖ not planned |
| 4 | file length gate → code-restructuring | ✅ / 🔴 N files ≥ 500 (split) |
| 5 | /analyze-clean-code → code-cleaning | ✅ / ➖ not planned |
| 6 | /validate-changes (final) | ✅ |
| 7 | lint:fix + type-check | ✅ |
| 7.5 | reconcile deferred-work prerequisites | ✅ |
| 7.6 | code issues solved in place; TODO rows decided | ✅ empty / ⚠️ N open (decisions below) |
| 8 | /wrap-context-docs + `[wf]` rows carried | ✅ |
| 9 | stack: readiness gate → title corrected → PR opened ready / `gh pr ready` | ✅ #<N> |

- **File Length**: ✅ none ≥ 500 / 🔴 `<file>`: was → now (decomposed)
- **Code Quality**: X/10 ⭐
- **Tests**: All passing ✅
- **Test readability**: PR's tests min X/10 (fluent ≥ 8 ✅) · suites below 7 recorded: `<paths>` / none
- **Production Ready**: ✅ Yes
- **Documentation**: ✅ Wrapped

### Decided without review
- Unresolved TODOs and code issues this PR added — the step 7.6 table with its decisions
  *(If empty: "This PR added no open TODOs or code issues.")*
- Cleanups applied (steps 1–3, 5), Minor included
- Files split (step 4), with module layout and before → after line counts
```

## Rules
- Follow the row's TODOs in order; wait for each to complete; never skip a planned or always-run step
- Don't wrap incomplete changesets
- Don't proceed with failing tests
- **Never delete predecessor-owned files or inherited stubs** to shrink a stacked diff. Extra files
  mean leaked ancestor commits; rebase, do not `git rm`.
