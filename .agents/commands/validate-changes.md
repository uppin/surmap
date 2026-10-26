---
description: Analyze code changes for risks in test infrastructure, production code, security, and code quality
---
## Validate Changes

Analyze code changes to identify risks and issues. Also validates documentation when no context documents exist.

## Context Documents

Look for:
- Changeset: `docs/<area>/1-WIP/YYYY-MM-DD-*.md`
- PRD: `docs/*/1-WIP/YYYY-MM-DD-*.md`
- Dev docs: `packages/{package}/docs/*.md`

## Workflow

### 0. Stack detection and rebase — HARD GATE before any code diff

Detect whether this branch is part of a PR stack **before** any `git diff`, `git log` of the
delta, or file-by-file analysis. A stacked `HEAD` contains its predecessors' commits; diffing it
(against `master`, or against a stale merge-base) reports ancestor work as this PR's — or tempts
an agent to "clean" the extra files by deleting predecessor code.

```bash
BRANCH=$(git branch --show-current)
# 1. Registered stack that includes this branch
gh stack view 2>/dev/null | grep -F "$BRANCH"
# 2. This branch's own changeset: same file has ## Stack Context AND this branch name
if [ -n "$BRANCH" ]; then
  grep -l "## Stack Context" docs/<area>/1-WIP/*.md 2>/dev/null \
    | xargs grep -l --fixed-strings "$BRANCH" 2>/dev/null
fi
# 3. This branch's open PR is based on another stack branch (not trunk)
gh pr view --json baseRefName --jq .baseRefName 2>/dev/null
```

No hit (and base is trunk / no PR) → ordinary branch; skip to step 1 and diff against `master` as
usual. An empty `$BRANCH` (detached HEAD) is **not** a match — do not grep with it. Do **not**
`grep -l "Inherited Dependencies"` across `1-WIP` without requiring this branch's name in the same
file.

A hit on (1) listing `$BRANCH`, or (2) a file, or (3) a base that is not trunk → **stack branch**.
Everything below is **required** before step 4 (and before any other code-diff command in this run):

1. Load the `pr-stack` skill (`.agents/skills/pr-stack/SKILL.md`).
2. **Always run `/pr-stack-rebase`** (this branch only) — follow
   `.agents/commands/pr-stack-rebase.md`. A ⚠-free `gh stack view` is **not** a skip. If the branch
   is already on the latest base tip and the commit range is this PR only, that command
   verify-and-publishes without rewriting (it pushes the branch if the remote lacks this state);
   that still counts as having run it. Nothing below starts until the rebased state is on the
   remote.
3. **Do not execute a code diff** until `/pr-stack-rebase` has finished **and** the leak check
   passed: `git log --oneline origin/<base>..HEAD` contains **only this PR's own commits**. Any
   predecessor commit in that range is leaked ancestor work.
4. If the leak check fails, or `/pr-stack-rebase` cannot produce a leak-free range: **STOP**. Report
   it as 🔴 Critical. Do **not** run `git diff`, do **not** treat extra files as this PR's scope,
   and do **not** delete them to shrink the diff. The fix is rebase/`--onto`, never checkout or
   `git rm` of predecessor files.

The resolved base from `/pr-stack-rebase` is the only base later steps may diff against.

### 1. Check for changeset document
```bash
find docs -path "*/1-WIP/*.md" -exec grep -l "🚧 In Progress" {} \;
```

### 2. If changeset exists
Read it, extract implementation progress, identify affected packages.

### 3. If NO changeset exists
- **Code changes**: Start a changeset per the `pr-lifecycle` skill § *Start a changeset*
  (`.agents/skills/pr-lifecycle/SKILL.md`), its rows backfilled from what the branch holds, and name
  the backfill in the report
- **Doc-only changes**: Skip changeset, validate documentation quality

### 4. Analyze actual code changes

**Forbidden until step 0's gate has passed on a stack branch.** Do not run the diffs below — and do
not run `git diff master...HEAD` at all — while there is any risk of leaked ancestor commits.

On a stack branch, `base` is the one `/pr-stack-rebase` resolved. On an ordinary branch, `base` is
`master`.

```bash
git fetch origin "$base"
git diff "origin/$base...HEAD" --name-only
git diff "origin/$base...HEAD" --stat
git diff "origin/$base...HEAD"
```

On a stack branch the file list must contain **only this PR's own files**. Anything else means the
base is wrong or a predecessor's work leaked in — 🔴 Critical, stop analysis, do not delete the
extra files.

### 5. Sync changeset with code reality
For each item, check if code implements it. Update statuses:
- ✅ Complete, ⚠️ In Progress, 🔲 Not Started
- Add new items for code changes not in original changeset

### 6. Build Validation

Identify affected packages, then build each one — package-level builds, never a full-repo sweep:
```bash
git diff "origin/$base...HEAD" --name-only | cut -d'/' -f1-2 | sort -u
uv run mypy
```

Report per package: ✅ Pass · ⚠️ Warnings (changed code only) · ❌ Failed · ℹ️ CI-only.

**Known build limitations** (not failures):
- `surmap`: requires `ARTIFACT_VERSION` and `SRC_MD5` env vars (set in CI)
- `surmap` packages: may require CI-specific configuration

**If a build fails**: mark 🔴 Critical and block the PR until resolved.
**Exception**: known CI-only builds — verify via type-check + tests instead.

### 6a. Documentation Validation (only when no context documents exist)

Run this when there is no active changeset in `docs/<area>/1-WIP/` and no active PRD in
`docs/*/1-WIP/`, or when the changes are documentation-only.

**Feature documentation** (against `.agents/skills/planning/references/feature-doc.md`):
- Product area structure (`1-OVERVIEW.md`, correct titles)
- Feature document standards (correct template, acceptance criteria, status indicators)
- Asset management (all `appendices/` files referenced, no orphans)
- Changelog format (no broken PRD links, release note style, says "PRDs" not "amendments")

**Development documentation** (against `.agents/skills/planning/references/dev-doc.md`):
- Package README standards (single README, < 150 lines, no implementation details)
- Detailed docs structure (`<workspace>/<package>/docs/` exists, comprehensive)
- Changesets history format (no broken changeset links, release note style, reverse chronological)

### 7. Analyze each changed file for:

**Test Infrastructure Risks**: Mock implementations in production, test-only code paths
**Production Code Risks**: Hardcoded values, missing error handling at trust boundaries (I/O, user
input, external services), redundant error handling inside trusted paths (catch-and-rethrow, checks
the types already rule out), type escapes (`as any`, `as unknown as T`, unexplained `@ts-ignore`)
**Security & Validation**: Exposed secrets, unvalidated inputs, injection vulnerabilities
**Code Quality**: Long functions (>40 lines), deep nesting (>3 levels), magic values, duplication
**Deletion Safety**: unplanned removals of files or code this PR is not supposed to delete — see
**step 7a**

### 7a. Deletion safety — required on every branch

The diff must not remove code this PR is not supposed to delete. Run this against the **same
`base` as step 4**, and only after the step 0 gate (stack) has passed.

```bash
git diff "origin/$base...HEAD" --diff-filter=D --summary    # deleted files
git diff "origin/$base...HEAD" --numstat                    # net line deletions per file
git diff "origin/$base...HEAD" --diff-filter=M              # removed hunks inside modified files
```

Treat each of the following as 🔴 Critical unless the changeset/PRD **explicitly** called for that
removal:

| Check | Failure looks like |
|---|---|
| **Unplanned file deletion** | A path in `--diff-filter=D` that the changeset/PRD does not name as a removal |
| **Unplanned large removal** | A modified file loses a substantial region (function, module, fixture, docs) with no matching changeset item |
| **Scope trespass by deletion** | Deleted path is outside this PR's owned files / affected packages |
| **Predecessor-owned deletion** (stack) | A file or symbol an ancestor PR owns is deleted, emptied, or has its stub stripped |
| **Inherited stub gone** (stack) | A `TODO(pr-<other-k>)` that exists at `origin/<base>` is missing at `HEAD` |
| **Leaked-then-deleted** (stack) | Extra ancestor files appeared in the diff and were removed to "clean" it — that destroys predecessor work; rebase instead |

For a stack branch, also verify every row in the changeset's
`## Inherited Dependencies — do not implement here` still **exists** in the tree at `HEAD` (the
stub or predecessor implementation, not a hole). `grep` each listed symbol; a miss is critical.

**Never "fix" a too-large stacked diff by deleting the extra files.** Extra files mean the base is
wrong or ancestor commits leaked — go back to step 0 / `/pr-stack-rebase`, do not `git rm`.

Record every deletion (planned or not) in the report. Planned deletions pass only when they map to
a changeset item. Unplanned deletions make the verdict 🔴 (S4).

## Output Format

```markdown
## Change Validation Report

### Context Documents
- Changeset: `docs/<area>/1-WIP/YYYY-MM-DD-name.md` (✅ existing | 🆕 created)
- PRD: `docs/<area>/.../1-WIP/YYYY-MM-DD-name.md` (if applicable)

### Changeset Sync Results

**Sync Status**: ✅ Synced | ⚠️ Partially Synced | 🔄 Updates Applied

| Changeset Item | Old Status | Actual Code Status | Updated To |
|----------------|------------|--------------------|------------|
| Feature X | 🔲 Not Started | ✅ Implemented (a.ts, b.ts) | ✅ Complete |

### Stack Rebase Gate
- Stack branch: yes | no
- `/pr-stack-rebase`: ran · already current / rebased · leak-free ✅ | 🔴 leak STOP (no code diff)

### Deletion Safety
| Check | Result |
|-------|--------|
| Deleted files (`--diff-filter=D`) | none / list, each mapped to a changeset item or 🔴 unplanned |
| Unplanned large removals | none / list |
| Predecessor-owned code intact (stack) | ✅ / 🔴 missing |
| Inherited stubs still present (stack) | ✅ / 🔴 missing |

### Files Analyzed
- file1.ts (X lines changed) — [maps to changeset item #1]
- file3.ts (Z lines changed) — [❌ not in changeset scope]

### Risk Summary
| Category | Issues Found | Severity |
|----------|--------------|----------|
| Build Validation | X | Low/Medium/High |
| Changeset Alignment | X | Low/Medium/High |
| Test Infrastructure | X | Low/Medium/High |
| Production Code | X | Low/Medium/High |
| Security | X | Low/Medium/High |
| Code Quality | X | Low/Medium/High |
| Deletion Safety | X | Low/Medium/High |

### Issues Detail

#### 🔴 Critical (must fix)
1. **[file:line]** Description — why it's a problem, suggested fix

#### ⚠️ Warnings (should fix)
#### ℹ️ Info (consider)

### Test Impact
- Tests affected: X
- New tests needed: Y
```

## Stack Mode — when this branch is part of a PR stack

Step 0 already detected the stack and ran `/pr-stack-rebase`. If that gate did not pass, **this
section does not run** — there is no code diff to validate. Ordinary branch → skip this section.

Load this PR's changeset `## Stack Context`: branch, base, owned API surface, green wave,
greenability.

### S0. Rebase is already done — do not skip, do not re-diff against master

`/pr-stack-rebase` ran in step 0. Do not run a second independent `git diff master...HEAD`. The only
legal delta is `origin/<base>...HEAD` after that rebase, and only if the leak check passed.

If a later step (build, push, a nested `/validate-changes` from `/pr-wrap`) would read a code diff
again, the same rule holds: **no diff while a leak is possible**. `/pr-wrap` re-invokes
`/pr-stack-rebase` at its own start for the same reason.

### S1. Confirm the PR's own file list against the rebased base

```bash
base=<resolved-base>   # from /pr-stack-rebase — never assume master
git diff "origin/$base...HEAD" --stat
git log --oneline "origin/$base..HEAD"          # still this PR's commits only
gh pr view <N> --json changedFiles,baseRefName
```

The file list must contain **only this PR's own files**. Anything else means the base is wrong or a
predecessor's work leaked in — 🔴 Critical, **stop**, do not delete the extra files.

Then run **step 7a** (deletion safety) against this same range: predecessor-owned files and
inherited stubs must still exist at `HEAD`.

### S2. Validate implementation against the plan

Beyond the normal risk analysis, check the branch against **the plan this PR was created from**:

| Check | Source of truth | A gap looks like |
|---|---|---|
| Every changeset item implemented | this PR's changeset | an item still 🔲/⚠️ with no code behind it |
| Every acceptance criterion met | this PR's PRD | a criterion with no test and no implementation |
| Owned API surface finished | this changeset's `## Stack Context` → Owned API surface | a `TODO(pr-<this-k>)` stub body still throwing |
| Tests green for the right reason | the red-phase tests | a test still failing on **this** PR's missing code |
| Green row's TODOs done | the TODOs under the changeset's Green row | an open TODO with no deferral reason |
| **Inherited boundary respected** | changeset `## Inherited Dependencies — do not implement here` | a predecessor-owned symbol implemented **here** |
| **Green wave still true** | changeset `## Stack Context` → `### Green wave` vs. what is actually red | `**Wave:** 1 of m` on a PR whose tests need a predecessor's behaviour, or a wave that contradicts `Greenable independently?` |
| **Inherited code still present** | same table + `origin/<base>` tree | a predecessor-owned file/stub **deleted** here |
| No successor work | the successor PR's own changeset, or `gh stack view` | code or a test covering a later PR's surface |

Find leftover and trespassing stubs quickly:

```bash
grep -rn "TODO(pr-" <pkg>/src        # TODO(pr-<this-k>) left → gap; other TODO(pr-N) implemented → trespass
```

**Implementing an inherited symbol is a defect, not extra credit** — it collides with the PR that owns
it, and that PR's tests are the ones specifying it. Report it as critical and revert it to the stub.

A test still red because a **predecessor** is red is *not* a gap, provided the changeset's
`Greenable independently?` line already says so. Record it as blocked-on-n\<j\> — the node number
the changeset uses, `n<j>` being branch `pr-<j>-<slug>` — not as failure.

If the changeset does **not** say so, the wave is the thing that is wrong, not the test: this PR was
planned as startable and is not. Correct **this PR's own** `### Green wave` and
`Greenable independently?` together (they are one fact), update the `## Stack` block in this PR's
description to match, and report it — a stale "startable now" is what sends the next implementer
into a PR that cannot go green. Never edit a sibling's row to compensate.

### S3. Commit and push the current status — required

Run this **after** applying the changeset updates described in the next section — those updates are
the PR's status as reviewers and successors will see it, so they must be on the remote, not sitting in
this worktree:

```bash
git add -A && git commit          # never --no-verify, never amend
git push origin $(git branch --show-current)
```

If the push is rejected because the base moved, run **`/pr-stack-rebase`** again (this branch only),
then **re-run the leak and deletion checks before any new code diff**. Do **not** run
`gh stack sync` / `gh stack rebase` from a per-PR worktree — they cascade over the whole stack and
fail on, or clobber, branches pinned by other worktrees.

### S4. Report the verdict — never route

`/validate-changes` is a procedure, not a `## Workflow` row: it reports one of three verdicts and
returns. The caller — `/pr-wrap` steps 1 and 6, or the developer —
acts on the verdict under the step contract (`.agents/skills/pr-lifecycle/SKILL.md`): a
🔴 or ⚠️ verdict halts the caller's row ⛔ and names, in **Result**, the earlier row whose work is
incomplete.

**Leak or unplanned deletion** → the diff is not safe to treat as this PR's work (may already have
stopped in step 0 or 7a):

> 🔴 **Diff unsafe** (`<branch>`, PR #N of stack `<stack-name>`): leaked ancestor commits and/or
> unplanned deletions (including predecessor-owned files or inherited stubs). The repair is
> `/pr-stack-rebase` (never `git rm` the extra files) and restoring any deleted predecessor code;
> the diff is not wrappable until a re-run of `/validate-changes` passes.

**Gaps remain** → the implementation is not done:

> ⚠️ **Gaps vs plan** (`<branch>`, PR #N of stack `<stack-name>`): status committed and pushed.
> Remaining: <list, each mapped to its changeset item / acceptance criterion / unfinished stub>.
> The implementation row (the changeset's Green / Restructure / Migrate row) is incomplete.

**No gaps** → the PR matches its plan **and** the rebase/deletion gates passed:

> ✅ **Implementation matches plan** (`<branch>`, PR #N of stack `<stack-name>`): `/pr-stack-rebase`
> ran and the commit range is this PR only; every changeset item and acceptance criterion
> implemented, owned surface complete, inherited symbols untouched (not deleted), diff limited to
> this PR's files, no unplanned deletions. Status committed and pushed.

Never report ✅ with open gaps, a failed leak check, or unplanned deletions. Never end
stack mode without having pushed **unless** the leak gate failed in step 0 — then there is no
status commit to push, and the repair is `/pr-stack-rebase`, not a push of a leaked tree.

## Update Changeset

Always update the changeset's three named sections:
1. **Implementation Progress** — sync all items with actual code state, and set
   `**Last Synced with Code**: YYYY-MM-DD (via /validate-changes)`
2. **Validation Results** — under `### Change Validation (/validate-changes)`: status, risk level,
   analysis summary
3. **Refactoring Needed** — under `### From /validate-changes (Code Quality)` and, when documentation
   was validated, `### From /validate-changes (Documentation Quality)`

**Key Principle**: After validation, changeset = source of truth for implementation state.

## Related

**Commands**: `/pr-wrap` (runs this procedure in steps 1 and 6), `/pr-stack-rebase` (**always**
before any stack code diff), `/green`, `/plan-pr-stack`
**References**: `.agents/skills/coding/references/coding-practices.md`,
`.agents/skills/pr-lifecycle/references/changeset.md`,
`.agents/skills/planning/references/feature-doc.md`,
`.agents/skills/planning/references/dev-doc.md`
**Skill**: `pr-stack` (`.agents/skills/pr-stack/SKILL.md`) — when this branch is part of a PR stack
