---
description: TDD Red Phase - Write failing tests before implementation
---
## Red Phase - Write Failing Tests First

This command guides creation of comprehensive failing tests as the first step in TDD.

**For complete TDD workflow, see `.agents/skills/tdd/references/tdd.md` rule.**
**For testing standards, see `.agents/skills/tdd/references/testing-practices.md` rule.**
**Every test is fluent** — load the `fluent-tests` skill (`.agents/skills/fluent-tests/SKILL.md`)
before writing; the bar is `.agents/skills/testing/references/fluent-style.md`.

## Workflow row

This command follows the step contract in `.agents/skills/pr-lifecycle/SKILL.md` when a
changeset resolves. It runs a **Red** `[wf]` row whose command is `/red` (a developer
swap for `/plan-red`'s Red row, or a rebalance's replacement tests). It records `<n> failing @ <sha>`
in **Result**, and halts the row ⛔ when nothing is red or the code does not compile against the
tests' imports for a reason outside this change. With no changeset — an ad-hoc red step — there is
no row, and the turn ends with the output below.

## Prerequisites

- This step is about writing tests FIRST, before any implementation exists
- Tests will initially fail (no implementation exists yet)
- Tests clearly define expected behavior and API design

## Workflow

### 1. Write Comprehensive Failing Tests

Capture all desired behavior and edge cases:
- Main functionality tests
- Edge case tests
- Error scenario tests
- API boundary tests

### 1.0 Write Them Fluent — Mandatory

Load the `fluent-tests` skill and the reference for the framework you are writing in, then write
every test to it: visible Given/When/Then, a behaviour-sentence name, builders for data, a matcher
or driver that states intent. **This holds when the suite you add to is not fluent** — add the
builder, matcher or driver your test needs instead of copying the suite's raw setup, and leave the
suite's other tests as they are (rewriting them is a migration, its own PR —
`.agents/skills/testing/references/fluent-style.md` § *Migrating a suite*). Every test this step
writes or edits scores **≥ 8** on that file's rubric.

### 1.1 Prefer Strengthening Existing Tests

You do **not** need to create new tests/files for every bug.

- Prefer updating an existing relevant test when one already covers the flow
- Add stricter assertions to expose the bug more precisely
- Create a new test only when no existing test can represent the scenario cleanly
- A test you strengthen is brought to fluent as part of the edit — that test only

### 2. Implement Tests (Not Skeletons)

**CRITICAL**: Tests should be fully implemented, not placeholders:
- Complete test setup
- Full test execution
- Proper assertions
- Clear test names

Ideal test needs no changes when going green.

When reproducing a bug in an existing test, tighten it with additional assertions such as:
- event ordering assertions
- exact payload/argument assertions
- state transition assertions (before/after operation)
- invariants that must remain stable across repeated operations

### 3. Define Public API Through Tests

Tests show how feature should be called:
- Function signatures
- Parameter types
- Return values
- Error handling

### 4. Verify Tests Fail Correctly

```bash
cd packages/package-name
uv run pytest -q
```

Tests should fail for right reasons:
- ✅ Missing implementation
- ❌ NOT test bugs

### 5. Commit, close the row, report

Commit the failing tests (with the changeset when one resolves), close the **Red** row, and end the
turn with the output below. It is the summary's **Done** / **Decided without review** content — no
review follows it.

## Goals

1. ✅ Write comprehensive failing tests
2. ✅ Tests fully implemented (new or updated existing tests)
3. ✅ Define public API through test usage
4. ✅ Establish clear test structure
5. ✅ Verify tests fail for right reasons
6. ✅ Code compiles (imports work)

## What NOT to Do

- ❌ Don't write implementation code yet
- ❌ Don't make tests pass with minimal stubs
- ❌ Don't skip edge cases or error scenarios
- ❌ Don't write vague or broad tests
- ❌ **Don't write tests with conditional logic**
- ❌ **Don't add try/catch blocks or fallbacks**
- ❌ **Don't write placeholder tests**
- ❌ **Don't copy a non-fluent suite's style** into a new test, and don't rewrite its other tests here

**Follow `.agents/skills/tdd/references/testing-practices.md`** - Write reliable, deterministic tests.

## Keep It Clean

**CRITICAL**: Never put "red phase" or "green phase" in:
- Code comments
- Test descriptions
- Production code

Keep TDD phases in chat context only.

## Output Format

```markdown
## 🔴 Red Phase Complete - Failing Tests Ready

### Tests Created
- `test-file.test.ts` - X tests

### Test Coverage
**Main Functionality:**
- [x] Test: should do main thing
- [x] Test: should handle input X

**Edge Cases:**
- [x] Test: should handle empty input
- [x] Test: should handle null values

**Error Scenarios:**
- [x] Test: should throw on invalid input
- [x] Test: should fail gracefully on error

### API Definition (via tests)
```python
# How the feature will be called (defined by tests)
def classify_motion(track: Track, window: list[ObjectPoints]) -> Motion: ...
```

### Test Results
```bash
cd packages/package-name && uv run pytest -q
```

**Output:**
```
❌ All tests failing (expected)
- Missing implementation for classify_motion
- No error handling implemented
```

### Readiness Check
- ✅ All tests fully implemented
- ✅ Code compiles
- ✅ Imports work
- ✅ Tests fail for right reasons (missing implementation)
- ✅ No test bugs detected
- ✅ Fluent: every written or edited test scores ≥ 8 (lowest: <n>/10)

**Row Red**: ✅ <n> failing @ <sha>  (as a row, inside the skill's summary)
```

## Update Documentation

**If changeset exists**: Add to "Refactoring Needed":
```markdown
### From `/red` (TDD Red Phase)
- [ ] Test helper function needed for repeated setup
- [ ] Test data builder would improve readability
- [ ] Mock factory needed for complex dependencies
```

Focus on test structure issues, not implementation (no production code exists yet).

## Success Criteria

Red phase complete when:
- ✅ All tests fully implemented (not skeletons)
- ✅ Tests comprehensively cover functionality
- ✅ API design clear from test usage
- ✅ Code compiles
- ✅ Tests fail for right reasons
- ✅ No test bugs
- ✅ Every written or edited test is fluent (≥ 8)
- ✅ Committed, and the Red row closed

## Best Practices

✅ **Do:**
- Write comprehensive tests covering all scenarios
- Fully implement tests (not placeholders)
- Define clear API through tests
- Follow `.agents/skills/tdd/references/testing-practices.md` standards
- Verify tests fail correctly

❌ **Don't:**
- Don't write implementation yet
- Don't create skeleton tests
- Don't add conditional test logic
- Don't skip edge cases
- Don't put TDD phase info in code
- Don't create new tests when an existing one can be made strict enough

## Related

**References**: `.agents/skills/tdd/SKILL.md`, `.agents/skills/tdd/references/tdd.md`, `.agents/skills/tdd/references/testing-practices.md`
**Commands**: `/plan-red` (owns the Red row in the presets), `/next`
**Skill**: `code-cleaning` (`.agents/skills/code-cleaning/SKILL.md`) — refactor after green
**On Muse**: the `test-writer` subagent (`.muse/agents/test-writer.md`) writes this phase's tests,
and `refactor` (`.muse/agents/refactor.md`) handles the post-green cleanup
