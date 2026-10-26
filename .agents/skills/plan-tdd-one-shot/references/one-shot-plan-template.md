# One-Shot Plan Template

Use this reference when the user wants a detailed execution-ready TDD plan rather than a lightweight outline.

## Workflow

The changeset the plan produces opens with its `[wf]` rows under `## Workflow` — the preset for its `(Type, Behaviour)`
pair from `.agents/skills/pr-lifecycle/SKILL.md` § *Presets*, planning row closed ✅. The
TODOs below are the detail of those rows: Red (acceptance and red tests), Green (the cycle), Wrap
(validation, lint, docs). In the changeset they are written as TODOs nested under those rows — the
only checkboxes it carries. They carry no review items.

## Required TODOs

The plan should use discrete TODOs similar to:

```yaml
todos:
  - id: planning-discovery
    content: "Record initial discovery (docs/<area>/1-WIP/{slug}-initial-discovery.md)"
    status: completed
  - id: planning-prd
    content: "Create/update PRD documentation"
    status: completed
  - id: planning-changeset
    content: "Create dev doc + changeset (opens with ## Initial Discovery)"
    status: in_progress

  - id: dev-acceptance-tests
    content: "Create failing acceptance tests"
    status: pending
  - id: dev-run-acceptance-tests
    content: "Run the newly created acceptance tests and verify they fail"
    status: pending
  - id: dev-tdd-red
    content: "TDD Red - Write failing unit/integration tests"
    status: pending
  - id: dev-tdd-green
    content: "TDD Green - Implement with quality code"
    status: pending
  - id: dev-update-docs
    content: "Update documentation with progress"
    status: pending
  - id: dev-tdd-cycle-repeat
    content: "Repeat Red -> Green -> Update cycle until feature complete"
    status: pending
  - id: dev-run-all-tests
    content: "Run all tests (uv run pytest -q
    status: pending

  - id: prod-validate-changes
    content: "Validate changes (/validate-changes)"
    status: pending
  - id: prod-refactor-changes
    content: "Refactor issues from change validation"
    status: pending
  - id: prod-validate-tests
    content: "Validate tests (/validate-tests)"
    status: pending
  - id: prod-refactor-tests
    content: "Refactor test issues"
    status: pending
  - id: prod-validate-ready
    content: "Validate production readiness (/validate-prod-ready)"
    status: pending
  - id: prod-refactor-ready
    content: "Refactor production readiness issues"
    status: pending
  - id: prod-analyze-quality
    content: "Analyze code quality (/analyze-clean-code)"
    status: pending
  - id: prod-refactor-quality
    content: "Refactor code quality issues"
    status: pending
  - id: prod-final-validation
    content: "Final validation (/validate-changes)"
    status: pending
  - id: prod-lint-typecheck
    content: "Run uv run ruff check src tests, uv run pytest -q
    status: pending
  - id: prod-wrap-docs
    content: "Wrap documentation (/wrap-context-docs) — when the PR is set ready for review; also deletes {slug}-initial-discovery.md"
    status: pending
```

## What the Step Summaries Report

There are no review checkpoints. Each step's summary carries, under **Decided without review**, what
a checkpoint used to show:

1. The Red row: test titles, locations, a short coverage summary, and confirmation that the new tests fail for the right reason.
2. The Green and Wrap rows: what shipped, which acceptance tests now pass, key implementation decisions, and `/validate-changes` results.
3. The last row: completion status. Its **Next row** line says every row is done; what follows is the developer's call.

## Body Structure

The markdown body of the plan should usually include:

```md
# Feature Implementation Plan: [Feature Name]

## Overview

## Workflow

The preset's `[wf]` rows, planning row ✅ (the `pr-lifecycle` skill § *Presets*).

## Initial Discovery

Companion: `docs/<area>/1-WIP/{slug}-initial-discovery.md` (combined conclusions at the top; each Explore pass at the tail). The changeset's first content section after the header links here.

## Affected Packages

## Implementation Strategy

## Technical Decisions

## Risks and Mitigations

## Acceptance Criteria
```

## Planning Notes

- Keep product intent in `docs/<area>/` and technical execution in `docs/<area>/1-WIP/`.
- Persist every Explore / Discovery pass in `{slug}-initial-discovery.md` next to the changeset. Wrap deletes it.
- If planning happens in Plan mode, preserve the discussion in the changeset.
- Prefer repo commands from `README.md` when command names have drifted from legacy prompts.
