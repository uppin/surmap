---
description: Changeset document structure and requirements for tracking development changes
---

# Changeset Documentation

## Purpose

Changeset documents track **delta changes** (State A → State B) to development documentation across one or more packages. They are **living documents** during implementation and get wrapped into stable dev docs when complete.

**Key Concept**:
- **Development Documentation** = Read-only stable reference
- **Changeset Document** = Write-during-development delta tracker

## Changeset vs Development Docs

| Aspect | Development Docs | Changeset Docs |
|--------|------------------|----------------|
| **Location** | `{common,common-testing,mapping-pipeline,onboard-detection,surmap,packages}/*/README.md`, `packages/{package}/docs/` | `docs/<area>/1-WIP/YYYY-MM-DD-name.md` |
| **State** | Read-only (State B only) | Writable (tracks A → B transition) |
| **Purpose** | Stable technical reference | Track changes during development |
| **Lifecycle** | Permanent, updated via wrapping | Temporary, deleted after wrapping |
| **Content** | Current implementation state | Delta, milestones, acceptance tests |

## Document Structure

### Required Sections

#### 1. Header Metadata

```markdown
# Changeset: {Feature/Change Name}

**Date**: YYYY-MM-DD
**Status**: 🚧 In Progress | ✅ Complete
**Type**: Feature | Bug Fix | Refactor | Migration | Infra | Test Rebalance | Test Style | Architecture Change
**Behaviour**: adds | changes | preserves
**Complexity**: 1–5 — <the signals that set it, in one line>
```

**Status progression**:
- `🚧 In Progress` - Active development
- `✅ Complete` - Ready for wrapping

**`Type` is the kind of change, and it decides the shape of the plan** — whether a PRD is warranted,
which template this document follows, what the first commit contains, and which command implements
it. Settle it **before** writing the rest of the document; a migration planned as a feature gets a
product-requirements document for a move nobody will observe, and a bug fix planned as a feature gets
acceptance tests instead of a reproduction.

**`Type` alone does not identify the kind — the `(Type, Behaviour)` pair does**, and every
dispatch reads the pair. `Type: Migration` covers both a contract change and a mechanical move, and
those two get opposite red steps; `Behaviour` is what separates them. Never route on `Type` alone:

| `Type` | `Behaviour` | The kind that dispatches |
|---|---|---|
| Feature | adds | Feature |
| Bug Fix | changes | Bug fix |
| Migration | **changes** | **Contract change** — new-contract tests + preservation tests for what survives |
| Migration | **preserves** | **Mechanical migration** — baseline + preservation tests |
| Refactor | preserves | Refactor / restructure |
| Infra | preserves | Infra / toolchain |
| Test Rebalance | preserves | Test rebalance |
| Test Style | preserves | Test-style migration — suites rewritten to fluent (`testing/references/fluent-style.md`) |
| Architecture Change | adds · changes · preserves | route on `Behaviour`; the `Type` is a scope label, not a workflow. **adds / changes** → Feature or Contract change. **preserves** → Refactor / restructure when the move is expressible as `code-restructuring` intents, else Mechanical migration (baseline + preservation tests) |

**`Behaviour` is the family `Type` belongs to**, and it is the field that actually governs:

| `Behaviour` | `Type` | PRD | This document | Proof, by default |
|---|---|---|---|---|
| **adds** | Feature | required | this template | failing acceptance tests |
| **changes** | Bug Fix · Migration (contract change) · Architecture Change | only when user-visible | this template | a reproduction test for a **defect**; for an intentional contract change, tests asserting the **new** contract plus preservation tests for the parts that survive — there is no defect to reproduce |
| **preserves** | Refactor · mechanical Migration · Infra · Test Rebalance · Test Style · Architecture Change | none | `Refactor` uses `pr-lifecycle/references/restructure.md`; the rest use this template | a recorded baseline that must still hold |

A change whose two halves land in different rows is **two changesets** — the moment a
behaviour-preserving diff alters an output, its baseline stops being a guardrail and becomes
something that has to be edited, which leaves nothing proving the move was safe. Full taxonomy,
including the boundary cases (a migration whose target API's semantics differ, a dependency upgrade,
performance work): the `pr-stack` skill § *Node kinds*, which is the same model whether or not the
change is part of a stack.

**`Complexity` is required on every changeset — stacked or standalone, whichever command planned it.**
It is a planning output, written for whoever sizes the implementer: an orchestrator, a subagent
launcher such as `/yolo-pr-stack`, or the developer choosing a model and effort for `/green`,
`/pr-wrap` or `/code-restructuring` by hand all read this one line instead of re-deriving the size of
the change from the diff. Score it when the changeset is written and re-score it in
the same commit as the red step if the failing tests showed the node is bigger or smaller than
planned. Take the **highest** score any row reaches, not an average:

| Score | The node, as planned |
|---|---|
| **1** | ≤ 3 owned symbols, one package, unit-level tests, no Restructure Prerequisite, no inherited restructure |
| **2** | One package, a handful of owned symbols, still unit-level or in-memory tests |
| **3** | One package with integration tests, or an adapter / I/O seam, or a Restructure Prerequisite inside the package |
| **4** | More than one package, **or** concurrency / ordering semantics, **or** a data migration, **or** a proto / contract change, **or** an inherited restructure to repair |
| **5** | Several of the row-4 signals at once, or a design the changeset itself records as unsettled |

The line names the signals (`3 — one package, integration tests, S3 adapter seam`), never just the
number: a score nobody can audit is a guess. It sizes the *implementer*; it does not change what the
node must prove. A score of 5 is a warning that the boundary may be wrong — say so in
`## Decisions & Trade-offs`.

**The changeset itself is never optional, for any `Type`.** It is what carries the background, State
A, State B and the verification method to whoever picks the work up without this conversation's
context. Only the PRD varies.

#### 1.5. Workflow

**Required, for every `Type`.** One `- [wf <n>]` line per step: its status, the command that runs
it, the step and one line of evidence. Commands never route to a successor and never parse a
section: they grep the rows, run their own and close it, and the next row says what comes next.
The line format, the grep one-liners, the presets per `(Type, Behaviour)`, the step contract and the
halt rules live in [the `pr-lifecycle` skill](../../pr-lifecycle/SKILL.md).

```markdown
## Workflow

- [wf 1] ✅ YYYY-MM-DD `/plan-red` Plan — PRD, changeset, initial discovery · PRD + this file
- [wf 2] ⬜ `/plan-red` Red — acceptance and failing lower-tier tests, committed ·
- [wf 3] ⬜ `/green` Green — implement until every red test passes ·
  - [ ] Milestone 1: Parser handles chunked sessions
  - [ ] Acceptance: `feature.e2e.test.ts` passes
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded
  - [ ] `docs/mapping-pipeline/mapping-pipeline-editor/feature.md` — update API table with new endpoint
  - [ ] Validate tests (`/validate-tests`)
  - [ ] (optional) Production readiness validated (3) — run if the diff reaches server code
- …
```

**Guidelines**:
- **Every checkbox in a changeset is a TODO nested under the row that does it** (`  - [ ] …` /
  `  - [x] …`, two spaces, open or done only); no other section carries one. The planner writes the
  plan-derived TODOs — Scope deliverables, milestones (§9) and acceptance-test checkoffs (§11) under
  Green (or the kind's implementing row), the wrap obligations (§17) under Wrap **plus** the optional
  `/pr-wrap` steps this change needs (`/pr-wrap` § *Workflow row*, *Row TODOs*; a small UI fix plans
  none, a production-code feature plans them; `(optional) … — run if <condition>` leaves the call to
  `/pr-wrap`, which ticks a skip `— skipped: <reason>` and may add steps if scope grows) — and a command seeds
  its own *Row TODOs* under its row when the row starts. A re-run resumes at the row's first open TODO
- The planning command writes the rows from the preset and adjusts them to the change. A row that
  cannot apply is ➖ with the reason, never dropped silently
- Keep them under `## Workflow`, directly after the header metadata, for people reading the file
- The developer may edit the rows at any time; commands follow them as written

#### 2. Initial Discovery

**Required.** First content section after `## Workflow`. Points at the companion Explore / Discovery
file in the same WIP directory. Full template and capture rules:
`.agents/skills/pr-lifecycle/references/initial-discovery.md`.

```markdown
## Initial Discovery

Full codebase exploration that grounded this plan: [initial-discovery.md](./YYYY-MM-DD-feature-name-initial-discovery.md).

State A below is distilled from that file. Do not duplicate grep traces or file dumps here.
```

**Purpose**:
- Make the planning exploration recoverable for later sessions without re-running the search
- Keep the changeset itself a delta document (State A / State B), not a tool-trace dump

**Guidelines**:
- The companion file is `docs/<area>/1-WIP/{changeset-slug}-initial-discovery.md`
- It must exist **before** this changeset is written (planning-phase Step 2)
- Combined conclusions live at the top of that file; each Explore pass is a separate section at the tail
- `/wrap-context-docs` deletes the companion with this changeset — do not merge it into package docs

#### 2.5. Prerequisites — Deferred TODOs, Code Issues, Open Deferred Answers, and Restructures

**Required when planning-phase Step 2b found anything relevant; omitted entirely when it did not.**
An empty heading is noise. Placed directly after Initial Discovery, because it governs what happens
*before* the rest of the changeset can be executed.

Canonical rules, formats and verdict definitions: the
[`deferred-work` skill](../../deferred-work/SKILL.md).

```markdown
## Prerequisites

### Deferred TODOs

Paths are repo-relative — a record lives in the docs of the package it describes.


| Item | Verdict | Disposition | Outcome |
|---|---|---|---|
| `mapping-pipeline/mapping-pipeline-server/docs/todo/2026-08-14-analyzer-fallback-deferred.md` | ⛔ Blocking | The fallback this changeset must remove is the one that item records. Fixed here — see Scope | *(filled by `/green`)* |
| `mapping-pipeline/mapping-pipeline-server/docs/todo/2026-07-02-subasset-revision-guard.md` | ⚠ During | This change writes `pageNumber` on the same path. Must not widen the lost-update window; the write stays inside the existing revision check | *(filled by `/green`)* |
| `mapping-pipeline/mapping-pipeline-api/docs/todo/2026-06-30-proto-republish.md` | ℹ Answered | The ambassador types shipped on 2026-08-01; the boundary cast this item asks about can go | *(filled by `/green`)* |

### Code Issues

| Issue | Verdict | Disposition | Outcome |
|---|---|---|---|
| `mapping-pipeline/mapping-pipeline-server/docs/code-issues/oversized-file-session-replay-service.md` | ⛔ Blocking | 940 lines, and this changeset's implementation lands inside it. Restructure prerequisite below | *(filled by `/green`)* |
| `mapping-pipeline/mapping-pipeline-server/docs/code-issues/missing-tests-subasset-processing-service.md` | ⚠ During | `splitSubassets` is entered by no tier. This changeset's acceptance tests cover it — see Testing Plan | *(filled by `/green`)* |
| `mapping-pipeline/mapping-pipeline-server/docs/code-issues/crap-asset-mapper.md` | — Unrelated | Same package, different call path. Recorded as considered; not fixed here | *(filled by `/green`)* |

*(Scanned `mapping-pipeline/mapping-pipeline-server/docs/code-issues/` and `mapping-pipeline/mapping-pipeline-common/docs/code-issues/`.
`surmap` has no `<package-dir>/docs/code-issues/` — nobody has analyzed it, which is not the same as clean.)*

### Open Deferred Answers

Earlier `#yolo` decisions in this change's path that the developer has not reviewed yet
(`deferred-work` skill, `references/deferred-answer-record.md`).

| Record | Verdict | Disposition | Outcome |
|---|---|---|---|
| `src/surmap/surmap-server/docs/deferred-answers/2026-10-20-caption-store.md` | ⛔ Blocking | This change adds caption search on top of the sidecar store that record picked. Asked in this plan's interview: the developer confirmed it | *(filled by `/green`: confirmed → record deleted)* |

### Restructure Prerequisite — executed BEFORE green

- `/code-restructuring` against `mapping-pipeline/mapping-pipeline-server` — tracked as the Green row's first
  TODO (`  - [ ] Restructure Prerequisite executed — fill-flow split`)
  - **Source**: `mapping-pipeline/mapping-pipeline-server/docs/code-issues/oversized-file-session-replay-service.md`
    *(or `planner judgment — <the difficulty in this changeset it removes>`, approved by the
    developer at planning — see `planning-cross-check.md` § Softening the ground)*
  - **Code issues closed**: `mapping-pipeline/mapping-pipeline-server/docs/code-issues/oversized-file-session-replay-service.md`
  - **Restructure changeset**: `docs/<area>/1-WIP/YYYY-MM-DD-fill-flow-split.md` (`Type: Refactor`, no
    PRD) — the path `/code-restructuring` writes at its step 4, reserved here. Planning names it; it
    does not write it
  - **Why before green**: this changeset implements inside `fillSessionFlow`; splitting it afterwards
    would re-touch every line the feature added and make the diff unreviewable
  - **Baseline carve-out**: green everywhere except this changeset's own planned red tests, listed
    by name in the restructure changeset's `## Baseline` as known-red
  - **Commit**: its own commit, landing before any implementation commit
```

**Purpose**: make the debt this change runs into visible at planning time, when the answer can still
be *sequence the work differently* — rather than at `/green`, where the only options left are to work
around it, silently make it worse, or stop.

**The section has two halves and two authors.** `Verdict` and `Disposition` are **planning** output:
what the item is and what this changeset intends to do about it. `Outcome` is **`/green`** output
(step 3.5a): what it actually did, with the commit or `file:line` where the work landed.

That column is not bookkeeping. **This changeset is deleted at wrap**, so the Outcome column is the
only place the mapping from *this change* to *that record* is ever written — and it is what
`/pr-wrap` gates on and what `/wrap-context-docs` reads to decide which records to close, which to
update, and which to leave. An Outcome cell still blank at wrap is indistinguishable from work
nobody did, and wrap treats it that way.

Outcome vocabulary, one of four per row:

| Outcome | Means | What happens to the record |
|---|---|---|
| ✅ **Resolved** | the item is fully dealt with | **deleted** (`git rm`) in the fixing commit; git keeps the history |
| ◐ **Partly** | measurably better, not closed | record **stays open**, updated with the new numbers and a narrowed remainder |
| ➖ **Unchanged** | a ⚠ during / — unrelated verdict honoured; nothing to change | record untouched |
| ⛔ **Deferred** | intended here, not delivered | a new TODO file, with a named blocker and recorded consent |

**Guidelines**:
- **Reference a record by its path in backticks, never a Markdown link.** Both trees are versioned
  together, so a link would resolve — but a code issue is *renamed* when the symbol it names moves,
  and a resolved record is deleted. A link rots silently through either;
  a backticked repo-relative path reads as the identifier it is.
- A ⛔ **Blocking** item also earns a line in `## Scope`. It is work, not a note.
- Record — **Unrelated** verdicts sparingly, only where a reader would otherwise assume the item was
  missed. Do not pad the table.
- Say which `<package-dir>/docs/code-issues/` directories you scanned, and name the in-scope packages that have
  none. Absence means nobody ran `/analyze-code-issues`, not that the package is clean.
- **`/green` fills every Outcome cell; `/pr-wrap` refuses to wrap while one is blank.** A ◐ Partly is
  a legitimate outcome and often the honest one — a partial fix whose record is deleted as ✅ Resolved is
  worse than no fix recorded at all, because the next planner's Step 2b skips the item.
- The **Restructure Prerequisite** block is executable: `/green` step 0.5 runs it before writing any
  implementation, and it implements nothing itself. Every field above is required — the changeset
  path, the reason it must come first, the baseline carve-out, and that it is its own commit.
- **`Source` says where the restructure came from.** A code-issue path means a tool measured it.
  `planner judgment` means the planner proposed it to soften the ground for *this* change and the
  developer approved — record the named difficulty it removes, because that is the only thing
  justifying a behaviour-preserving diff landing ahead of the feature. A restructure with neither
  has not been agreed and does not belong in this section.
- **Planning reserves the restructure changeset's path; it does not write the document.** That is
  `/code-restructuring` step 4, which needs the seam analysis to exist first. Naming the path here is
  what lets `/green` find the work without re-deriving it.
- In a **PR stack**, a restructure that spans more than one node is not this section's business —
  it becomes its own node or a prerequisite PR, and each affected node instead carries
  `## Inherited Restructure — expect rewrite`. See the `pr-stack` and `deferred-work` skills.

#### 3. Affected Packages

**CRITICAL**: List ALL packages with documentation changes.

```markdown
## Affected Packages

**CRITICAL**: List ALL packages with documentation changes:

- **surmap**: [README.md](../../{common,common-testing,mapping-pipeline,onboard-detection,surmap,packages}/package-1/README.md) - Description of changes
  - [architecture.md](./package-1/architecture.md) - Specific changes
  - [api-reference.md](./package-1/api-reference.md) - API updates
- **surmap**: [README.md](../../{common,common-testing,mapping-pipeline,onboard-detection,surmap,packages}/package-2/README.md) - Description of changes
  - [integration.md](./package-2/integration.md) - Integration changes
```

**Purpose**:
- Identifies which package documentation will be updated
- Provides links to READMEs and detailed docs that will change
- Used by `/wrap-context-docs` to know what to update

#### 4. Related Feature Documentation

**Optional but recommended**: Link to feature documents or PRDs that drive these technical changes.

```markdown
## Related Feature Documentation

References to feature docs (if applicable):
- [Feature Document](../ft/{product-area}/feature-name.md)
- [PRD Document](../ft/{product-area}/1-WIP/PRD-YYYY-MM-DD-*.md)
```

**Purpose**: Bidirectional linking between user requirements and technical implementation.

**`## Stash Tracker`** (after it) — required when the change was planned from a Roadmap tracker page
(`/roadmap-red`, or a `/plan-pr-stack` node whose input was a Roadmap URL). It is the page's whole
policy for this PR: URL and item, when it was read, whether the agent may publish (*editable*) or
must advise the developer (*manual*), what each publish writes, the review threads and their
disposition, and the page's claims checked against the code. Template and rules: the
`roadmap-driven-development` skill § *Write the changeset's `## Stash Tracker`*. The publishes
themselves are TODOs under the rows that make them; no step decides one on its own.

#### 5. Summary

```markdown
## Summary

Brief description of what is changing in the technical implementation.
```

**Guidelines**:
- 2-3 sentences
- High-level overview
- Focus on WHAT is changing, not WHY

#### 6. Background

```markdown
## Background

Why these technical changes are needed.
```

**Guidelines**:
- Explain motivation and context
- Reference architectural decisions
- Explain technical debt or limitations being addressed

#### 7. Scope

**CRITICAL**: High-level deliverables of the change — what it delivers, not where it stands.

```markdown
## Scope

- **Package Documentation**: Update package READMEs and dev docs
- **Implementation**: Complete code changes across affected packages
- **Testing**: All acceptance tests passing
- **Integration**: Cross-package integration verified
- **Technical Debt**: Production readiness gaps addressed
- **Code Quality**: Linting, type checking, and code review complete
```

**Purpose**:
- Names the deliverables; their progress is the TODOs the planner nests under the row that
  delivers each (§1.5) — implementation under Green, documentation under Wrap — never a checkbox here
- Validated by `$code-cleaning wrap the context docs` before wrapping

**Update Responsibility**: See `.agents/commands/update-context-docs.md` for the scope update responsibility matrix.

#### 8. Technical Changes

```markdown
## Technical Changes

### State A (Current)

Describe current implementation state:
- Current architecture
- Current APIs
- Current behaviors

### State B (Target)

Describe target implementation state:
- New architecture
- New APIs
- New behaviors

### Delta (What's Changing)

Specific changes per package:

#### surmap
- **Architecture**: Change description
- **API**: New endpoints/functions
- **Implementation**: Core algorithm changes

#### surmap
- **Integration**: How integration changes
- **Dependencies**: New dependencies
```

**Purpose**:
- **State A**: Document current implementation (before changes)
- **State B**: Document target implementation (after changes)
- **Delta**: Package-specific technical changes

**Guidelines**:
- State A and State B should be clear and specific
- Delta should map to affected packages
- Focus on technical details, not process

**Architecture diagram updates — when the delta changes what a diagram depicts.** A declared
architecture diagram (found per `planning-phase.md` Step 2 — package `README.md` first, then the
group-level `{group}/AGENTS.md`) is a stable doc like any other, so it is never edited during
development: the changeset is what *indicates* the architecture is changing and *specifies* the
update. When State B alters the depicted architecture — a component added, removed, split or
re-homed, a connection or data flow changing — add:

```markdown
### Architecture Diagram

- **Diagram:** `src/surmap/README.md` — group-level component topology (mermaid)
- **Update:** `surmap-training` gains a directed edge from `surmap-server`
  (training jobs stream per-page facts); no other nodes or edges change
```

The block names the diagram's file and format **exactly as declared** (`mermaid` is the default
when the declaration names no format) and states what changes in the diagram — specific enough
that `/wrap-context-docs` can apply it without re-reading the rest of the changeset. The wrap
applies the update to the diagram file and writes the diagram in State B (the topology as it now
is), never as a delta. A diagram update also earns a Wrap-row TODO (§17) so it cannot be
forgotten between green and wrap. Omit the block when the delta changes nothing a diagram depicts —
not every changeset owes a diagram update.

#### 9. Implementation Milestones

Written as TODOs nested under the Green row (or the kind's implementing row), not as a section:

```markdown
- [wf 3] ⬜ `/green` Green — implement until every red test passes ·
  - [ ] Milestone 1: Description
  - [ ] Milestone 2: Description
```

**Purpose**: Break implementation into measurable milestones.

**Guidelines**:
- Milestones should be specific and verifiable
- Each milestone represents substantial progress
- Ticked `[x]` as completed during implementation, by the row's command or `/update-context-docs`

#### 9.5. Verification — how this change is proven

**Required in every changeset, for every `Type`.** A code change with no way to tell whether it
worked is not an acceptable PR outcome, and "the reviewer reads the diff" is how a method is
*checked*, not a method. This section names the proof; `## Testing Plan` and `## Acceptance Tests`
below are its usual instantiation, not a substitute for declaring it.

```markdown
## Verification

**Method:** V<n><, and for V1 the shape: fail→pass or characterisation> — <one line naming the proof>
**Command:** `<the exact command a reviewer re-runs>`
**Before:** <the recorded state before the change. A **failing** test for V1-fail→pass; for
V1-characterisation a **green** result plus what would have broken it; baseline counts for V2;
the command's output for V3>
**After:** <what the same command must produce for this change to be correct — for a
characterisation test that is *still green*, which is the whole claim>

<For V1-characterisation, say what the test would have caught, since "green → green" is not
self-evidently a guardrail. For V2, the evidence that the baseline covers the code that moves. For
V3, the recorded before-output in full. For V4, the numbered steps, the evidence captured, and the
consent line.>
```

**A green before-state is valid, and for a behaviour-preserving change it is the normal one.** Do
not write a failing test into `**Before:**` to satisfy the placeholder — a false red-before claim is
worse than an honest `green (would fail if <X> changed)`, because a reviewer who re-runs it finds
the section already untrue.

**The ladder — pick the highest rung this change can actually reach:**

| Rung | Method | Fits |
|---|---|---|
| **V1** | **An executable test, in one of the two shapes below** — an acceptance test (adds), a reproduction test (changes), a characterisation / preservation test written *before* the move (preserves) | the default for every `Type` |
| **V2** | **A recorded baseline that must still hold** — the existing suites, named and counted before the change and re-run after, **where they demonstrably cover the code that moves** | Refactor · mechanical Migration |
| **V3** | **A deterministic command whose before- and after-output are recorded here** — a build, a type-check, a generated-artifact diff, an analyzer or coverage count, a benchmark | Infra · toolchain · performance |
| **V4** | **A scripted manual procedure with recorded evidence** — numbered steps anyone can repeat, plus what was observed (log line, request id, dashboard panel, screenshot) | behaviour no harness in this repo can reach |
| **V5** | nothing | **never acceptable** |

**V1 has two shapes, and only one of them fails first:**

| Shape | The transition | Fits |
|---|---|---|
| **V1-fail→pass** | red before the change, green after | an acceptance test for new behaviour · a reproduction test for a defect · a new-contract test |
| **V1-characterisation** | green before, green after — its value is that it **would have failed** had the change altered behaviour | a preservation test before a migration · a baseline-gap test before a restructure · a replacement test in a rebalance |

**Say which shape it is, and never claim a transition the test cannot make.** A characterisation
test never fails, so describing it as "fails before, passes after" makes the section uncheckable.
And a characterisation test proves behaviour *survived* — it proves nothing about **coverage
equivalence**. A claim that one test covers what another covered is a measurement, so it needs the
**V3** command beside it (here: `cov-acc unique --tier <tier>`, before and after). A test rebalance
therefore carries both rungs: V1-characterisation for the replacements, V3 for the equivalence.

**Guidelines**:
- **Tests are the default, not the fallback.** Where a lower rung is chosen, name **what blocks the
  higher one**. "This code had no tests" is not a blocker — it is the reason to write one.
- **V2 is a claim about coverage, so prove the claim.** A baseline guards the change only if it
  executes the code that moves; name the suites and what they cover. A green baseline over an
  untested file is a coincidence, not a guardrail — so a V2 change that finds a gap writes the
  missing test (V1) for that gap **first**, before the move. That is the rhombus rule in
  [docs/architecture.md](../../../../docs/architecture.md): coverage goes down a tier
  before the code above it moves.
- **V4 needs the developer's recorded consent** — `**Approved:** <who>, <date>` in the section.
  Choosing an unautomated guardrail is a judgment call about what the repo is willing to carry, and
  that is the developer's to make. Present what blocks V1–V3 and ask.
- **One method per behaviour, not one per changeset.** A change that adds an endpoint and upgrades a
  toolchain records V1 for the endpoint and V3 for the toolchain; a single line covering both proves
  neither.
- **It must be executed, not only declared.** The Wrap row carries the TODO
  `Verification executed — result recorded`, and `/pr-wrap` reads the recorded result before the PR
  leaves draft. A `## Verification` nobody ran is V5 with extra words.
- Never delete the section because the tests below already say it. The tests say *what runs*; this
  says *what would have caught the change being wrong*, which is the question a reviewer of a
  behaviour-preserving diff has no other way to answer.

#### 10. Testing Plan

```markdown
## Testing Plan

### Testing Strategy

**Determine Appropriate Test Level:**

The appropriate test level depends on the changeset scope:

- **E2E tests** when: Building complete features, user workflows, full API flows
- **Integration tests** when: Changing component interactions, DAO methods, service integrations, package boundaries
- **Unit tests** when: Modifying individual functions, algorithms, isolated logic

**Primary Test Approach:**
[Describe the most appropriate test level for this changeset and why]

**Example 1** (Full Feature - Async Export):
- **Test Level**: E2E
- **Why**: Complete user-facing feature with API, async processing, and storage
- **Approach**: Trigger export via API → Poll with -eventually → Verify archive contents

**Example 2** (DAO Method - Batch Update):
- **Test Level**: Integration
- **Why**: Changes how data is written to database, not full feature
- **Approach**: Call DAO method → Verify database state → Check side effects

**Example 3** (Algorithm - Data Transformation):
- **Test Level**: Unit
- **Why**: Pure function with deterministic input/output
- **Approach**: Call function with test data → Verify output structure and correctness

### Testing Options Analysis

#### Option 1: [Primary Testing Approach]
**Test Level**: E2E | Integration | Unit (choose based on changeset scope)
**Description**: [Detailed description of the most appropriate testing approach for this changeset]

**Scope**: What this test covers
- [Describe what needs to be tested based on changeset scope]
- [For features: Full workflow from trigger to completion]
- [For components/DAOs: Integration with dependencies]
- [For functions: Input/output with edge cases]
- Success and error scenarios
- Edge cases and boundary conditions

**Assertions**:
- **Strong assertion 1**: Specific, deterministic verification (e.g., "Archive contains exactly 3 files: data.json, metadata.xml, summary.txt")
- **Strong assertion 2**: Content verification (e.g., "data.json contains valid JSON with expected schema")
- **Strong assertion 3**: State verification (e.g., "Database record status = 'COMPLETED'")

**Reliability Considerations**:
- Deterministic: Test produces same result every time
- No false positives: Passes only when feature truly works
- No false negatives: Fails only when feature truly broken
- Timeout handling: Appropriate `-eventually` timeout for async operations
- Cleanup: Proper test data cleanup to prevent interference

**Implementation Location**: `packages/{package-name}/tests/{test-name}.e2e.test.ts`

#### Option 2: [Alternative/Complementary Approach]
**Description**: [Alternative testing strategy or complementary integration test]

**Scope**: What additional coverage this provides
- Specific integration between Package A and Package B
- Performance characteristics verification
- Error handling and recovery

**Assertions**:
- **Strong assertion 1**: [Specific verification]
- **Strong assertion 2**: [Specific verification]

**Trade-offs**:
- **Pros**: [Benefits of this approach]
- **Cons**: [Limitations compared to Option 1]

#### Option 3: [Unit-Level Testing]
**Description**: [Granular unit testing for critical components]

**Scope**: Isolated component/function testing
- Core algorithm verification
- Edge case handling
- Input validation

**Assertions**:
- **Strong assertion 1**: [Specific verification]
- **Strong assertion 2**: [Specific verification]

**Note**: Unit tests complement but do NOT replace end-to-end acceptance tests.

### Testing Principles Applied

**✅ Appropriate Test Level:**
- Choose test level based on changeset scope (E2E for features, Integration for components/DAOs, Unit for functions)
- Test at the highest appropriate level that provides confidence without unnecessary complexity
- E2E: Entry point to final outcome including all integrations
- Integration: Component/service interaction with real dependencies
- Unit: Isolated function/logic with deterministic inputs

**✅ Strong Assertions:**
- Verify actual outcomes, not just status codes
- Check file/data contents, not just existence
- Validate data structure and correctness
- Use exact values where possible, avoid ranges/margins unless testing uncontrollable factors

**✅ Deterministic Tests:**
- Same input produces same output every time
- No flaky tests due to timing, randomness, or external factors
- Controlled test data and environment
- Proper async handling with `-eventually` for timing-dependent operations

**✅ Complete Scope Verification:**
- Verify the entire scope of the change, not just partial results
- E2E: From entry point to final outcome including side effects
- Integration: Component interaction and actual integration with dependencies
- Unit: Function behavior including all branches and edge cases
- Don't stop at "operation initiated" - verify actual completion and results

**❌ Anti-Patterns to Avoid:**
- Testing at wrong level (E2E for function changes, Unit for full features)
- Checking only status codes/return values without verifying actual effects
- Using wide tolerance ranges for deterministic operations
- Testing only the "happy path" without error scenarios
- Over-mocking in acceptance tests (mock only what's outside changeset scope)
- Weak assertions like "array has length > 0" instead of verifying specific contents
- Testing less than the full scope of the change

### Async Operation Testing

**For async operations (exports, processing jobs, webhooks):**

```python
// Example pattern for async operation testing
await eventually.expect({
  timeout: 30000, // Appropriate timeout for the operation
  interval: 1000, // Polling interval
}, async () => {
  // 1. Check operation completion
  const status = await getOperationStatus(operationId);
  expect(status).toBe('COMPLETED'); // Not 'IN_PROGRESS' or 'PENDING'

  // 2. Verify the actual outcome
  const result = await getOperationResult(operationId);
  expect(result).toBeDefined();

  // 3. Verify contents/data (not just existence)
  expect(result.files).toHaveLength(3);
  expect(result.files).toContainEqual(
    expect.objectContaining({
      name: 'data.json',
      size: expect.any(Number),
      contentType: 'application/json'
    })
  );

  // 4. Verify actual file contents
  const fileContent = await downloadFile(result.files[0].url);
  const parsedData = JSON.parse(fileContent);
  expect(parsedData.items).toHaveLength(expectedItemCount);
  expect(parsedData.metadata.version).toBe('2.0');
});
```

### Coverage Requirements

**Acceptance tests MUST cover (at appropriate test level):**
- **Happy path**: Successful flow with typical inputs/data
- **Error scenarios**: Expected error conditions and recovery
- **Edge cases**: Boundary conditions, empty data, maximum limits
- **Integration points**: Dependencies and boundaries within changeset scope
- **Actual effects verification**: Real outcomes, not just return values/status codes
- **Side effects**: State changes, database updates, file creation (if in scope)

### Test Data Strategy

**Controlled test data approach:**
- Use deterministic test data (no random values unless necessary)
- Create isolated test data per test (no shared mutable state)
- Clean up test data after test execution
- Use realistic data volumes for performance testing
```

**Purpose**: Plan comprehensive, rock-solid testing approach before implementation.

**Guidelines**:
- **Analyze thoroughly**: Take time to identify testing options and challenges
- **Prioritize end-to-end**: Primary acceptance tests should test the full workflow
- **Strong assertions**: Verify actual outcomes and contents, not just status
- **Deterministic**: Tests must be reliable and repeatable
- **Multiple options**: Document primary and alternative testing strategies
- **Trade-off analysis**: Explain pros/cons of different approaches
- **Created during planning**: Completed during the planning workflow before implementation begins
- **Referenced during implementation**: Used by planning and TDD-oriented workflows to create actual tests

#### 11. Acceptance Tests

```markdown
## Acceptance Tests

### surmap
- **E2E**: Full workflow test from X to Y with content verification (feature.e2e.test.ts)
- **Integration**: Package-1 to Package-2 integration with data validation (integration.it.test.ts)
- **Unit**: Core algorithm with deterministic assertions (core-logic.test.ts)

### surmap
- **E2E**: End-to-end user workflow covering all integration points (workflow.e2e.test.ts)
- **Integration**: External API integration with response verification (api-client.it.test.ts)
```

**Purpose**: Define specific test implementations that verify State B is achieved.

**Types**:
- **E2E tests**: Complete workflows from entry point to final outcome (for full features)
- **Integration tests**: Component/service interactions with real dependencies (for integrations/DAOs)
- **Unit tests**: Isolated function/logic testing (for algorithm/function changes)

**Guidelines**:
- **Choose test level based on changeset scope** - use Testing Plan analysis to determine
- **Group by affected package** with test type and file path
- **Descriptive test names** that explain what behavior/scenario is being tested
- **Reference Testing Plan** - tests should implement the strategies defined in Testing Plan section
- **Include file paths** for traceability (e.g., `batch-update.it.test.ts`)
- **Each test is also a TODO under the Green row** (or the kind's implementing row), ticked when it
  passes — by `@test-acceptance` as tests are implemented and verified

**Relationship to Testing Plan**:
- Testing Plan (Section 10): Determines APPROPRIATE test level and HOW to test (strategies, approaches, analysis)
- Acceptance Tests (Section 11): WHAT specific tests to implement at the determined level

#### 12. Technical Debt & Production Readiness

```markdown
## Technical Debt & Production Readiness

Track gaps and technical debt introduced:
- Performance optimization needed in X
- Error handling incomplete in Y
- Documentation update needed for Z
```

**Purpose**: Track production readiness gaps discovered during implementation.

**Guidelines**:
- Add items as discovered during development; each one to address is also a TODO under the row
  that addresses it, ticked when done
- Updated by `@prod-ready`
- **A TODO still open when the PR is wrapped is a deferral**, and a deferral of planned scope
  needs a `<package-dir>/docs/todo/` file with a named blocker, refuted alternatives and the developer's
  recorded consent. Link the file from the TODO. Leaving it open with no record is a
  silent scope cut — see the [`deferred-work` skill](../../deferred-work/SKILL.md)

#### 13. Decisions & Trade-offs

```markdown
## Decisions & Trade-offs

Document technical decisions made during implementation:
- **Decision 1**: Why and what trade-offs
- **Decision 2**: Alternatives considered
```

**Purpose**: Document architectural decisions and rationale.

**Guidelines**:
- Explain key technical decisions
- Document trade-offs and alternatives
- Provide context for future maintainers
- **Record a workflow the developer chose over the one this change's `Type` implies** — a feature
  planned without a PRD, a restructure planned with acceptance tests instead of a `plan.jsonl`, a
  verification rung below the one available. Name what was traded and that it was their call. This
  is what turns a missing artifact into a **choice**: without the line, `/validate-changes` reports
  it as a defect and the next reader re-opens a settled question

#### 13.5. Deferred Answers — the questions this change decided under `#yolo`

**Required when a run on this change wrote a deferred-answer record. Omitted entirely otherwise.**
Each command that writes a record (`behaviour-modifiers` skill, `references/yolo.md`) adds its row
here in the same commit as the record. A supervisor's review updates the row when the asker pastes
it in.

```markdown
## Deferred Answers

| Record | Kind | Question | Asker's pick | Supervisor | Decision | Built on it |
|---|---|---|---|---|---|---|
| `src/surmap/surmap-server/docs/deferred-answers/2026-10-23-caption-store.md` | Technical | Where do user captions persist? | b) dataset row | Refined → c) sidecar file | c) | `src/captions/store.ts`, commit `abc1234` |
| `docs/src/surmap/deferred-answers/2026-10-23-captions-empty-state.md` | Product | What does an empty captions list show? | a) hint text | — | a) | `CaptionsDialog.tsx`, acceptance test `captions-empty` |
```

**Purpose**: the record files outlive the changeset, which wrap deletes. This section is what ties
them to *this* change while it is in flight, and it is what the wrap carries into the history
entries (§17, `/wrap-context-docs` step 7c). It is also the source of the PR body's
`## Deferred answers` section.

**Guidelines**:
- One row per record, and never the record's content. The question is a few words, and the record
  holds the options and the reasoning
- Paths in backticks, never links. A record is deleted when the developer reviews it
- Not a substitute for **Decisions & Trade-offs**. A choice made with the developer, or one no one
  would have asked about, goes there. A row here is a question the developer *would* have been asked

#### 14. Refactoring Needed

```markdown
## Refactoring Needed

Track code quality issues and refactoring opportunities discovered during development:

### From the Red step (Acceptance Test Creation)
- Issue: Description
- Issue: Description

### From @red (TDD Red Phase)
- Issue: Description
- Issue: Description

### From @validate-changes (Change Validation)
- Issue: Description
- Issue: Description

### From @validate-tests (Test Quality)
- Issue: Description
- Issue: Description

### From @prod-ready (Production Readiness)
- Issue: Description
- Issue: Description

### From @analyze-clean-code (Code Quality)
- Issue: Description
- Issue: Description

### From @refactor (Completed Refactorings)
- Refactoring: Description — done
- Refactoring: Description — done
```

**Purpose**: Central tracking of all refactoring needs discovered throughout development lifecycle.

**Guidelines**:
- Add issues as discovered by any rule
- Organize by source rule for traceability
- Each issue a refactor will address is also a TODO under the row that does it (usually Wrap);
  the bullet here keeps its detail
- Updated by: planning, TDD, coding review, testing review, and code-cleaning workflows as implementation progresses

#### 15. Validation Results

```markdown
## Validation Results

### Change Validation (@validate-changes)

**Last Run**: YYYY-MM-DD
**Status**: ✅ Passed | ⚠️ Warnings | ❌ Issues Found

**Summary**:
- Files changed: X
- Test impact: Y tests affected
- Risk assessment: Low/Medium/High

**Critical Issues**:
- Issue 1: Description
- Issue 2: Description

**Recommendations**:
- Recommendation 1
- Recommendation 2

---

### Test Validation (@validate-tests)

**Last Run**: YYYY-MM-DD
**Status**: ✅ Passed | ⚠️ Warnings | ❌ Issues Found

**Summary**:
- Tests analyzed: X
- Anti-patterns found: Y
- Description-body mismatches: Z

**Critical Issues**:
- Issue 1: Description (file:line)
- Issue 2: Description (file:line)

**Recommendations**:
- Recommendation 1
- Recommendation 2

---

### Production Readiness (@prod-ready)

**Last Run**: YYYY-MM-DD
**Status**: ✅ Ready | ⚠️ Gaps | ❌ Blockers

**Summary**:
- Mock code in production: X instances
- Fallback code: Y instances
- Unimplemented features: Z

**Blockers**:
- Blocker 1: Description
- Blocker 2: Description

**Recommendations**:
- Recommendation 1
- Recommendation 2

---

### Code Quality (@analyze-clean-code)

**Last Run**: YYYY-MM-DD
**Overall Score**: X/10 ⭐

**Summary**:
- Critical issues: X
- Major issues: Y
- Minor issues: Z

**Critical Issues**:
- Issue 1: Description (file:line)
- Issue 2: Description (file:line)

**Recommendations**:
- Recommendation 1
- Recommendation 2
```

**Purpose**: Document findings from validation rules to track quality and readiness.

**Guidelines**:
- Update after each validation run
- Keep latest results at top
- Preserve historical results for audit trail
- Link to refactoring items when applicable
- Updated by: `/validate-changes`, `/validate-tests`, `/validate-prod-ready`, `/analyze-clean-code`

**Format for each validation**:
- **Last Run**: Date of validation
- **Status**: Overall pass/warning/fail indicator
- **Summary**: Key metrics and counts
- **Critical Issues**: Must-fix items
- **Recommendations**: Suggested improvements

#### 16. References

```markdown
## References

- Related changesets: [link]
- Design documents: [link]
- Feature requirements: [link]
```

**Purpose**: Link to related documentation.

#### 17. Wrap TODOs (formerly the Final Checklist)

**Required for the verification item (§9.5); otherwise include whenever there are tasks that must
run at wrap time.**

Concrete, self-contained tasks that `/wrap-context-docs` must execute before the changeset is archived, written as TODOs nested under the Wrap row — no `## Final Checklist` section. Items can be anything — documentation updates, changelog entries, file edits, external system changes. Not limited to any particular type. Tick each `[x]` only after it has been completed and verified.

```markdown
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded
  - [ ] {Concrete task — specific enough to execute without re-reading the changeset}
```

**Examples of typical items:**

```markdown
- [wf 5] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs (and sync the Roadmap) ·
  - [ ] `src/stories/PointCloudViewRoadmap.mdx` — ProgressTable `{ id: 'F-4' }`: `status: 'planned'` → `'done'`
  - [ ] `src/stories/PointCloudViewRoadmap.mdx` — FeatureDemo F-4 rows: flip all `done: false` → `done: true`
  - [ ] `mapping-pipeline/point-cloud-view/docs/changesets/YYYY-MM-DD-short-description.md` — write release-note file
  - [ ] `docs/mapping-pipeline/mapping-pipeline-editor/feature.md` — update API table with new endpoint
  - [ ] `src/surmap/README.md` — architecture diagram: apply the `### Architecture Diagram` update
  - [ ] Notify #survey-team Slack that F-4 has shipped
```

**When to add them:**
- **Always, for the one item every changeset owes**: `Verification executed — result recorded` (see
  §9.5). It is the item most easily lost between implementation and wrap, and the one that decides
  whether the PR proved anything
- Whenever there are tasks that can be forgotten between implementation and wrap
- The optional `/pr-wrap` steps this change needs (validate-tests, validate-prod-ready,
  analyze-clean-code, `/analyze-code-issues` — `/pr-wrap` § *Workflow row*, *Row TODOs*); `/pr-wrap`
  seeds its always-run steps itself and may add optional ones if the scope grows during the run. A
  step marked `(optional) … — run if <condition>` is decided by `/pr-wrap` at run time
- `/roadmap-red` always adds Roadmap sync TODOs from the MDX content
- `/roadmap-red` and a Stash-planned stack node always add the Stash publish (or manual-advice) TODOs `## Stash Tracker` lists
- A changeset with a `## Deferred Answers` section (§13.5) always carries
  `Deferred answers carried into the history entries`, which is `/wrap-context-docs` step 7c
- A `Type: Refactor` changeset always carries them: a behaviour-preserving change wraps to a changelog entry plus only those dev-doc statements the move made false, and that list is derived at plan time — see the `code-restructuring` skill
- Any changeset can use them for any wrap-time obligation

**Guidelines**:
- Each item must be checkable without reading any other part of the changeset
- Be specific: name the exact file, field, or system to update
- Ticked `[x]` by `/wrap-context-docs` as each item is completed

## Changeset Lifecycle

**Nothing links to a changeset.** No stable document — `1-OVERVIEW.md`, a feature doc, a changelog
entry, a package `README.md` / `README.md` / `docs/` page — references a changeset or its
initial-discovery companion in `1-WIP/`, by link or by path (`docs/AGENTS.md` § *Nothing links into
`1-WIP/`*). Both are deleted at wrap; where a stable doc must name in-flight work, it names the PR
number.

### 1. Created (planning workflow)

**State**: New changeset document created
**Status**: `🚧 In Progress`
**Rows**: all ⬜ but the planning rows; every TODO `[ ]`

**Actions**:
- Companion `YYYY-MM-DD-feature-name-initial-discovery.md` already written (planning-phase Step 2)
- `<package-dir>/docs/todo/` and every in-scope `<package-dir>/docs/code-issues/` cross-checked (planning-phase
  Step 2b), with a verdict per relevant item in `## Prerequisites`
- Document created with full template, including `## Initial Discovery` linking to that companion
- Affected packages listed
- State A, State B, Delta defined
- Implementation milestones and acceptance tests planned as TODOs under the Green row, wrap
  obligations under the Wrap row

### 2. In Progress

**State**: Active development
**Status**: `🚧 In Progress`
**Rows**: ⬜ → ⏳ → ✅; each row's TODOs go `[ ]` → `[x]` (open or done, nothing between)

**Actions**:
- Milestone and acceptance-test TODOs ticked as completed / as they pass
- Each command seeds its *Row TODOs* under its row when the row starts and ticks them
- Technical debt items added as discovered
- Decisions documented as made
- Under `#yolo`, each deferred-answer record listed in `## Deferred Answers` in the same commit
  that writes it (§13.5)
- **Refactoring issues tracked** as discovered by validation rules
- **Validation results** added after each validation run

**Updated by**:
- `/green` - Fills each `## Prerequisites` row's **Outcome** cell (step 3.5a) and reconciles the
  deferred-work records to match (3.5b)
- `/update-context-docs` - Ticks the rows' TODOs the implementation completed
- Every step command - Marks its own `[wf <n>]` row ⏳ on start and ✅ / ⛔ / ➖ with evidence on
  finish ([the `pr-lifecycle` skill](../../pr-lifecycle/SKILL.md) § *Step contract*)
- The Red step (`/plan-red`, `/red`) - Creates acceptance tests, ticks its rows' TODOs, adds refactoring issues
- `tdd` - Adds refactoring issues from TDD phases and tracks test progress
- `coding` - Adds validation results and code quality findings
- `testing` - Adds test validation results and testing-related follow-up
- `code-cleaning` - Ticks completed cleanup/refactoring TODOs and adds results

### 3. Complete

**State**: All work finished
**Status**: `✅ Complete`
**Rows**: every row before Wrap ✅ or ➖, with no open TODO

**Prerequisites**:
- Every TODO under the rows before Wrap ticked `[x]` — milestones, Scope deliverables, acceptance tests passing
- Technical debt addressed or documented
- Every `## Prerequisites` row's **Outcome** cell filled (✅ resolved / ◐ partly / ➖ unchanged /
  ⛔ deferred), the restructure prerequisite executed, each record matching its Outcome — resolved
  records deleted, partly-addressed updated and left open with its remainder narrowed — and anything
  deferred carrying a TODO file with a named blocker and recorded consent
- Code quality validated
- **All validation results** show passing status
- **All refactoring issues** addressed or documented

**Actions**:
- Status changed to `✅ Complete`
- Ready for wrapping

### 4. Wrapped (`/wrap-context-docs`)

**State**: Applied to dev docs, deleted
**Status**: Deleted

**Actions**:
- Changeset applied to package READMEs and `packages/{pkg}/docs/`
- State B content merged into stable docs
- Delta, milestones, Scope sections removed from final docs
- **Refactoring Needed** section removed (issues should be resolved)
- **Validation Results** section removed (not preserved)
- Changeset **deleted**: `YYYY-MM-DD-changeset-name.md` (not archived)
- Companion **deleted**: `YYYY-MM-DD-changeset-name-initial-discovery.md` (not archived, not merged into package docs)
- Release note-style file written to `{group}/{pkg}/docs/changesets/YYYY-MM-DD-short-description.md`
- **Nothing links to that file.** A history entry is terminal: no stable document — an `README.md`,
  a `README.md`, a `docs/` page, a `docs/<area>/` feature doc — may reference an individual entry under
  `docs/architecture.md` or `docs/<area>/*/changelog/`, in any form (a `See [changesets/…](…)` trailer, an
  `**Implementation**: see …` line, a parenthetical, a "Change History" list, or a **bare path in
  backticks** — the test is what it points at, not how it is spelled). An entry records one
  dated delta and is never revised, so a document stating current behaviour that links to one goes
  stale as soon as a later entry supersedes it. If the fact still matters, write the **fact** into
  the stable doc in State B. A single pointer at the `docs/architecture.md` **directory** is the
  permitted exception; links out of an entry — to PRs, stable docs, other entries — are free

## Cross-Package Changesets

A single changeset can span multiple packages:

```markdown
## Affected Packages

- **surmap**: [README.md](../../mapping-pipeline/stereo-ingest/README.md)
  - [architecture.md](./stereo-ingest/architecture.md) - Parser updates
  - [api-reference.md](./stereo-ingest/api-reference.md) - New parse methods

- **surmap**: [README.md](../../mapping-pipeline/mapping-pipeline-server/README.md)
  - [integration.md](./mapping-pipeline-server/integration.md) - Parser integration
  - [api-reference.md](./mapping-pipeline-server/api-reference.md) - Updated endpoints

- **surmap**: [README.md](../../mapping-pipeline/mapping-pipeline/README.md)
  - [api-reference.md](./mapping-pipeline/api-reference.md) - Client API updates
```

## Best Practices

### Do's ✅

- **Write the initial-discovery companion first** (`{slug}-initial-discovery.md`) and open the changeset with `## Initial Discovery`
- **List ALL affected packages** (even minor changes)
- **Describe State A and State B clearly** with technical specifics
- **Make milestones specific and measurable** (verifiable deliverables)
- **Define acceptance tests for each package** with file paths
- **Tick each row's TODOs** as work progresses
- **Document decisions and trade-offs** as they're made
- **Keep changeset timing-agnostic** (milestones, not dates)
- **Use relative markdown links** for cross-references

### Don'ts ❌

- **Don't modify dev docs directly** (use changeset workflow)
- **Don't include process instructions** in changeset (focus on technical outcomes)
- **Don't skip "Affected Packages" section** (required)
- **Don't create changeset without reading State A docs** (know current state)
- **Don't forget to link to feature/PRD docs** (maintain traceability)
- **Don't guess at package scope** (read code/docs first; persist that exploration in the discovery companion)
- **Don't skip Scope section** (required for tracking)
- **Don't skip Initial Discovery** (required; the companion file must exist)
- **Don't leave `Type` / `Behaviour` at a guess** (they decide whether a PRD is warranted, which
  template applies and what the first commit contains — settle them before writing the body)
- **Don't skip `## Verification`** (required for every `Type`; a change with no stated proof is not
  planned, and a reviewer reading the diff is not a method)
- **Don't declare a verification method and never run it** (§9.5 is executed and its result recorded
  — that is the Wrap-row TODO every changeset owes)
- **Don't merge discovery dumps into package docs** (wrap deletes the companion)

## Validation Checklist

**Before wrapping** (`/wrap-context-docs`):
- [ ] `{slug}-initial-discovery.md` exists next to the changeset (wrap deletes it; do not merge into package docs)
- [ ] Every row before Wrap ✅ or ➖, with no open TODO under it — milestones, Scope deliverables,
      acceptance tests passing — or each open one carrying its deferred-work record
- [ ] **`## Verification` executed and its result recorded** — the `Command` re-run, the `After`
      state observed and written down (for V4, the evidence attached and the consent line present)
- [ ] Technical debt addressed or documented
- [ ] Status changed to `✅ Complete`
- [ ] All affected packages listed with valid links
- [ ] State B clearly defined
- [ ] **All validation results show passing status**:
  - [ ] @validate-changes: ✅ Passed
  - [ ] @validate-tests: ✅ Passed
  - [ ] @prod-ready: ✅ Ready
  - [ ] @analyze-clean-code: Score ≥ 7/10
- [ ] **All refactoring issues** resolved or documented as acceptable technical debt

## Related Rules and Commands

**Related References**:
- `dev-doc.md` - Development documentation structure
- `feature-doc.md` - Feature documentation that drives changesets
- `pr-lifecycle/references/prd.md` - PRD documents that link to changesets
- `initial-discovery.md` - Explore / Discovery companion file next to the changeset

**Related Prompts**:
- `.agents/commands/update-context-docs.md` - Update changeset during development
- `.agents/commands/wrap-context-docs.md` - Apply changeset to dev docs when complete

**Related Skills**:
- `planning` - Create and maintain planning docs
- `tdd` - Drive implementation from failing tests
- `coding` - Review implementation and production readiness
- `testing` - Review test quality and failures
- `code-cleaning` - Perform cleanup and final wrap-up

**Workflow Integration**: the order of steps is this changeset's own `[wf <n>]` rows (§1.5),
not a fixed chain. [the `pr-lifecycle` skill](../../pr-lifecycle/SKILL.md) § *Presets* holds the starting table for each kind
of change.
