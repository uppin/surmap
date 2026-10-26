---
name: tech-stack
description: Understand SurMap's implementation stack, package rules, and native/optional-dependency conventions before making architecture or tooling decisions. Use when the user asks about stack choices, framework constraints, package conventions, or technology-specific implementation patterns.
---

# Tech Stack

Use this skill to ground technical decisions in SurMap's stack and conventions.

## Workflow

1. Identify which layer is relevant.
Decide whether the question is about general stack choices, package conventions, or native/optional dependencies (e.g. RTAB-Map).

2. Read only the needed references.
Do not load all reference material unless the task spans multiple technology areas.

3. Apply the conventions to the current decision.
Use the references to inform architecture choices, dependency decisions, package structure, and implementation patterns.

## References

Read these only when needed:

- `references/tech-stack.md` — the SurMap stack and where each decision is recorded
- `references/package-rules.md` — package, dependency and script rules (`pyproject.toml`)
- `references/native-package.md` — native / system-provided dependencies (RTAB-Map pattern)
