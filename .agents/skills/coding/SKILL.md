---
name: coding
description: Validate whether implementation work is safe, production-ready, and aligned with test and code quality expectations. Use when development is mostly complete, before PR creation, or when the user asks for readiness checks, risk analysis, or code-quality review.
---

# Coding

Check whether the current implementation is ready to move forward.

## Workflow

1. Validate changes against actual code.
Compare the implementation with the expected scope, review risks, and confirm the affected packages build and behave as expected.

2. Validate production readiness.
Look for unsafe fallbacks, leftover mocks, unresolved TODOs, and anything that would make the change unsafe outside tests.

3. Analyze code quality.
Review complexity, duplication, deep nesting, and readability issues that should be addressed before handoff.

4. Summarize findings clearly.
Prioritize real risks and call out residual gaps if the work is not fully ready.

## Use These Source Prompts

- `.agents/commands/validate-changes.md`
- `.agents/commands/validate-prod-ready.md`
- `.agents/commands/analyze-clean-code.md`

## References

Read these only when needed:

- `references/coding-practices.md`
- `references/general-code-style.md`
- `references/python-code-style.md`

## Guardrails

- Prefer concrete findings over broad commentary.
- Block on correctness and safety issues before polish.
