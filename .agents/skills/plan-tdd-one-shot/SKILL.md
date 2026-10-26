---
name: plan-tdd-one-shot
description: "Plan a full one-shot TDD delivery workflow before implementation. Use when the user wants a detailed TDD rollout plan, acceptance-test-first milestones, changeset [wf] workflow rows, or production-readiness validation steps without starting code changes."
---

# Plan TDD One Shot

Create the planning artifacts and execution checklist before coding starts.

Use `tdd` for implementation-time red/green/refactor work.
Use `planning` when the user wants non-TDD planning or broader product and technical planning.

## Workflow

1. Clarify the change.
Ask only the minimum questions needed to understand scope, affected areas, constraints, and whether this is new behavior or a change to existing behavior.

2. Create or update product documentation first.
Use `docs/<area>/` and follow the repo PRD and feature-doc conventions.

For requirement changes, create or update a PRD in `docs/<area>/1-WIP/`.
Capture summary, background, affected features, high-level requirements, and success criteria.

3. When the flow reaches collaborative planning, move into Plan mode.
**On Muse**: invoke `plan mode` with `target_mode_id: "plan"`. **On other harnesses**: ask the
user to switch (in Claude Code, `/plan`) — do not assume you can switch modes yourself.

If the user switches, use Plan mode to discuss technical options, trade-offs, milestones, and the changeset structure.
If the user stays in the current mode, continue planning in-thread instead of blocking.

4. Create the technical delta: start the changeset per `.agents/skills/pr-lifecycle/SKILL.md`
§ *Start a changeset*, with the planning row closed ✅ — the `[wf]` rows are the order the work runs
in; nothing else in the plan sequences it. Beyond the skill's list, it carries:
- affected packages
- implementation milestones
- acceptance test outline
- technical decisions and constraints
- risks and mitigations
- a granular TODO checklist — nested under the `[wf]` row that does each item (milestones and
  acceptance tests under Green; wrap obligations and the optional `/pr-wrap` steps under Wrap), the
  only checkboxes in the changeset

If planning happened in Plan mode, include the planning discussion **after** `## Initial Discovery`
(that section stays first after the header).

**On Muse**, deliver the finished plan through the `planning workflow` tool — it is how a Plan-mode
session hands its plan over to be written — never as a plain-text message. On other harnesses,
present it inline.

5. Expand the plan into discrete TODOs.
Do not leave the plan as a few broad phases.
Break it into actionable steps covering acceptance tests, the red/green loop, documentation updates and validation — the detail of the `## Workflow` rows.

Use [one-shot-plan-template.md](references/one-shot-plan-template.md) for the required TODO structure.

6. Report instead of gating.
The plan must require acceptance tests to be created and run before implementation. It carries **no**
review checkpoints: each step closes its own row and ends with the step summary
(the `pr-lifecycle` skill § *Summary*), whose **Decided without review** block shows what a checkpoint used to —
the acceptance tests written, what shipped and the validation results. What genuinely needs the
developer halts the row ⛔ (the `pr-lifecycle` skill § *Halts*). Who advances the rows — the developer, `/next`
or `/yolo` — is the developer's choice, not the plan's.

7. Fix the documentation wrap point in the plan.
Wrapping happens **at the moment the PR is set ready for review** — not while it stays a draft (a
draft's changeset belongs in `docs/<area>/1-WIP/` where the next session picks it up), and not deferred
to after merge (which would have reviewers reading a delta-shaped changeset instead of the docs the
change produced). The plan's TODO must say so:

- [ ] If the PR is going up for review and all criteria are met: wrap changeset/PRD into feature docs
  - Add the changelog entry, then delete the source from `docs/<area>/1-WIP/`
- [ ] If not all complete, or the PR stays a draft: keep changeset/PRD in `docs/<area>/1-WIP/`

In a stack, ready and wrap **bottom-up**, so each predecessor's docs leave `1-WIP` before its
successors'.

8. Treat production-readiness validation as part of the plan, not optional cleanup.
Include:
- `/validate-changes`
- `/validate-tests`
- `/validate-prod-ready`
- `/analyze-clean-code`
- final `/validate-changes`
- `uv run ruff check src tests`
- `uv run pytest -q` — every affected workspace
- final `uv run pytest -q` — every affected workspace

## Output Standard

Produce:
- a product doc or PRD if the change needs one
- a changeset and its initial-discovery companion (§ *Start a changeset*), with granular TODOs
- explicit acceptance criteria
- explicit commands for test and validation steps

## Guardrails

- Keep planning and execution separate: this skill plans the work, `tdd` executes it.
- Do not collapse mandatory validation into a single generic QA step.
- Do not skip the separate step to run new acceptance tests and verify they fail.
- Do not plan review checkpoints; the step summaries replace them.
- Prefer repo commands from `README.md` over legacy command names when they differ.

## Source Material

Use these as source workflows when needed:

- `.agents/skills/planning/SKILL.md`
- `.agents/skills/pr-lifecycle/SKILL.md` — presets, step contract, halts, summary
- `.agents/skills/pr-lifecycle/references/initial-discovery.md`
- `.agents/skills/tdd/SKILL.md`
- `references/one-shot-plan-template.md`
