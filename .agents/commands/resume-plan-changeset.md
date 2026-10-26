---
description: Resume or continue planning from a changeset (Plan mode); infer changeset from git or use a named one; read or backfill its [wf] rows; derive TODOs from the changeset; sync MD when execution starts
---
# Resume Plan from Changeset

Resume technical planning anchored to a **changeset** in `docs/<area>/1-WIP/`. Outcome: an agreed execution plan whose backlog comes **only** from the TODOs nested under the changeset's `[wf]` rows (and user refinements), ready for implementation.

## Intent vs non-goals

- **Intent**: Pick the right WIP changeset, read where it stands from its **`[wf]`** rows (backfilling them when it has none), ground discussion in State A (stable dev docs + code), reproduce the rows' **TODOs** **line-by-line** (including ticked ones), **strip checkbox markers** in plan output (status lives in the changeset and in `planning workflow` todo `status`, not as `[ ]` / `[x]` in the plan list), **append command/doc references** for automatable steps, and incorporate user refinements (including revisiting “done” work).
- **Non-goals**: Do not land production code or tests while still in Plan mode. **Do not** invent a parallel, shortened, or reordered TODO list (including via `planning workflow` frontmatter todos, milestone lists, or “recommended implementation order” sections that replace the changeset workflow).

## Plan mode (mandatory)

This process MUST run in **Plan** mode.

1. **On Muse**: invoke `plan mode` with `target_mode_id: "plan"` and a short `explanation` (e.g.
   resume changeset planning before implementation).
2. **On a harness without a mode-switch tool, or if the user declines**: ask the user to switch to
   Plan mode manually (in Claude Code, `/plan`) and confirm before continuing.

**Edits during Plan mode**: Prefer **read-only** planning in chat. **Do not** update the changeset file (or code) during Plan mode unless the user **explicitly** asks for draft edits to the markdown; the canonical sync of the changeset to the **confirmed** plan is the **first step after** Plan mode ends (see below).

## Changeset rules in this repo

Follow **`.agents/skills/pr-lifecycle/references/changeset.md`**: `skill `references/``. It defines sections, the rule that every checkbox is a TODO nested under its `[wf]` row (`[ ]` / `[x]` only), and lifecycle.

## Select the active changeset

### User specified a changeset

If the user names a file, path, or title (e.g. `2026-05-16-layer-center-debug-overlay.md` or `docs/<area>/1-WIP/...`), normalize to `docs/<area>/1-WIP/<file>.md`, verify the file exists, and use it.

### Otherwise: infer from git vs base branch

1. **Base branch** (integration base), in order:
   - `git symbolic-ref refs/remotes/origin/HEAD` → e.g. `refs/remotes/origin/master` → use `origin/master`
   - Else `origin/master`, then `origin/main`
   - If still unclear, ask which ref is the base.

2. **Merge base and changed paths** (from repo root):
   - `mb="$(git merge-base HEAD <base-ref>)"`
   - Default: **`git diff --name-only "$mb" HEAD`** (commits on the branch vs base).
   - If the user clearly cares about **uncommitted** work: also show `git status --short` and consider `git diff --name-only` against `HEAD` for working tree; say which view you used.

3. **Resolve to one file** in `docs/<area>/1-WIP/*.md`:
   - **First**: Any `docs/<area>/1-WIP/*.md` path that appears in the changed-path set.
   - **Second**: The changeset whose **Affected Packages** / links / described paths **best cover** the changed paths (`packages/`, `docs/dev/`, workspace `README.md`, etc.). Prefer the **narrowest** changeset that still covers all touched packages, if that is obvious.
   - **Tie-break** (if multiple candidates remain): Prefer the WIP file **most recently modified** in git history among candidates (`git log -1 --format=%ct -- <path>`), or ask the user.
   - **If zero or still ambiguous**: Stop and ask for the exact `docs/<area>/1-WIP/<name>.md` path.

## Grounding in State A (planning)

After the changeset is selected:

1. Read the **full** changeset (header through latest section).
2. Read the companion `{changeset-slug}-initial-discovery.md` in the same WIP directory when it
   exists (`## Initial Discovery` links to it). Combined conclusions are the synthesis; each
   `## Exploration N` is the raw pass. If further Explore / Grep / Glob / Read work happens while
   resuming, **append** a new Exploration section and rewrite Combined Conclusions — do not
   overwrite earlier passes. See `.agents/skills/pr-lifecycle/references/initial-discovery.md`.
3. For each **Affected Package**, read current stable pointers: `packages/{package}/README.md` and relevant `packages/{package}/docs/*.md` so the plan matches **today’s** documented State A.
4. If the changeset is stale vs the tree (e.g. files renamed), call that out in the plan and in the later MD sync.

## Workflow rows (status and sequence)

The changeset's `[wf]` rows (`.agents/skills/pr-lifecycle/SKILL.md`) are the sequence and
the status; the TODOs nested under each row are its detail (one grep, `^(- \[wf |  - \[[ x]\] )`):

- **Present**: copy them into the plan as-is — every row, its Status and Result. The next row (the
  skill's next-row grep) is where execution resumes. Refinements that invalidate a ✅ row's result (its tests,
  its implementation) list that row and every row below it for reset to ⬜.
- **Absent** (a changeset planned before the contract): derive it from the preset for the
  changeset's `(Type, Behaviour)` (the `pr-lifecycle` skill § *Presets*). Mark ✅ only the rows whose work the
  branch demonstrably holds — a red commit, green tests, an open PR — each with that evidence, and
  say in the plan that the rows were backfilled. A legacy `## TODO` section, or checkboxes in Scope /
  Milestones / Acceptance Tests / Final Checklist, move under the row that does each. It is written into the file at the sync after
  Plan mode (§ *After the plan is confirmed*), not during it.

## TODO list source (the rows' TODOs only)

Build the plan backlog **from the TODOs nested under the `[wf]` rows**. Do not replace it with a generic task template, Implementation Milestones order, or a custom “red/green” checklist.

### Line-by-line (mandatory)

Copy the rows' **TODOs** **in the same order** as the markdown, **one line per bullet**:

- **Label text**: Copy each row’s human-readable label **exactly** from the changeset (no paraphrasing, no skipping completed rows). Read checkbox state from the changeset (`[ ]` / `[x]`) but **do not** repeat markers in the plan.
- **Plan formatting — strip checkboxes**: In **Plan TODOs** (chat, plan file body, `planning workflow` todo `content`), emit plain bullets with **label + command parentheticals only**. Remove the leading `  - [ ]` / `  - [x]` from the source line, and group the bullets under their row. Example plan line: `- Create failing acceptance tests (\`.agents/commands/plan-red.md\`)` — not `- [ ] Create failing acceptance tests …`.
- **Changeset unchanged**: The WIP changeset keeps its nested checkboxes; only the **plan output** is stripped.
- **Do not** collapse bullets, **do not** skip completed rows, and **do not** silently reorder unless the user explicitly asks to reprioritize (default is **file order**).
- **Command references** are **appended** after the stripped label in the plan output (see below); they do **not** require editing the changeset file.

### Other sections (reference mirrors)

**Scope**, **Implementation Milestones** detail, **Testing Plan** assertions, **Acceptance Tests**, **Technical Debt**, **Refactoring Needed**, etc. carry no checkboxes — their progress is the rows' TODOs:

- Mirror them only as **reference** when useful—they are **not** a second execution workflow.
- **Milestone** TODOs (under Green) describe *what* to build; they do **not** replace the Red row's TODOs such as “Create failing acceptance tests”.

Respect markers: `[ ]` open, `[x]` done. If the user narrows scope, call out which **`[x]`** TODOs might need to be unticked / reworked after refinement.

### Command and doc references (mandatory)

For every automatable TODO, **append** the correct parenthetical after the **stripped** label.

1. Parse checkbox state from the changeset line; take **label text only** for the plan bullet.
2. **Append** the reference block (see mapping rules). If the changeset already has parentheticals (e.g. `/validate-changes`), **keep or normalize** to `.agents/commands/…` paths—do not drop them.
3. If no mapping exists, use `(no mapped command — confirm with user)`.

**Mapping rules**

- **Muse slash commands** → `.agents/commands/<name>.md` in backticks. Example:

  ```markdown
  - Validate changes (`.agents/commands/validate-changes.md`)
  ```

- **Multiple commands in one step**: comma-separated paths in one parenthetical:

  ```markdown
  - Repeat Red→Green→Update cycle until feature complete (`.agents/commands/red.md`, `.agents/commands/green.md`, `.agents/commands/update-context-docs.md`)
  ```

- **Legacy review-gate rows** (a changeset planned before the `pr-lifecycle` skill may still carry one): **no** command paths, and mark them *superseded — reported under the step summary's **Decided without review***. They are not gates any more.

- **`Refactor issues from …` / `Refactor test issues` / similar**: append `(follow findings from previous validation step; no separate command)` unless a dedicated refactor command exists.

- **Repo test/lint without a dedicated command** (`uv run pytest -q`, `uv run ruff check src tests`, `uv run mypy`): append `(see README.md)`.

**Standard TODO label → command map** (use when the changeset line matches; do not paraphrase the label):

| Verbatim label (substring match) | Append |
|--------------------------------|--------|
| Create failing acceptance tests | `.agents/commands/plan-red.md` |
| Run acceptance tests (verify they fail) | `.agents/commands/test-acceptance.md` |
| TDD Red | `.agents/commands/red.md` |
| TDD Green | `.agents/commands/green.md` |
| Update documentation with progress | `.agents/commands/update-context-docs.md` |
| Repeat Red→Green→Update | `.agents/commands/red.md`, `.agents/commands/green.md`, `.agents/commands/update-context-docs.md` |
| Run all tests (uv run pytest -q) | `README.md` |
| Validate changes | `.agents/commands/validate-changes.md` |
| Validate tests | `.agents/commands/validate-tests.md` |
| Validate production readiness | `.agents/commands/validate-prod-ready.md` |
| Analyze code quality | `.agents/commands/analyze-clean-code.md` |
| Final validation | `.agents/commands/validate-changes.md` |
| Linting and type checking | `README.md` |
| Wrap documentation | `.agents/commands/wrap-context-docs.md` |

**Persisting into the changeset file**

Only when the user **explicitly** wants the WIP markdown updated, or when you are already editing that file for other confirmed-plan edits: you **may** copy parentheticals into the TODOs. **Never** rewrite the TODOs **just** to add paths if the user asked to leave that document unchanged.

## Plan document structure (mandatory)

When producing a plan file (e.g. via `planning workflow`) **or** the main chat deliverable, use this order:

1. **Active changeset** — path, how chosen, link to PRD if any.
1a. **Workflow** — the `[wf]` rows with each row's Status and Result (or the backfilled rows, marked as such), and the row execution resumes at.
2. **Plan TODOs (authoritative)** — every row's TODOs, grouped under the row, **first substantive section**, one bullet per TODO: **stripped label** + command parentheticals (no `[ ]` / `[x]`). State explicitly: *this is the only execution backlog*.
3. **Notes for upcoming steps** (optional, **subordinate**) — file paths, test names, or State A→B summary that help the **next open** TODO only. Must **not** re-list or replace TODOs.
4. **Reference mirrors** (optional) — Scope, Implementation Milestones, Acceptance Tests copied line-by-line when useful.
5. **Revisit list**, **open questions**, **staleness**.

### planning workflow / tracked todos (mandatory)

**On Muse**, deliver the plan through the `planning workflow` tool. Elsewhere, present the plan inline in
the same order. Either way, if you emit a plan frontmatter `todos` array:

- **Every** frontmatter todo must correspond **1:1** to a single TODO line under a row (same **stripped** label text in `content`, same order). Set `status` from the changeset checkbox: `completed` for `[x]`, `pending` for `[ ]`; `in_progress` for a ⏳ row's first open TODO (if the plan tool supports it).
- **Forbidden**: condensed bundles such as “implement handler + consumer + tests”, “validate and wrap”, or milestone-only lists that omit workflow steps (acceptance-test steps, repeat Red→Green, separate validate/refactor rows).
- The plan body **must** still include the full **Plan TODOs** section even when frontmatter todos exist.

## Refinement during planning

The user may **change** scope, milestones, tests, or State B. Treat prior work as **conditional**: list which completed items may need **follow-up**. The **authoritative** execution order remains the **latest agreed rows and TODOs** (with refinements called out), not Implementation Milestones alone, until the changeset file is synced after plan confirm.

## After the plan is confirmed → implementation handoff

When the user **confirms** the plan and you move to **implementation** (typically **Agent** mode):

1. **First implementation action**: Update the **changeset Markdown** so it matches the confirmed plan (`[wf]` rows — written when they were backfilled, rows reset when refinement invalidated them — the rows' TODOs, Scope, Testing Plan, Acceptance Tests, State B / Delta). Remove or rewrite stale bullets from earlier iterations. **Do not** add command-path parentheticals to the TODOs unless the user wants that file updated or you are already changing those lines for other reasons. Commit it.
2. **Then** execution is the next `[wf]` row (the skill's next-row grep), run with its command (the same as `/next`); its open TODOs, in order, are that step's detail, resumed at the first open one (read the mapped `.agents/commands/*.md` for a row before acting).

## Rust toolchain (this workspace)

When proposing or running `cargo`, `rustfmt`, or `clippy`, use **`./dev`** from the repo root per `README.md` (e.g. `./dev cargo test -p package-name`).

## Chat output (mandatory close)

End the planning response with these sections **in order**:

1. **Active changeset path** and **how it was chosen** (explicit path vs git: base ref, merge-base, path set).
1a. **Workflow** — the `[wf]` rows with Status and Result, whether it was backfilled, and the row execution resumes at.
2. **Plan TODOs** — every row's TODOs, line-by-line: **labels without checkbox markers** + command/doc parentheticals (complete list; do not summarize into fewer bullets).
3. **Revisit list** — completed items (per changeset `[x]`) or tests that may need rework after refinement.
4. **Open questions** — or “none blocking”.
5. **Staleness** — changeset vs current tree/docs.

Technical context (State A/B, diagrams) may appear **above** the close only if **Plan TODOs** remain the obvious primary backlog; prefer putting long context after the TODO list or under **Notes for upcoming steps**.

## Related

- `.agents/skills/pr-lifecycle/references/changeset.md` — `skill `references/``
- `.agents/skills/planning/references/dev-doc.md` — `skill `references/``
- `.agents/skills/pr-lifecycle/SKILL.md` — the `## Workflow` table, presets and step contract
- `/plan-ft-dev` — create a new changeset
- `/update-context-docs` — progress updates during implementation
