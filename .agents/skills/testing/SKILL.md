---
name: testing
description: Fix failing tests, validate test quality, create or review acceptance tests, and decide whether tests should be repaired or rarely skipped. Use when tests are failing, flaky, low-quality, under-specified, or when the user asks for help getting the test suite back into shape.
---

# Testing

Restore test health without compromising production behavior.

## The shape tests are restored toward

The target balance is a **rhombus**: very few e2e tests (unique flows, success scenarios only), the
**majority** as fast in-memory integration tests that use real implementations for code we own and
in-memory doubles only at ports to code we do not, and a few unit tests for functions that need no
doubles at all. The tier is decided by one question — *what would a double have to stand in for?*

Full doctrine: [docs/architecture.md](../../../docs/architecture.md#test-balance--the-rhombus).
The architecture that makes the middle band possible:
[hexagon-testable-architecture](../hexagon-testable-architecture/SKILL.md).

When a test is failing *because* it sits at the wrong tier — an e2e test asserting an error branch, a
unit test held together by mocks of our own modules — fixing the tier is the fix.
`/plan-test-rebalance` plans that move across a package; `/green-100` enforces the shape on one
changeset.

The `bug-fixer` behaviour belongs here. On Muse the `bug-fixer` subagent
(`.muse/agents/bug-fixer.md`) still exists and remains the preferred way to apply fixes there;
elsewhere this skill carries the same behaviour directly.

## Workflow

1. Determine scope.
Run the relevant tests, identify failing files and test names, and confirm whether this is a suite-wide issue or a localized break.

2. Diagnose the root cause.
Separate production bugs, test infrastructure failures, and bad tests. Prefer fixing the real issue over patching the symptom.

3. Use focused debugging when needed.
Run one failing test at a time with extra logging when the failure is hard to understand.

4. Validate test quality.
Check determinism, isolation, assertion quality, and anti-patterns before declaring the suite healthy,
and score readability against the fluent rubric
([references/fluent-style.md](references/fluent-style.md)).

## Fluent style

Every test written or rewritten is fluent — the [`fluent-tests`](../fluent-tests/SKILL.md) skill is
the how, [references/fluent-style.md](references/fluent-style.md) the repo's contract: the mandate
(new tests are fluent even in a legacy suite), the 10-check score and its thresholds, the
`non-fluent-tests` code issue for a legacy suite below the bar, and the two ways a suite is migrated
without holding up the work that found it (a ground-softening node, the stack's sweep node).

5. Skip only as a last resort.
If a test truly must be skipped, document why, capture the follow-up work clearly, and avoid normalizing the skip.

## Use These Source Prompts

- `.agents/commands/fix-tests.md`
- `.agents/commands/fix-tests-focused.md`
- `.agents/commands/test-acceptance.md`
- `.agents/commands/validate-tests.md`
- `.agents/commands/skip-tests.md`

## Guardrails

- Do not add test-only production branches.
- Do not accept flaky behavior as good enough.
- Prefer removing debug scaffolding before finishing.
- A test repaired by rewriting it comes out fluent; its untouched neighbours stay as they are.
