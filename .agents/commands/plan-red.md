---
description: Plan feature and write failing tests - PRD, changeset, acceptance tests, and red phase
---
## Plan Red - From Requirements to Failing Tests

Combines planning and test-first development into a single flow: gather requirements, create documentation, write acceptance tests, and write failing unit/integration tests.

**Prerequisites**:
- User has described the feature or change they want to implement
- Context about affected code/packages (if modifying existing features)

## Workflow row

Follows the `pr-lifecycle` skill (`.agents/skills/pr-lifecycle/SKILL.md`). It is the
planner: it writes `## Workflow` from the preset Step 0 picks, then owns **Plan** (Steps 0–7,
Result: PRD + changeset paths) and **Red** (Steps 8–10, Result: `<n> failing @ <sha>`). Halts,
beyond the skill's: a broken build or baseline (Step 7), an acceptance test that cannot be written
cleanly against the current shape (Step 8), nothing red after Steps 8–9.

Writing the rows, it nests the plan-derived TODOs under the row that does them: milestones, Scope
deliverables and acceptance-test checkoffs under Green; under Wrap the wrap obligations (always
`Verification executed — result recorded`) plus the optional `/pr-wrap` steps this change needs
(`/pr-wrap` § *Workflow row*, *Row TODOs*), which `/pr-wrap` may extend if scope grows.

**Row TODOs** — seeded under each row when it starts; a re-run resumes at the first open one:

- Plan: `Record initial discovery` · `Cross-check <package-dir>/docs/todo/ and <package-dir>/docs/code-issues/` ·
  `Create/update PRD documentation` · `Create changeset` · `Build and baseline healthy (Step 7)`
- Red: `Acceptance tests written and failing for the right reason` · `Unit/integration tests written
  and failing` · `Tests committed with the changeset`

## Execution Flow

### Step 0: Classify the change — the kind decides the preset

Ask one question about the diff this change will produce: **what does it do to observable
behaviour?** The answer is the changeset's `**Behaviour**` field and it decides the whole shape of
the plan (`pr-lifecycle/references/changeset.md` §1; full taxonomy and boundary cases in the `pr-stack` skill §
*Node kinds*, which applies to standalone changes too).

Route on the **`(Type, Behaviour)` pair**, never on `Type` alone — `Type: Migration` is two
different kinds and they land in different rows. The pair picks the `## Workflow` preset
(the `pr-lifecycle` skill § *Presets*), and the preset's row 1 names the planning command that owns it:

| Behaviour | `Type` | Preset | This command | Where it belongs |
|---|---|---|---|---|
| **adds** | Feature | feature | **yes — this is the path** | Steps 1–9 below, unchanged |
| **changes** | Bug Fix | bugfix | **yes, with two adjustments** | PRD only when the change is user-visible; Step 8's failing test is a **reproduction** test — red *for the defect*, per `/reproduce` — not an acceptance test for a missing feature |
| **changes** | Migration · deprecation · removal (a **contract change**) | feature | **yes, and it is not a reproduction** | Nothing is wrong today, so there is no defect to reproduce. Step 8 writes tests for the **new** contract, and `/plan-tdd-migration`'s preservation-test technique covers the parts of the old contract that survive. Do **not** hand the whole change to `/plan-tdd-migration`: that command requires features to remain unchanged |
| **changes** or **adds** | Architecture Change | feature | **yes** | `Type` is a scope label here, not a workflow — take the `adds` or `changes` row above according to what the diff does to observable behaviour |
| **preserves** | Architecture Change | restructure or migration | no | `Type` is a scope label here too. A move `code-restructuring` can express as intents → the restructure row below; anything else → the mechanical-migration row (`/plan-tdd-migration`, preservation tests against a baseline) |
| **preserves** | Refactor · restructure | restructure | no | `/code-restructuring` — a `Type: Refactor` changeset, a `plan.jsonl`, a recorded baseline, no PRD and no acceptance tests |
| **preserves** | mechanical Migration | migration | no | `/plan-tdd-migration` — behaviour-preservation tests against a recorded baseline |
| **preserves** | Test Rebalance | rebalance | no | `/plan-test-rebalance` — lower-tier tests proven equivalent *before* anything above them is deleted. Its Red row is this command's Step 8–9, run against the rebalance changeset |
| **preserves** | Infra · toolchain · configuration | infra | no | `/plan-ft-dev` for the changeset (no PRD), with `## Verification` at **V3** — the deterministic command and its recorded before-output. There is no red phase to run: nothing observable changes, so the recorded command *is* the guardrail |

**This table is a recommendation, and the developer overrules it.** If they want a
behaviour-preserving change planned here anyway, or a feature planned without a PRD, say in one line
what the routing would have given them and what their choice costs mechanically — a restructure
planned here has no `plan.jsonl`, so there is nothing for `restructure` to apply — then **do what
they decide** and record it in `## Decisions & Trade-offs`. A reaffirmed request is a decision, not
a disagreement to re-litigate. The same applies when the change fits no row: resolve it with the
behaviour question, and if it still does not resolve, propose a workflow and ask. What is not a
preference is `## Verification` — the workflow decides *how* the change is proven, never *whether*.

**Route before planning, not after.** A behaviour-preserving change run through this command gets a
product-requirements document for a move nobody will observe and acceptance tests that accept
nothing; the cost is paid in Step 8, when there is no new behaviour to write a test against. If the
change has **two** families in it — a refactor that also fixes a bug — that is two changesets and two
commits, because the moment a preserving diff alters an output its baseline stops being a guardrail.

**Then state how the change will be proven.** Every changeset carries a `## Verification` section
(`pr-lifecycle/references/changeset.md` §9.5) naming the highest rung it can reach — V1 an executable test that fails
before and passes after, V2 a recorded baseline that must still hold, V3 a deterministic command
with its before-output recorded, V4 a scripted manual procedure with the developer's recorded
consent. For the feature path that is the acceptance tests of Step 8, and writing the section is a
one-liner pointing at them. It is still written: a code change with no stated proof is not an
acceptable PR outcome, and the section is what says which rung was reached and what blocked a
higher one.

### Planning Phase (Steps 1–6)

Follow the planning phase from `.agents/skills/planning/references/planning-phase.md` — Steps 1
through 6 (interview → code analysis → **deferred-work cross-check** → product area → PRD →
changeset → worktree setup and handoff).

**Step 2b is not optional.** After the code analysis, load the `deferred-work` skill
(`.agents/skills/deferred-work/SKILL.md`) and scan the records for items sitting in this change's
path:

- `<package-dir>/docs/todo/` — work earlier changesets deferred;
- `<package-dir>/docs/code-issues/` — analyzer findings, for every package in scope;
- `<package-dir>/docs/deferred-answers/` and `docs/<area>/deferred-answers/` — `#yolo` decisions
  not yet reviewed. Each one in the path goes in `## Prerequisites` → `### Open Deferred Answers`,
  and one this change would build further on is asked in the interview (`planning-cross-check.md`,
  scan 4).

Classify each — ⛔ blocking / ⚠ during / ℹ answered / — unrelated — and put everything blocking or
constraining in the changeset's `## Prerequisites`. A **blocking** item also earns a TODO under the
row that clears it, because it is work rather than a note. Discovering it during `/green` is late: the choice
by then is to work around it, silently make it worse, or stop.

Right-size each fix: small and inside this change's own files → do it here. Small but in shared code
→ a prerequisite PR that lands first. Large, or the code issue says `Restructure: required` → its own
`Type: Refactor` restructure changeset, named in `## Prerequisites` → **Restructure Prerequisite** and
executed by `/green` **before** any implementation. Never absorb a large restructure into this
changeset's implementation.

Name the in-scope packages that have **no** `<package-dir>/docs/code-issues/` directory — that means nobody
has run `/analyze-code-issues` on them, not that they are clean. Run it when this change lands in
code the analyzers would have something to say about.

**Check the suites the tests will land in.** For each existing test file Steps 8–9 will add to, look
for an open `<package-dir>/docs/code-issues/non-fluent-tests-<file-slug>.md`, or score it quickly against
the rubric in `.agents/skills/testing/references/fluent-style.md`. The new tests are fluent either
way; what a non-fluent suite earns is a **migration proposal**, below — and an **oversized** one
(≥ 500 lines, `**Priority:** 1`) earns the first proposal, recommended *do it*, ahead of every other
softening candidate.

**Then look beyond the records — suggest softening the ground.** The scan finds debt somebody wrote
down; your own reading of the code in Step 2 is the other source. Where the structure as it stands
would make *this* change harder or riskier — a function no test can reach, a collaborator constructed
inline, an obvious seam about to gain a fourth responsibility — propose a preparatory
`/code-restructuring` pass. The strongest signal comes one step later: **if Step 8 cannot write a
clean acceptance test against the current shape**, that is the finding, and it is worth returning
here rather than writing a test through two layers of doubles.

**Suggest; do not decide.** A preparatory restructure spends the developer's review budget before the
feature has earned any. Present the difficulty it removes, the operations, the measured blast radius
(`findReferences` caller count), the cost, and what skipping it costs — then ask. The bar is a named
difficulty in *this* changeset; "the code would be nicer" is not one, and a restructure larger than
the change it enables has stopped being preparation. Full guidance, including the presentation
format: `.agents/skills/deferred-work/references/planning-cross-check.md` § *Softening the ground*.

Approved, it becomes a **Restructure Prerequisite** in `## Prerequisites` with
`**Source:** planner judgment`. Declined, file the observation — a code issue if it is measurable,
otherwise a `Future enhancement` TODO — and note the decision in `## Decisions & Trade-offs` so a
reviewer reading a contorted seam can see it was a choice.

**A non-fluent suite the new tests land in is a softening candidate too** — with one difference:
its migration is never a Restructure Prerequisite, because it must not hold up this change's green.
Approved, it is **its own PR placed below this one** (this change becomes a two-node stack —
`/plan-pr-stack`'s ground-softening node), greened in parallel; this changeset's tests are written
fluent against the suite as it is today. Declined, the suite's `non-fluent-tests` record (filed by `/pr-wrap` if
not yet open) is what remains — and the stack's sweep, or the next planner, takes it. Shape and proof:
`fluent-style.md` § *Migrating a suite*.

Tick the Plan row's first TODOs (`Record initial discovery`, `Cross-check <package-dir>/docs/todo/
and <package-dir>/docs/code-issues/`, `Create/update PRD documentation`, and `Create changeset`).

The changeset is started per the `pr-lifecycle` skill § *Start a changeset*
(`.agents/skills/pr-lifecycle/SKILL.md`), with the preset Step 0 picked and **Plan** ⏳. Record a
developer override of the routing (above) as the preset choice, not only in `## Decisions & Trade-offs`.

### Step 7: Verify Build and Baseline — MANDATORY

Before writing any tests, verify the environment is healthy for the affected packages.

**7a. Build each affected package:**

```bash
uv run mypy
```

**7b. Run the existing test suite for each affected package:**

```bash
uv run pytest -q
```

**If the build fails — STOP. Write no tests.** Halt **Plan** ⛔ with the failing package and
command in **Result**; the summary's **⛔ Needs you** block carries:

```
⛔ BUILD FAILURE — no tests written.

Package: @/<package-name>
Command: uv run mypy
Error: <paste error summary>

Run this command to investigate:
  uv run mypy

Options: a) fix the build, then re-invoke /plan-red  b) re-invoke with the failure declared
pre-existing and out of scope (recorded in Result)
```

Record any pre-existing test failures — these are not caused by this changeset and must be listed separately so they aren't confused with new failures during `/green`.

With the build and baseline healthy, close **Plan** ✅ (PRD + changeset paths) and mark **Red** ⏳.

### Step 8: Create Failing Acceptance Tests

**If a test cannot be written cleanly against the current structure, stop writing tests.**
A mock of a mock, a private method reached through a cast, or a whole service constructed to exercise
one branch is not a test-writing problem — it is the ground-softening signal, and it is cheapest to
act on now. `/green` would otherwise rewrite the test, and a red phase built on a contorted seam
specifies the contortion. Halt the **Red** row ⛔ with the Step 2b proposal (difficulty, operations,
blast radius, cost) in the summary and the options *a) queue a Restructure Prerequisite* ·
*b) write the test against the current shape* · *c) re-plan*. The developer's answer on
re-invocation is recorded in **Result** before any test is written.

For each acceptance test defined in changeset:
1. Write test that captures desired behavior — **fluent**, per the `fluent-tests` skill (load it
   before the first test), even when the suite it joins is not
2. **CRITICAL**: Fully implement test — not a placeholder
3. Test should fail due to missing functionality
4. Verify test fails for the right reason

Record for the summary's **Decided without review** — this replaces the former acceptance-test
review, so it is never skipped:
- List of all test titles created
- File paths with line numbers
- What each test validates
- Confirmation all tests are FAILING

### Step 9: Red Phase — Write Failing Unit/Integration Tests

Use `/red` approach for smaller-scope tests:
1. Write comprehensive failing tests covering:
   - Main functionality
   - Edge cases
   - Error scenarios
   - API boundaries
2. Fully implement tests (not skeletons)
3. Define public API through test usage
4. Verify all tests fail for right reasons (missing implementation, not bugs)
5. Every test written or edited is fluent and scores ≥ 8
   (`.agents/skills/testing/references/fluent-style.md`); the suite's other tests are not touched

```bash
cd packages/package-name
uv run pytest -q
```

### Step 10: Commit, close the row, summarise

If nothing is red, halt **Red** ⛔ — a red phase with no failing test has proven nothing. Otherwise
commit the tests with the changeset and close **Red** ✅. The summary's **Done** and **Decided
without review** blocks carry:
- PRD location
- Changeset location
- Initial discovery location (`docs/<area>/1-WIP/{slug}-initial-discovery.md`)
- **Prerequisites** — every `<package-dir>/docs/todo/` and `<package-dir>/docs/code-issues/` item with its verdict, and
  whether a **restructure prerequisite** is queued for `/green` to run first (with its changeset
  path). State plainly if the scan found nothing relevant
- All acceptance test titles + file paths
- All unit/integration test titles + file paths
- Confirmation all tests are failing correctly

## Out-of-Scope Ideas

During planning and code analysis, ideas that are relevant but outside this changeset's scope go into
**a new file** in `<package-dir>/docs/todo/` — `YYYY-MM-DD-<slug>.md`, `**Category:** Future enhancement`,
`**Source:**` this changeset. Never add a second item to an existing file — that is the shared
append-point the layout removes. Updating an item's own file is a different thing, and is required.

`<package-dir>/docs/todo/` is read as well as written — Step 2b scans it for items this change runs into. The
two directions are complementary: what you defer today is what somebody's Step 2b finds tomorrow, so
write entries that state **why** the work was deferred, not only what is left. That reason is what
tells the next planner whether it blocks them.

**A future enhancement is not the same as deferred scope.** Something the changeset never planned
needs no consent. Cutting something it *did* plan needs a named blocker, refuted alternatives and the
developer's word — asked for by halting the row ⛔, and recorded from their answer on re-invocation
(the `pr-lifecycle` skill § *Halts*; the `deferred-work` skill).

## Rules

- **Classify the change before planning it (Step 0)**; two families in one change is two changesets
- **Every changeset states its `Type` and `Behaviour`, and carries `## Verification`** — the method,
  the command a reviewer re-runs, the before-state and the expected after-state. V4 (a manual
  procedure) needs the developer's recorded consent; a change with no stated proof is not planned
- **A bug fix's red test reproduces the defect**, not a missing symbol — see `/reproduce`. A PRD is
  written only when the change is user-visible
- **Step 2b before the changeset**, recording every relevant item in `## Prerequisites` with a
  verdict, including the ones you decide not to fix
- **A restructure prerequisite is planned here and executed before green** — its own
  `Type: Refactor` changeset, its own commit, and it implements nothing
- **Suggest a ground-softening restructure, never impose one**
- **Build must pass before writing any tests**
- Each step is discrete and actionable
- Take extra time on testing strategy — don't rush
- Tests must be fully implemented, not placeholders
- No conditional logic in tests
- No try/catch blocks or fallbacks
- **Every test is fluent** (`fluent-tests` skill), even in a suite that is not — a non-fluent suite
  earns a migration proposal (its own PR, never blocking this one), not a copied style
- Never put "red phase" or "green phase" in code comments or test descriptions
- Quality first — never compromise code quality

**References**: `.agents/skills/pr-lifecycle/references/initial-discovery.md`,
`.agents/skills/pr-lifecycle/references/changeset.md` §2.5
