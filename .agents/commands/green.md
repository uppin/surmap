---
description: TDD Green Phase - Implement production-quality code. Quality > test passage.
---
## Green Phase - Implement Quality Code

Implement production-quality code to make failing tests pass. **Code quality > Test passage.** Never compromise code to force tests to pass.

**For the complete workflow, use the `tdd` skill (`.agents/skills/tdd/SKILL.md`).**
**For testing standards, see `.agents/skills/tdd/references/testing-practices.md`.**

## Workflow row

Follows the `pr-lifecycle` skill (`.agents/skills/pr-lifecycle/SKILL.md`). Owns
**Green** (feature, bugfix, story, stash presets), **Implement** (infra) and **Migrate** (test-style).
Result: `<n>/<n> green @ <sha>`; for Implement, that the `## Verification` command now produces the
planned after-output; for Migrate, the after-state against the recorded before-state — same tests
green, every behaviour still asserted, coverage not lower, each suite's fluent score ≥ 8. Migrate
has no red tests: it rewrites test files only, with whatever toolkit fits (`restructure` operations,
a codemod, by hand — `testing/references/fluent-style.md` § *The toolkit*), and touches no production
file. Halts,
beyond the skill's: the ancestor-functionality gate (0b), a restructure prerequisite that cannot
run cleanly (0.5), a test failure you cannot classify (1), a red test this row owns still failing
with no quality fix (2 — **Result** names the tests). The row closes ✅ only when every red test it
owns passes.

**Row TODOs** — seeded under the planner's implementation milestones:

- Stack rebased, ancestor-functionality gate passed (step 0 — stack branch only)
- Restructure prerequisite executed in its own commit (0.5 — only when the changeset has one)
- Red verified, failing tests reviewed (1)
- Every red test this row owns passes with production-quality code (2)
- Planner's milestones and wiring TODOs done or deferred with a record (3)
- Prerequisites Outcomes and deferred-work records reconciled (3.5)
- Committed and pushed with the row (4)

## Composer offload (`#composer-subagent`, `#coder`)

With `#composer-subagent` (or `#composer`) in the request, this command's work is done by the Muse
agent (`agent -p`) on the newest Composer model, driven by a Sonnet · low subagent — the
`composer-subagent` skill (`.agents/skills/composer-subagent/SKILL.md`), stage G, with the
skill's **row consent**. `#coder` does the same on a Coder workspace (`coder-remote` skill) and implies
`#composer-subagent`. The main agent readies the host (guiding the user through a missing Muse agent
CLI or login), runs the preflight, briefs the driver, reports a halt — the row's ⛔, written, committed and pushed by the Muse agent — in its
end-of-turn summary, and verifies the result. Every step of this file still runs; only who types changes.
Only on request — never chosen on the agent's own initiative. Every modifier this command honours,
`#yolo` included, is defined once in the `behaviour-modifiers` skill
(`.agents/skills/behaviour-modifiers/SKILL.md`).

## Prerequisites

1. **Failing tests must exist, failing for the right reasons** — missing implementation, not test
   bugs (an Implement row has no red tests; its input is the `## Verification` command still
   producing the recorded before-output). Step 1 verifies this by running them.
2. **On a stack branch, step 0 comes first**; **a restructure prerequisite, step 0.5**.

## Workflow

### 0. If This PR Is Part of a Stack — Pre-run (HARD GATE)

Detect **before** reviewing tests or writing code. Bind every check to **this branch**. A
`Stack Context` in some other PR's changeset does not make this branch stacked. An empty
`git branch --show-current` (detached HEAD) is **not** a match — do not grep with it.

```bash
BRANCH=$(git branch --show-current)
# 1. Registered stack that includes this branch (fails if this branch is not in a stack)
gh stack view 2>/dev/null | grep -F "$BRANCH"
# 2. This branch's own changeset: same file has ## Stack Context AND this branch name
#    (skip when BRANCH is empty)
if [ -n "$BRANCH" ]; then
  grep -l "## Stack Context" docs/<area>/1-WIP/*.md 2>/dev/null \
    | xargs grep -l --fixed-strings "$BRANCH" 2>/dev/null
fi
# 3. This branch's open PR is based on another stack branch (not trunk)
gh pr view --json baseRefName --jq .baseRefName 2>/dev/null
```

**Stack branch** if (1) lists `$BRANCH`, or (2) returns a file, or (3) returns a base that is not
`master` / `main` / the repo default trunk. Load the `pr-stack` skill
(`.agents/skills/pr-stack/SKILL.md`) and run **0a then 0b before step 1**.

If none of those hit, skip this section — this is an ordinary branch.

Do **not** `grep -l "Inherited Dependencies"` or `grep -l "Stack Context"` across `1-WIP` without
requiring this branch's name in the same file.

**0a. Rebase first — `/pr-stack-rebase`**

Run **`/pr-stack-rebase`** (this branch only) and follow `.agents/commands/pr-stack-rebase.md`.
A ⚠-free `gh stack view` is **not** a skip: this PR must be fully in sync with the latest pushed
ancestor implementation before it starts greening. If the branch is already on the latest base tip
and `origin/<base>..HEAD` is this PR's commits only, that command verify-and-publishes (no rewrite, but it
pushes the branch if the remote lacks this state); that still counts as having run it. **Greening
starts only after the rebased state is on the remote** (`/pr-stack-rebase` Step 4b).

Do **not** start implementation on a stale parent. Do **not** run `gh stack sync` /
`gh stack rebase` from this worktree.

**0b. Ancestor-functionality gate — MUST halt if unmet**

After the rebase, check that **functionality this PR depends on from ancestor PRs is implemented**.
A stacked branch inherits predecessors' **code**, including their stubs. Compiling against a stub is
not the same as depending on its behaviour.

1. Read this PR's changeset: `## Inherited Dependencies — do not implement here` and
   `## Stack Context` → **`### Green wave`** and **Greenable independently?**. The wave is the quick
   read — `**Wave:** 1 of m` means this PR was planned as startable now; any higher wave names the
   predecessor behaviour it waits on. It is a *plan*, though, and this gate is the *fact*: if the
   two disagree, the tree wins and the wave is wrong. Correct it in this PR's changeset.
2. After rebase, inspect each predecessor-owned symbol this PR uses in the current tree. A symbol
   is **still unimplemented** when its body is a planning stub: `NotImplementedError`, a typed
   placeholder, or `TODO(pr-<ancestor>)`.
3. This PR **depends on that functionality** when any of the following is true:
   - The changeset says **Greenable independently? no — blocked by n\<j\>** (node numbers, not PR
     numbers — see the `pr-stack` skill § *Node numbers*; `n<j>` is branch `pr-<j>-<slug>`) and that
     node still owns those stubs.
   - This PR's tests drive the **real** predecessor object (not a test double) and would need its
     behaviour — not merely its signature — to pass.
   - The Inherited Dependencies table describes a runtime call that needs the ancestor's real
     behaviour, not compile-only use of the type.
4. Compile-only use is **not** a dependency on implementation: coding against the stub's signature,
   or injecting a double at the test seam, is how an independently greenable PR proceeds while the
   ancestor is still a stub. Those cases pass this gate.
5. If this PR **does** depend on ancestor functionality that is still a stub: **halt the row ⛔. Do
   not implement anything.** Result and the summary's *Needs you* state:
   - which symbols are still stubs, with file:line;
   - which ancestor PR owns each (number, URL, branch);
   - why this PR needs the real behaviour (which tests / greenability line);
   - that you will **not** implement a predecessor-owned symbol from here.

   The options, for example: a) wait for that ancestor's Green row to land and re-invoke; b) inject
   doubles and proceed as independently greenable; c) drop or rescope the blocked tests; or another
   instruction the developer gives on re-invocation. Do not pick for them. Do not silently continue.

An undeclared dependency is the same halt: if the changeset says independently greenable but the
tests actually require ancestor behaviour that is still stubbed, halt ⛔ — do not start greening
against a lie.

### 0.5. Execute the Changeset's Restructure Prerequisite — BEFORE any implementation

Read this changeset's `## Prerequisites` section. If it has a **Restructure Prerequisite** block,
that restructure runs **now** — before the red review in step 1 and before a single line of
implementation. Implementing on top of a structure you are about to change means writing the code
twice and handing the reviewer a diff that is a behaviour change and a mechanical move at once.

If the changeset has no `## Prerequisites` section, or the section names no restructure, skip to
step 1.

1. **Read the restructure changeset** the block names (`Type: Refactor`, in `docs/<area>/1-WIP/`) and
   load the `code-restructuring` skill (`.agents/skills/code-restructuring/SKILL.md`). Run
   `/code-restructuring` against it.
2. **Baseline carve-out — the one thing that differs from a standalone restructure.**
   `code-restructuring` step 1 treats a red baseline as a stop, and this branch is red on purpose:
   `/plan-red` wrote failing tests here. The baseline is therefore **green everywhere except this
   changeset's own planned red tests**, which the restructure changeset's `## Baseline` lists by
   name as known-red. Anything red that is *not* on that list is still a stop — halt the row ⛔ with
   the failures in Result, and do not restructure on top of it.
3. **The restructure rewrites this changeset's red tests too.** Their imports and paths move with
   everything else, mechanically, through the language service. After the apply, re-run them and
   confirm **each still fails for the same reason it failed before**. A planned red test that went
   *green* during a restructure was not fixed — it was broken, or it was never testing this
   changeset's behaviour. Halt the row ⛔ either way, naming the test.
4. **It implements nothing.** If a seam turns out to need this changeset's behaviour to exist first,
   that is a planning error, not a licence to slide implementation into the restructure. Halt the
   row ⛔ and name the Plan row in Result — the options are a re-sequence of the prerequisite or a
   re-plan.
5. **Its own commit**, before any implementation commit, with the restructure changeset's
   before/after baseline numbers in the message body. Never fold it into an implementation commit.
6. **Delete the code issues it resolved** — `git rm` each `<package-dir>/docs/code-issues/` file the
   block named, in this commit, with the new measurement in the commit message.
   **Delete the spent plan in the same commit** — `git rm -r <package-dir>/restructure/<slug>/` — and
   clear `.restructure/`. A plan is a build input; it does not stay on the branch after its apply
   (`code-restructuring` step 8).
7. Check the box in the changeset's `## Prerequisites` and in the `## TODO` checklist
   (`Restructure prerequisite`).

On a **stack branch**, this runs after step 0's rebase and gate, and only for a restructure this PR
**owns**. A restructure declared under `## Inherited Restructure — expect rewrite` belongs to another
node: you inherit its result through `/pr-stack-rebase`, you never execute it from here.

### 0.9. A Migrate Row (test-style) — no red gate

A **Migrate** row has no red tests by design, so steps 1 and 2 do not apply and *nothing is red* is
not a halt here. Instead (`.agents/skills/testing/references/fluent-style.md` § *Migrating a suite*):

1. **Before-state present.** The changeset's `## Verification` records, per suite, the test titles,
   count, coverage of the production files it exercises and the fluent score with per-test rows.
   Missing → halt ⛔: the Plan row is incomplete.
2. **Baseline green.** Run each suite; anything red that is not recorded as pre-existing is a halt ⛔.
3. **Rewrite** the suites to fluent with whatever toolkit fits — test files only; a production file
   in the diff is a halt ⛔ (that is another kind of change).
4. **After-state.** Same tests green, every before-title still asserted (a renamed test mapped to its
   old title), coverage not lower, each suite's score ≥ 8 with its per-test rows. Record it beside
   the before-state.

Then continue at step 3 (the row's TODOs) and close the row with the after-state in **Result**.

### 1. Verify Red, Then Review the Failing Tests

**Run the tests first — never take "there are failing tests" on faith.** Run the suites the
changeset scopes this work to:

```bash
cd packages/package-name
uv run pytest -q
```

**If nothing is red: halt the row ⛔. The green phase does not run.** Record what you found in
Result and end the turn — do not implement, refactor, or hunt for other work to justify continuing.
Say which of these it is:

- **The planned tests don't exist** — the Red row's work is not on this branch (its commit is
  missing). Result names the Red row as incomplete.
- **All the planned tests already pass** — green was already done here, or (on a stack branch)
  step 0's rebase pulled in an ancestor implementation that satisfies them. Run the
  `/validate-tests` analysis on them and put its verdict in Result; the options are a) the passing
  implementation is the intended one — re-invoke and the row closes ✅ citing the commit that
  satisfied them; b) the tests were weakened into vacuity — the Red row is incomplete.
- **Tests fail to *run*** (build/import/harness errors) — that is not red-for-the-right-reasons;
  fix the harness problem and re-run. When the fault is in the tests themselves, halt and name the
  Red row in Result — do not treat it as license to implement.

**Then confirm each red test is red for the right reason — missing implementation, nothing else.**
Read the actual failure output per test before treating it as work. The right reason looks like an
assertion failing against behaviour that does not exist yet, or a planning stub firing
(`NotImplementedError`, `TODO(pr-<k>)` placeholder). An **environment failure wearing a red suit**
looks like:

- module-not-found / cannot-resolve on a **workspace dependency** — its `dist/` was never built.
  Fresh worktrees hit this constantly: build that dependency first (`uv run mypy`),
  it is a prerequisite, not a finding.
- missing generated code (`src/protogen`, WASM artifacts) after a branch switch — regenerate
  (`gen:protos`, `uv run pytest -q`), don't implement around it.
- ports in use, timeouts, stale caches/venvs, wrong toolchain — infrastructure, not requirements.
- a failure in tests **outside this changeset's scope** — somebody else's problem to triage, not
  this green phase's input.

Fix the environment and **re-run**; only what is still red afterwards is the green phase's input.
Implementing against an environment failure builds the wrong thing to a broken signal — and
"fixing" it by touching the test or the harness config to change the failure shape is the same
mistake. If a test fails for a reason you cannot classify as either, halt the row ⛔ with the failure
output in Result rather than guess.

With red tests confirmed — red for the right reasons — understand what needs to be implemented:
- Which tests are failing?
- What functionality do they require?
- What API do tests expect?

### 2. Implement Production-Quality Code

**On Muse**: delegate this step to the `tdd-implementer` subagent
(`.muse/agents/tdd-implementer.md`), giving it the failing tests' location and names, any context
about the feature, and the expected API. It reports back when done — tests may or may not pass, and
quality is still the priority.

**On other harnesses**: implement directly; the `tdd` skill folds in the same behaviour.

Either way:

- Analyze failing tests to understand requirements
- Implement production-quality code
- Focus on correct, quality implementation
- Verify each step with test runs
- Use minimal but proper implementation
- Keep tests unchanged (unless absolutely necessary)

**IMPORTANT**: If implementation is correct but tests still fail:
- DO NOT compromise code quality to force passage — never hack a test green
- May indicate test issues or incomplete understanding
- Better to have quality code with failing tests than bad code with passing tests — but the row
  then halts ⛔, naming the tests, instead of closing ✅

### 3. Complete the Planner's TODOs Under the Green Row

Some work can only be done **after** the implementation exists and tests pass — most commonly
wiring the **live demos / examples** that a feature ships with so they actually exercise the new
capability at runtime (not just flipping a documentation flag). The originating skill records these
in the active changeset as TODOs under the Green row.

This is a **generic contract** any planning skill can rely on:

1. Locate the active changeset for this work in `docs/<area>/1-WIP/` (the one whose **Related
   Documentation** / scope matches the tests you just made pass).
2. Read the open TODOs under its Green row (an older changeset may still carry them in a
   `## TODOs After the Green Phase` / `## Post-Green TODOs` section). If there are none, skip this step.
3. Execute **every** open one as part of the green phase — these are real
   implementation/wiring tasks, held until now only because they depend on the finished code.
4. Verify each one actually works (e.g. a wired demo must render with no console errors in both its
   panels and any toggles), then tick it `[ ]` → `[x]` in the changeset.
5. If a task genuinely cannot be completed, it is a **deferral**, and a deferral is governed by
   **step 3.5** below. Leave the TODO open, annotate **why** inline, and write the
   `<package-dir>/docs/todo/` file. Never silently drop it.

Do this before declaring the green phase done. The TODOs under the Wrap row (status flags,
changelog entries) are doc bookkeeping for `/wrap-context-docs` and are **not** part of this step.

### 3.5. Reconcile the Deferred-Work Records — and Write the Outcome into the Changeset

Green is the phase that either clears the debt this changeset planned around or admits it did not.
Both outcomes are recorded, in **two places** — and the changeset is the one that is easy to forget,
because it is also the one that gets deleted at wrap. Load the `deferred-work` skill
(`.agents/skills/deferred-work/SKILL.md`) for the formats.

Both records live in the docs of the package they describe: `<package-dir>/docs/todo/` and
`<package-dir>/docs/code-issues/`, where `<package-dir>` is the directory (`mapping-pipeline/mapping-pipeline-server`),
not the npm name.

**3.5a. Write what you actually did into the changeset.** Every row in this changeset's
`## Prerequisites` tables gets its **Outcome** cell filled — one line, concrete, naming the commit
or the file:line where the work landed:

```markdown
| Item | Verdict | Disposition | Outcome |
|---|---|---|---|
| `mapping-pipeline/mapping-pipeline-server/docs/todo/2026-08-14-analyzer-fallback.md` | ⛔ Blocking | Fixed here — see Scope | ✅ **Resolved** — fallback deleted in `a1b2c3d`; `analyzer-port.ts:88` now throws. Record deleted |
| `mapping-pipeline/mapping-pipeline-server/docs/code-issues/oversized-file-session-replay-service.md` | ⛔ Blocking | Restructure prerequisite | ✅ **Resolved** — 940 → 4 files, max 210 lines (step 0.5, `9e8d7c6`). Record deleted |
| `mapping-pipeline/mapping-pipeline-server/docs/code-issues/missing-tests-subasset-processing-service.md` | ⚠ During | Acceptance tests cover it | ◐ **Partly** — `splitSubassets` now entered by the it tier (12% → 71%); `mergeSubassets` still uncovered. Record updated, stays open |
| `mapping-pipeline/mapping-pipeline-server/docs/todo/2026-07-02-subasset-revision-guard.md` | ⚠ During | Must not widen the window | ➖ **Unchanged** — write stayed inside the existing revision check; no new exposure. Record untouched |
```

Do this **before** touching the records, not after: the changeset is where the mapping from *this
changeset* to *that record* exists, and it is the only place a reviewer can see the debt was actually
dealt with rather than merely listed at planning time. An Outcome cell left blank at wrap is
indistinguishable from work nobody did.

**3.5b. Then update the records themselves.** Three states, and the middle one is the one that gets
skipped:

| What green achieved | Record action |
|---|---|
| **Fully resolved** | **`git rm` the file** in the commit that fixes it; the commit message says what closed it and, for a code issue, the new measurement. Git keeps the history; there is no `Resolved` status |
| **Partly addressed** | the record **stays open** and is *updated*: a `Measurement history` row with the improved numbers (or, for a TODO, a `**Progress:**` line), and *What is left* / *What would close it* narrowed to the remainder. Say which PR moved it. A partial fix whose file is deleted is worse than no fix recorded at all — the next planner's Step 2b never sees the remainder |
| **Untouched** (a ⚠ during / — unrelated verdict, or a fix deferred) | leave the record alone. It is already correct, and rewriting it to say "considered again" is churn |

**3.5c. Then account for anything the changeset planned and did not deliver.** The bar is high, and
it is the point of this step:

> **The goal of this changeset is the full scope its PRD and changeset planned.** A TODO file is not
> a scope-reduction lever, not a way to end a long session tidily, and not somewhere to park the part
> that turned out to be hard.

Before writing one for **planned** scope, all four must hold — and if any fails, go back and finish
the work:

1. **Impossible now, not merely expensive** — and you can name the thing that makes it impossible.
2. **Every route around it is wrong** — you named the alternatives and each is *incorrect*, not just
   inconvenient.
3. **The developer consented** — through the skill's planned-scope halt, with the blocker and the
   refuted alternatives; their answer is quoted in the TODO file. A blanket invocation is not that
   answer. An unconsented deferral of planned scope is a silent scope cut.
4. **What remains still ships something coherent.** A half-wired feature is broken, not deferred —
   finish it or halt.

Legitimate: an unpublished `surmap*` type, an unregistered permission scope, another team's
endpoint, a proto not yet republished, a predecessor stack PR still stubbed, a decision the developer
postponed, or work that could only proceed by breaking a repo boundary (a fallback, a
test-environment branch, implementing a symbol another node owns).

**Not** legitimate: it is hard; it is slow; the tests are flaky; the file is enormous; the session is
running long; "we can follow up".

Work the changeset **never planned** is a different thing — a `**Category:** Future enhancement`
entry, welcome and needing no consent.

Each deferral is **one new file**, `<package-dir>/docs/todo/YYYY-MM-DD-<slug>.md`, never an append to an existing
one. It must state *why it could not be done*, *what was done instead* (with `file:line` for every
`TODO`/`FIXME` marker the implementation left), and *when it becomes possible* — that last line is
what `/fix-pr-stack` reads. Then name the file in the changeset row it explains (path in backticks,
not a link), and say so in the summary with a visual indicator. **Silence is not deferral.**

**3.5d. Report it.** The green summary states, per prerequisite: resolved / partly / unchanged /
deferred, and names every record file touched. `/pr-wrap` re-checks this and `/wrap-context-docs`
acts on it — both read the Outcome column, so a gap here surfaces there rather than being lost.

### 4. Commit, Push, Close the Row

Every branch: close the row and commit it **with** the green work — the relevant files only, never
`--no-verify`, never amend — then push. 4a and the milestone cadence in 4b apply only on a stack
branch, after step 0.

**4a. Stack branch — stay inside this PR's boundary**

- Implement **only the symbols this PR owns** — the `TODO(pr-<this-k>)` stubs planning left for you.
- **Never implement a predecessor-owned symbol**, however small the stub looks. The changeset's
  `## Inherited Dependencies — do not implement here` table lists them; they stay stubs in this
  branch. Two PRs implementing the same symbol is a guaranteed conflict, and the owning PR's tests
  are the ones specifying it.
- **Never implement successor behaviour**, and never make a test here assert it.

**4b. Commit and push**

Work sitting unpushed in one worktree is invisible to reviewers — and, on a stack branch, which is a
successor's **base** and a row in a registered stack, to every successor. So when green finishes:

```bash
git add <the green work> docs/<area>/1-WIP/<changeset>.md
git commit                        # never --no-verify, never amend
git push origin $(git branch --show-current)
gh stack view                     # stack branch: confirm no ⚠ on this branch
```

On a stack branch the cadence below applies.

**Do not save it all for the end.** The end of green is the *latest* a stack branch may be pushed, not
the cadence: push **each milestone** as it lands — an owned symbol going stub → real, a test group
going green, a Green-row TODO wired, and above all a **signature change to an owned symbol**, which
goes out on its own immediately because successors compile against it. Successors only get behaviour
you have pushed; anything held locally keeps them building against a stub.

**A milestone is production code that already passes its tests** — a finished slice, not a progress
checkpoint. Two hard preconditions: the slice's own tests are green (run them), and the branch still
**builds**. Other tests in this PR may still be red for parts you have not implemented yet; never the
ones covering what you just pushed. **Never push half-finished implementation to "share progress"** —
scaffolding or code that works for one case is worse for a successor than the stub it replaces, because
a stub is honestly unimplemented while half-working behaviour surfaces as *their* bug. Not finished and
green? Leave the stub and push when it is.

When a milestone clears a successor that a later green wave was waiting on, **say so** and update that row in
so that worktree knows to run `/pr-stack-rebase` and pick it up. Its `## Stack Context` is theirs to
update, not yours to edit from here.

If the push is rejected because the base moved, **do not** run `gh stack sync` / `gh stack rebase`
from this worktree — they cascade over the whole stack and will fail on (or clobber) branches pinned
by other worktrees. Run **`/pr-stack-rebase`**, which rebases and force-pushes this branch only.

**4c. Summary** — the commits and the step 3.5d report under **Done**; tests touched and why, and
deviations from the changeset's design, under **Decided without review**. On a stack branch, keep
this worktree: the changeset's remaining rows run here too.

## What NOT to Do

- ❌ Don't add workarounds to make tests pass
- ❌ Don't add a test that is not fluent — a test green adds (a missed edge, a coverage gap) meets
  the same bar as the red ones (`.agents/skills/testing/references/fluent-style.md`)
- ❌ Don't use environment detection to force passage
- ❌ Don't ignore errors indicating real problems
- ❌ Don't hardcode values just to pass tests
- ❌ Don't add `process.env.NODE_ENV === 'test'` branches
- ❌ Don't add try/catch blocks just to swallow errors
- ❌ Don't refactor existing code (unless necessary)
- ❌ Don't add extra features not covered by tests
- ❌ Don't focus on optimization or performance
- ❌ Don't make significant test structure changes
- ❌ Don't leave a gap with no record — an open TODO, an unwired demo, or a `TODO` in code with
  nothing in `<package-dir>/docs/todo/` explaining it

**CRITICAL**: If tests fail, fix the implementation, not the test.

## Implementation Quality Principles

**CRITICAL**: Never compromise these for test passage:

### ✅ Acceptable - Quality Production Code

```python
# ✅ Real production implementation
def process_frame(frame: StereoFramePair) -> FrameResult:
    if frame.calibration_id not in KNOWN_CALIBRATIONS:
        raise ValueError(f"unknown calibration: {frame.calibration_id}")
    return backend.process_frame(frame)
```

**If tests fail with this quality code:**
- Document why they fail
- Investigate test vs. implementation mismatch
- DO NOT add workarounds

### ❌ NOT Acceptable - Compromised Code

```python
# ❌ Hardcoded for tests
def process_frame(frame: StereoFramePair) -> FrameResult:
    if frame.frame_id == 1:  # the fixture's first frame
        return FrameResult(1, frame.t_ns, Pose(Vec3(4.0, 5.0, 6.0)), ())
    return FrameResult(frame.frame_id, frame.t_ns, None, ())

// ❌ Test-specific branch
if (process.env.NODE_ENV === 'test') {
  return mockData;
}

// ❌ Workaround to force passage
try {
  return realImplementation();
} catch {
  return fakeResult; // Just to make test pass
}
```

**These are NEVER acceptable** - even if tests fail without them.

## Keep It Clean

Never put "red phase" or "green phase" in code comments, test descriptions, or production code.

## Update Documentation

**If a changeset or dev doc exists**: update it with implementation status, and record any
`FIXME`/`TODO` markers the implementation introduced (`file:line`) so they are not lost. A marker
that stands for **deferred planned scope** also needs its `<package-dir>/docs/todo/` file (step 3.5) — the
marker says where, the file says why and who agreed.

## Success Criteria

- ✅ Quality implementation complete (production-quality, not fake)
- ✅ Minimal implementation (no over-engineering)
- ✅ Tests remain largely unchanged
- ✅ No workarounds added
- ✅ Code quality NOT compromised
- ✅ Every red test the row owns passes — else the row is ⛔, never ✅
- ✅ Steps 0–3.5 done as written: the Green row's TODOs, the restructure prerequisite, every
  `## Prerequisites` Outcome cell, and the deferred-work records reconciled

**See also**: `/green-attack` (exploratory alternative), `/green-100` (the coverage-gated variant),
`/validate-changes` (checks the implementation against the plan), the `code-cleaning` skill
(refactor; on Muse, the `refactor` subagent).
