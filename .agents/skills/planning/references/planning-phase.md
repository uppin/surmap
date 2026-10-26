# Planning Phase — Shared Reference

Canonical steps for interviewing the user, analyzing the codebase, and producing PRD + changeset documents. Referenced by planning skills and commands — follow these steps exactly.

Questions belong **before** the plan is written: the Step 1 interview, and the Step 2b
ground-softening question. Once the PRD and changeset exist nothing waits for a review — what a
review would have shown goes into the turn's summary under **Decided without review**, and what
genuinely needs the developer halts the planning row ⛔ (the `pr-lifecycle` skill § *Halts*).

## Step 1: Interview the User

**MANDATORY** — Ask the user these questions before proceeding. Do NOT skip or assume answers.

1. **What** — What is the feature or change? New feature or modification to existing?
2. **Why** — What problem does this solve? What is the motivation?
3. **Where** — Which packages / product areas are affected?
4. **Constraints** — Any specific requirements, performance targets, compatibility needs?
5. **UX** — Design preferences, user experience expectations?
6. **Scope** — What is explicitly out of scope?

Adapt follow-up questions based on answers. Keep interviewing until requirements are clear enough to write the PRD.

## Step 2: Analyze Existing Code

**MANDATORY** — Read the codebase before writing any documents. The exploration is the
changeset's discovery companion (the `pr-lifecycle` skill § *Start a changeset*, steps 2–3), so pick
the changeset slug now and write the companion before the PRD as well as the changeset.

**How to explore**:
- **On Muse**: launch the `explore` subagent via `Task` (`subagent_type: "explore"`) with the
  dump contract from `initial-discovery.md`.
- **On other harnesses**: use the equivalent Explore agent, or run Grep / Glob / Read yourself.

Record **every** pass: inspected files and code excerpts, grep/glob patterns, and the sequence of
the exploration. Combined conclusions go at the **top** of the discovery file; each pass is a
separate `## Exploration N` section at the **tail**. Further explorations during later steps
append a new pass and rewrite Combined Conclusions — they do not replace earlier passes.

For each affected package:
1. Read `packages/{package}/README.md`
2. Read `packages/{package}/docs/` (if exists)
3. Read `packages/{package}/AGENTS.md`
4. Read relevant source files to understand current architecture, APIs, and behavior
5. Check `docs/<area>/1-WIP/` for conflicting active changesets
6. Check `docs/{product-area}/` for existing feature docs

**Architecture diagrams — find the declaration, not the diagram.** Many packages and package
groups keep an **architecture diagram**: the components and the topology between them. It is
*declared*, not searched for — the owning `README.md` carries a line like:

```markdown
**Architecture diagram:** [`README.md`](./README.md) (mermaid) — group-level component topology
```

For each package in scope, resolve the diagram **in this order**: the package's own `README.md`
first (a package-internal diagram), then the **group-level `{group}/AGENTS.md`** (e.g.
`src/surmap/AGENTS.md`), which carries the group's cross-package topology. `mermaid` is the
default format; a declaration that names another format (PlantUML, D2, an image) wins for that
diagram. No declaration anywhere → the package has no diagram — note that in the discovery file and
plan nothing: an undeclared diagram is not a planning concern.

**If the change alters the architecture a diagram depicts** — a component added, removed, split or
re-homed, a connection or data flow changing — the changeset must **specify the diagram update**:
an `### Architecture Diagram` block in `## Technical Changes` (`pr-lifecycle/references/changeset.md` §8) naming the
diagram's file and format and stating exactly what changes in it. Planning only names the update —
the diagram file itself is never edited here; `/wrap-context-docs` applies the update at wrap time,
from the changeset's spec.

Document findings as **State A** (current state) — this becomes the baseline for the changeset.
State A in the changeset is distilled from the discovery file; do not dump grep traces into the
changeset.

## Step 2b: Cross-check the deferred-work records — MANDATORY

Three records inside `deferred-work/` hold work this repo knowingly did not do, or decisions
nobody has reviewed, and some of it will be sitting directly in the path of what you are about to
plan:

| Record | Path |
|---|---|
| Changeset TODOs | `<package-dir>/docs/todo/` |
| Code issues | `<package-dir>/docs/code-issues/`, for every package in scope |
| Deferred answers — `#yolo` decisions awaiting review | `<package-dir>/docs/deferred-answers/` (Technical) and `docs/<area>/deferred-answers/` (Product) |

**Follow [`deferred-work/references/planning-cross-check.md`](../../deferred-work/references/planning-cross-check.md)**
— it owns this step: the scan commands, the verdict table (⛔ blocking / ⚠ during / ℹ answered /
— unrelated), how to right-size each fix, the **restructure prerequisite** contract that `/green`
executes before any implementation, and what to do when a restructure spans a whole PR stack.

Scan **after** Step 2's code analysis, when you know which files and modules the change touches, and
**before** the changeset is written. Discovering one of these during `/green` is late: by then the
only choices are to work around it, silently make it worse, or stop.

**That page has two halves.** The scan finds debt somebody already recorded. The section
*Softening the ground* is the other source: **your own reading of the code in Step 2**, where the
structure as it stands would make this change harder or riskier than it needs to be — a function no
test can reach, a dependency constructed inline, an obvious seam about to gain a fourth
responsibility. The strongest signal comes at the **acceptance-test step** — `/plan-red` Step 8,
`/plan-pr-stack` Step 6e, or the equivalent in whichever command called this reference: **if a clean
failing test cannot be written against the current shape**, that is the finding, and it is worth
returning to this step rather than testing through two layers of doubles.

Those are **suggested to the user, never decided** — a preparatory restructure spends review budget
before the feature has earned any. Present the difficulty it removes, the operations, the measured
blast radius, the cost, and what skipping it costs; then ask. Approved, it becomes an ordinary
Restructure Prerequisite; declined, the observation is filed (a code issue if measurable, else a
`Future enhancement` TODO) and noted in `## Decisions & Trade-offs`.

Two things to carry out of that page and into the changeset:

- **Every relevant item gets a verdict in `## Prerequisites`** (`pr-lifecycle/references/changeset.md` §2.5) — including
  the ones you decide not to fix, so a reviewer sees the item was weighed rather than missed. A ⛔
  blocking item also earns a TODO under the row that clears it, because it is work rather than a note.
- **A package in scope with no `<package-dir>/docs/code-issues/` directory has not been analyzed** — say so.
  That is not the same as clean; run `/analyze-code-issues` when the change lands in code the
  analyzers would have something to say about.

The bar for *writing* to either record — a changeset's goal is its full planned scope, and deferring
any of it needs a named blocker, refuted alternatives and the developer's recorded consent (their
answer to a ⛔ halt of the row, the `pr-lifecycle` skill § *Halts*) — is in
[`deferred-work/SKILL.md`](../../deferred-work/SKILL.md).

## Step 3: Identify Product Area

Determine which product area the feature belongs to:
- `base-station` — SAM segmentation, labelling and the semantic map (Machine 2)
- `mapping-pipeline-server` — Backend map service
- `session-processing` — Core map manipulation
- `gotenberg-service` — Document conversion
- `mcp-servers` — MCP server implementations
- `infrastructure` — Logging, observability, BI
- Other — create new product area directory if needed

## Step 4: Create PRD Document

**Location**: `docs/{product-area}/1-WIP/PRD-YYYY-MM-DD-feature-name.md`

Follow the PRD template from `.agents/skills/pr-lifecycle/references/prd.md`.

Include:
- Header metadata (date, PRD type)
- Affected features (ALL feature documents impacted)
- Summary and background
- Proposed changes (what's changing, what's staying the same)
- Impact analysis (technical + user)
- Implementation plan
- Acceptance criteria with checkboxes
- References to affected features

**Do not reference the PRD from `1-OVERVIEW.md` or any other stable document** — nothing links
into `1-WIP/` (`docs/AGENTS.md` § *Nothing links into `1-WIP/`*). The PRD lists the feature docs it
affects; the feature docs learn of it only when `/wrap-context-docs` merges its content in.

Go on to the changeset without a PRD review: the PRD's path, its affected features and its
acceptance criteria are listed in the summary under **Decided without review**. A requirement the
interview left open is asked about **before** the PRD is written, not after.

## Step 5: Create Changeset Document

Start the changeset per the `pr-lifecycle` skill § *Start a changeset*
(`.agents/skills/pr-lifecycle/SKILL.md`): the calling command closes its own planning row with
evidence and every later row starts ⬜; the discovery companion already exists from Step 2, and
`## Prerequisites` carries Step 2b's verdicts and any **Restructure Prerequisite** block
(`pr-lifecycle/references/changeset.md` §2.5) — omitted entirely when the scan found nothing relevant.
Beyond the skill's list, the planning flow fills:

- Affected packages (ALL packages with links to READMEs and docs)
- Related feature documentation (link to PRD from Step 4)
- Summary and background
- Scope (high-level deliverables; their progress is TODOs under the rows, never checkboxes here)
- Technical changes — **State A** distilled from the Step 2 analysis
- Implementation milestones (specific, measurable — TODOs nested under the Green row)
- Testing plan:
  - Determine appropriate test level (E2E / Integration / Unit)
  - Testing options analysis with trade-offs
  - Coverage requirements
- Acceptance tests (per-package, with descriptive names and file paths)
- Technical debt & production readiness (empty, populated during development)
- Decisions & trade-offs (document choices made during planning)
- Refactoring needed (empty sections per validation phase)
- Validation results (empty sections per validation command)

**CRITICAL**: Take extra time on the testing strategy. This directly feeds the red phase — every acceptance test defined here becomes a real test file. Define:
- Descriptive test names that read as behavior specifications
- Exact file paths where each test will live
- What each test validates and why it matters

**MANDATORY**: Nest the plan-derived TODOs under the `## Workflow` rows that do them — the only
checkboxes in the changeset (`  - [ ]` / `  - [x]`). The planning row's are ticked by this phase;
each later command seeds its own *Row TODOs* when its row starts, after the planner's. Under Wrap go
the wrap obligations (always `Verification executed — result recorded`) plus the optional `/pr-wrap`
steps this change needs (`/pr-wrap` § *Workflow row*, *Row TODOs*) — plainly, or `(optional) … — run
if <condition>` for `/pr-wrap` to decide; it may add more if scope grows. None of them is a review gate.

```markdown
## Workflow

- [wf 1] ✅ YYYY-MM-DD `/plan-red` Plan — PRD, changeset, initial discovery · PRD + this file
  - [x] Record initial discovery (`YYYY-MM-DD-feature-name-initial-discovery.md`)
  - [x] Cross-check the deferred-work records — TODOs, code issues and deferred answers (Step 2b)
  - [x] Create/update PRD documentation
  - [x] Create changeset (this document)
- [wf 2] ⬜ `/plan-red` Red — acceptance and failing lower-tier tests, committed ·
- [wf 3] ⬜ `/green` Green — implement until every red test passes ·
  - [ ] Restructure prerequisite (`/code-restructuring`) — only if `## Prerequisites` names one
  - [ ] Milestone 1: {specific, measurable}
  - [ ] Acceptance: {test title} (`feature.e2e.test.ts`) passes
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded
  - [ ] Validate tests (`/validate-tests`)
  - [ ] (optional) Production readiness validated (3) — run if the diff reaches server code
  - [ ] Close resolved `<package-dir>/docs/todo/` and `<package-dir>/docs/code-issues/` records; file a TODO for anything deferred
- …
```

## Step 6: Worktree Setup and Handoff

Present complete summary:

```
**CRITICAL FOR CONTEXT & SUMMARY**

PRD created: docs/{product-area}/1-WIP/PRD-YYYY-MM-DD-feature-name.md
Changeset created: docs/<area>/1-WIP/YYYY-MM-DD-feature-name.md
Initial discovery: docs/<area>/1-WIP/YYYY-MM-DD-feature-name-initial-discovery.md
Workflow: <preset> — <k> rows; planning row ✅

Affected packages:
- surmap
- surmap

Acceptance tests planned:
- test-name-1 (packages/package-1/tests/test-file.test.ts)
- test-name-2 (packages/package-2/tests/test-file.test.ts)
```

**Step 6a: Write `tmp/current-worktree.json`**

Write this file at the **repo root** (not the worktree) so `uv run pytest -q` can auto-apply values:

```json
{
  "worktree": "<absolute-path-to-worktree>",
  "changeset": "docs/<area>/1-WIP/YYYY-MM-DD-feature-name.md",
  "prd": "docs/{product-area}/1-WIP/PRD-YYYY-MM-DD-feature-name.md",
  "conversation": "<path-to-conversation-jsonl>"
}
```

Omit the `"prd"` field if no PRD was created. Use `$(pwd)` for the worktree path.

The conversation JSONL path is derived from the `CLAUDE_CODE_SESSION_ID` environment variable: `~/.claude/projects/<project-slug>/$CLAUDE_CODE_SESSION_ID.jsonl`. The handoff script converts it to readable Markdown and opens it in Muse.

**Step 6b: Setup the worktree**

Install dependencies, then build only the packages the work needs:

```bash
cd <worktree-path> && uv sync --group dev \
  && uv run mypy
```

**Step 6c: Run the handoff script**

```bash
./scripts/worktree-handoff.sh
```

**CRITICAL**: Always use the relative path `./scripts/worktree-handoff.sh` (not an absolute path) so the command matches the allowed permission pattern.

## Rules

- Never skip the user interview — requirements come from the user, not assumptions
- Never skip code analysis — State A must reflect actual current implementation
- Never skip Step 2b — cross-check the deferred-work records (`<package-dir>/docs/todo/`,
  `<package-dir>/docs/code-issues/` and `<package-dir>/docs/deferred-answers/` for every package in
  scope, `docs/<area>/deferred-answers/` for the owning area, **plus** a repo-wide
  `grep -rl -F '@/<your-package>' */*/docs/todo/` for items another package owns that name yours)
  before writing the changeset, and give every relevant item a verdict in `## Prerequisites`,
  including the ones you decide not to fix. The rules live in `.agents/skills/deferred-work/`; the
  records do not
- **Suggest a ground-softening restructure where the current structure would make this change harder
  — and ask before planning it in.** Justify it by a named difficulty in *this* changeset, never by
  general tidiness; if declined, file the observation and record the decision
- A changeset's goal is the **full planned scope**. Deferring planned scope needs a named blocker,
  refuted alternatives and the developer's recorded consent — asked for by a ⛔ halt of the row,
  never mid-turn; see the `deferred-work` skill
- The initial-discovery companion is a full Explore dump, not a summary; append later passes,
  wrap deletes the file
- Always read existing docs/code before writing State A
- List the PRD in the summary under **Decided without review** — no PRD review gate
- Take extra time on testing strategy — don't rush
- Determine appropriate test level based on changeset scope
- List ALL affected packages, even for minor changes
- Make milestones specific and measurable
- Define acceptance tests with descriptive names and file paths
- Don't modify `{common,common-testing,mapping-pipeline,onboard-detection,surmap,packages}/*/docs/` directly — use changeset workflow
- Don't reference a PRD, changeset or discovery companion from any stable document — `1-OVERVIEW.md`,
  a feature doc, a package `README.md` / `README.md` / `docs/` page. Nothing links into `1-WIP/`
  (`docs/AGENTS.md`)
- Don't create changeset without reading State A docs
- Don't include process instructions in changeset content
- Quality first — never compromise document quality
