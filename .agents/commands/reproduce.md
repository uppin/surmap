---
description: Reproduce bugs/issues with failing tests that demonstrate the problem
---
## Reproduce Bug with Failing Test

This command guides the creation of failing tests that reliably reproduce reported bugs or issues.

**For testing best practices and anti-patterns, see `.agents/skills/tdd/references/testing-practices.md` rule.**
**For the bug-fix workflow, see the bugfix preset in `.agents/skills/pr-lifecycle/SKILL.md` § *Presets*.**

## Workflow row

This command follows the step contract in `.agents/skills/pr-lifecycle/SKILL.md` when a
changeset resolves. It runs the bugfix preset's **Red** row (the reproduction test) where its `[wf]` row
names `/reproduce`, and the same procedure is what `/plan-red` Step 8 applies for a Bug Fix. It
records `reproduces @ <sha>` (the failing test and its commit) in **Result**. It halts the row ⛔
when the bug does not reproduce — a test that passes against the reported behaviour has proven
nothing, and the options are *more detail from the reporter*, *a different tier* or *close as not
reproducible*. With no changeset there is no row, and the turn ends with the output below.

The clarification questions under *Prerequisites* gather input before any test is written, so they
stay.

## Prerequisites

Before writing the reproduction test, gather the following information:

1. **Bug description**: What is the expected vs actual behavior?
2. **Steps to reproduce**: How can the bug be triggered?
3. **Affected component/module**: Which part of the codebase has the issue?
4. **Environment/conditions**: Are there specific conditions that trigger the bug?

**CRITICAL**: If any of these details are unclear or missing, **ask the User for clarification** before proceeding.

## Test Suite Selection

### Finding Existing Test Suite

1. **Search for related test files** in the affected package:
   - Unit tests: `*.test.ts`
   - Integration tests: `*.it.test.ts`
   - E2E tests: `*.e2e.test.ts`

2. **Match by scope**:
   - If bug affects a specific component, add test to that component's test suite
   - If bug affects module integration, add to integration test suite
   - If bug affects user workflow, add to E2E test suite

3. **Prefer existing test suites** that already cover the affected code area

### Creating New Test Suite (Rare Cases)

Only create a new test suite if:
- No existing test file covers the affected component/module
- Bug affects a completely untested area of code
- Existing test structure doesn't logically fit the bug scenario

**When creating new test suite:**
- Follow naming convention: `ComponentName.test.ts` (unit), `feature.it.test.ts` (integration), or `workflow.e2e.test.ts` (E2E)
- Include proper test setup and teardown
- Structure test suite for future test additions

## How to Run the Failing Test

Tests should run via `uv run pytest -q` in the local package and appending the test suite to the command:

```bash
cd packages/my-package && uv run pytest -q
```

The test should fail, confirming the bug is reproduced.

## Goals of Bug Reproduction

1. **Write a failing test** that reliably demonstrates the bug
2. **Test should be complete** and fully implemented - no placeholders or skeleton tests
3. **Isolate the bug** - test should focus on the specific issue without testing unrelated functionality
4. **Reproduce consistently** - test should fail reliably every time it runs
5. **Use realistic data** - test inputs should match real-world scenarios that trigger the bug
6. **Verify test fails** for the right reasons (the actual bug, not test bugs)
7. **Report the failing test results** in the summary to show the bug is reproduced
8. **CRITICAL**: Code should compile and any imports should work
9. **KEEP IT CLEAN**: Don't add comments like "reproducing bug" or "this will fail until fixed" in the code

## What NOT to Do

- Don't fix the bug yet - only write the test that demonstrates it
- Don't make tests pass by adding workarounds
- Don't write tests that are too broad - focus on the specific bug
- Don't skip proper setup/teardown that might hide the bug
- **Don't write tests with conditional logic or multiple code paths**
- **Don't add try/catch blocks or fallback assertions**
- **Don't write vague tests that might pass or fail randomly**
- **Don't guess at details** - ask the User if anything is unclear

**CRITICAL**: Follow [testing-practices.mdc](/.agents/skills/tdd/references/testing-practices.md) rule - write reliable, deterministic tests without workarounds.

**The reproduction is fluent** — load the `fluent-tests` skill; the test names the defect's
behaviour as a sentence and scores ≥ 8 (`.agents/skills/testing/references/fluent-style.md`), even
when the suite it joins does not. A reproduction tightened into an existing test brings that one test
to fluent; its neighbours stay as they are.

## Output

1. **Present the test location**: Show which test suite the test was added to (or created)
2. **Present the failing test**: Show the test code that reproduces the bug
3. **Present the test results**: Run the test and show the failure output
4. **Confirm bug reproduction**: Explain how the test demonstrates the reported issue
5. **Close the row**: commit the test (with the changeset when one resolves), record the evidence, and name the next `[wf]` row

## Workflow Example

```
User: "The map viewer crashes when loading pages with special characters"

Assistant (clarifying):
- Which package/component is affected? (e.g., surmap)
- What specific characters cause the crash? (e.g., emoji, unicode, Chinese characters)
- Does it happen during initial load or when navigating between pages?

User: "It's in surmap, happens with emoji in page text, crashes on initial load"

Assistant (actions):
1. Searches for existing test suite: finds MapView.test.ts
2. Adds test: "should handle emoji characters in page text without crashing"
3. Runs test: cd mapping-pipeline/mapping-pipeline && uv run pytest -q
4. Test fails with expected error (crash/exception)
5. Commits it, closes the Red row ✅ "reproduces @ <sha>", and the summary names the next row
```

This workflow demonstrates gathering clarification, finding the appropriate test suite, writing the failing test, and recording the reproduction as the row's evidence.
