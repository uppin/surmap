---
name: planning
description: Plan product and technical work before implementation by creating or updating PRDs, changesets, and formal planning docs. Use when the user wants feature planning, a requirements change documented, or planning material turned into formal context docs. Use `tdd` instead when the request is specifically for a one-shot TDD delivery plan.
---

# Planning

Create the planning artifacts before coding begins.

## Workflow

1. Clarify the request.
Ask only the minimum concrete questions needed to understand scope, affected areas, constraints, and whether this is new work or a change.

2. Create or update product documentation first.
Use `docs/<area>/` and the current repo conventions for PRDs, features, and requirement changes.

3. Ask the user to switch to Plan mode if they want collaborative planning there.
Do not assume you can switch modes yourself. If they stay in the current mode, continue planning in-thread.

4. Cross-check the deferred-work records (planning-phase **Step 2b**) — **mandatory**.
Scan `<package-dir>/docs/todo/` and every in-scope `<package-dir>/docs/code-issues/` for items sitting in this
change's path, give each a verdict, and write them into the changeset's `## Prerequisites`. Where
the fix is a restructure, that section carries a **Restructure Prerequisite** block `/green` executes
before any implementation. Load the `deferred-work` skill
(`.agents/skills/deferred-work/SKILL.md`); finding one of these during `/green` is too late.

5. Resolve the architecture diagram.
For each in-scope package, check its own `README.md` and then its group-level `{group}/AGENTS.md`
for a declared **architecture diagram** (`references/planning-phase.md` Step 2). If one exists and
the change alters the architecture it depicts, the changeset's `## Technical Changes` carries an
`### Architecture Diagram` block specifying the update (`.agents/skills/pr-lifecycle/references/changeset.md` §8). The
diagram file itself is never edited during planning or development — `/wrap-context-docs` applies
the update at wrap time.

6. Start the changeset per `.agents/skills/pr-lifecycle/SKILL.md` § *Start a changeset*.
Keep implementation tracking in the changeset workflow, and do not update
`{common,common-testing,mapping-pipeline,onboard-detection,surmap,packages}/*/docs/` during planning. Close
the planning row ✅ with its evidence; the planner sets the order, and no step command names what
runs after it.

7. Write the execution checklist.
Break the work into discrete TODOs covering acceptance tests, TDD execution, validation and
documentation wrap-up — the detail of the `[wf]` rows. No TODO is a review gate: what a review
would have shown is reported in each step's summary (`.agents/skills/pr-lifecycle/SKILL.md` § *Summary*).

## Use These Source Prompts

- `.agents/commands/plan-ft.md`
- `.agents/commands/plan-ft-dev.md`
- `.agents/commands/requirements-change.md`
- `.agents/commands/plan-to-context.md`
- `.agents/commands/plan-pr-stack.md` (when the work spans a **stack of dependent PRs** planned ahead — alternative to `/plan-red`)
- `.agents/commands/analyze-code-issues.md` (when an in-scope package has no `<package-dir>/docs/code-issues/` record yet and the change lands in code the analyzers would have something to say about)

## References

Read these only when needed:

- `.agents/skills/pr-lifecycle/SKILL.md` — the `## Workflow` table, presets, step contract, halts, runners
- `references/feature-doc.md`
- `.agents/skills/pr-lifecycle/references/prd.md`
- `references/planning-phase.md`
- `.agents/skills/pr-lifecycle/references/changeset.md`
- `.agents/skills/pr-lifecycle/references/initial-discovery.md`
- `references/dev-doc.md`
- `references/repo-structure.md`
- `../deferred-work/SKILL.md` — the TODO and code-issue records Step 2b reads

## Guardrails

- Prefer a single coherent plan over scattered notes.
- Keep product intent and technical delta separate.
- Use `docs/<area>/1-WIP/` for in-progress technical docs.
- Persist every Explore / Discovery pass in `{changeset-slug}-initial-discovery.md`; wrap deletes it.
- Leave stable package docs for the wrap/finalization step (`<package-dir>/docs/code-issues/` is the exception —
  `/analyze-code-issues` writes it directly).
- The plan's scope is the deliverable. Never plan a gap in as a TODO; a TODO records something that
  turned out impossible, with a named blocker and the developer's consent — given as their answer to
  a ⛔ halt of the row (`.agents/skills/pr-lifecycle/SKILL.md` § *Halts*).
