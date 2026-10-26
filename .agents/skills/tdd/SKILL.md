---
name: tdd
description: "Drive test-first implementation using failing acceptance tests, red/green cycles, bug reproduction, and exploratory green investigations. Use when implementation is underway or the user asks for test-first execution, red-green-refactor work, acceptance-test-first delivery, or a failing-test-based bug fix workflow."
---

# Test-Driven Development (TDD)

This skill guides you through the Test-Driven Development workflow using the strict red-green-refactor cycle.

Use `plan-tdd-one-shot` when the user wants a detailed rollout plan before implementation starts.

**Workflow rows.** The red and green phases run as `## Workflow` rows (`/red`, `/plan-red`,
`/green`, `/green-100`, `/green-attack`) under `.agents/skills/pr-lifecycle/SKILL.md`; where
this skill says *halt*, it means that skill's halt.

## Core TDD Principles

**CRITICAL**: Never skip, remove, or workaround tests that are hard to overcome. If a test is challenging:
1. Stop and analyze why the test is difficult
2. If quality code cannot get past it, halt the row: the challenge goes in Result, the options in
   the summary's *Needs you*
3. The developer's answer arrives on re-invocation — act on it then
4. Never make tests pass through false positives or negatives

## TDD Cycle

Use this skill as the single entry point for TDD execution. It replaces the narrower red/green execution prompts as a standalone skill.

The `test-writer` and `tdd-implementer` behaviours are folded into this skill. On Muse those
subagents still exist (`.muse/agents/`) and remain the preferred way to run the red and green
phases there; elsewhere this skill carries the same behaviour directly.

### 0. Start with the right test level

Before unit-level red/green work, choose the right starting point:

- For a planned feature, begin with failing acceptance tests — the feature preset's Plan and Red rows
  (`/plan-red`, `.agents/commands/plan-red.md`).
- For a reported bug, begin with a failing reproduction test using `.agents/commands/reproduce.md`.
- For a focused behavior change, begin directly with a red test.

### 🔴 Red Phase - Write Failing Tests

**Before any implementation**, write comprehensive failing tests:

1. **Define the public API** through test usage
2. **Write descriptive test names** that explain behavior
3. **Set up clear assertions** for expected outcomes
4. **Verify tests fail** for the right reasons (missing implementation, not bugs)
5. **Write them fluent** — load the `fluent-tests` skill (`.agents/skills/fluent-tests/SKILL.md`)
   first. Mandatory even when the suite you add to is not fluent; leave the suite's other tests
   alone. Bar and scoring: `.agents/skills/testing/references/fluent-style.md`

**Run tests** to confirm they fail as expected.

**Purpose**: Capture requirements and desired behavior before coding begins.

### 🟢 Green Phase - Make Tests Pass

**Verify red first — run the tests.** If nothing is red, the green phase does not run: halt the
row and record whether the tests are missing (the Red row is incomplete), already passing (green is
done — validate, don't re-implement), or failing to run (fix the harness). Never invent
implementation work to justify continuing.

**And verify each red test is red for the right reason** — an assertion against missing
implementation or a planning stub firing, not an environment failure (unbuilt workspace deps,
missing `protogen`/WASM artifacts after a branch switch, ports, stale caches). Fix the environment
and re-run; only what is still red afterwards is green-phase input. See `/green` step 1.

**Implement minimal code** to make all failing tests pass:

1. Focus on functionality over form
2. Write just enough code to satisfy tests
3. Keep test changes minimal - tests define requirements
4. Avoid over-engineering at this stage

**Run tests** to confirm they all pass.

**If tests are difficult to pass**:
- Do NOT skip the tests
- Do NOT remove assertions
- Do NOT add workarounds or false positives
- Halt the row with the challenge and the options

**Purpose**: Create working implementation with minimal code changes.

**Restructure prerequisite:** (records live in `<package-dir>/docs/{todo,code-issues}/`; the rules in `.agents/skills/deferred-work/`) if the changeset's
`## Prerequisites` names one, it runs **before** any
implementation (`.agents/commands/green.md` step 0.5). Implementing on top of a structure that is
about to move means writing the code twice. The baseline is *green except this changeset's own
planned red tests* — those are listed as known-red; anything else red is still a stop.

**Stack branch:** before implementing, follow `.agents/commands/green.md` step 0 — run
`/pr-stack-rebase`, then halt the row ⛔ if required ancestor functionality is still a stub.

**The goal is the full planned scope.** If something cannot be finished, that is a deferral, not a
scope decision you make alone: it needs a named blocker, refuted alternatives and the developer's
recorded consent — asked for by halting the row with *finish it / defer with blocker X / re-plan*, and
recorded from their answer on re-invocation — written to a `<package-dir>/docs/todo/` file (`deferred-work/SKILL.md`,
`/green` step 3.5). "It is hard" and "the session is long" are not blockers. Silence is not
deferral.

### 🔬 Green-Attack Phase - Explore without forcing passage

Use an exploratory implementation pass when the right fix is still unclear.

- Run the failing tests.
- Investigate multiple implementation approaches.
- Add diagnostics and logs if needed.
- Keep tests intact and do not skip them.
- Treat learning and narrowing the solution as success, even if tests still fail at the end.

Use `.agents/commands/green-attack.md` as the source workflow when you need a deeper exploratory pass.

**Stack branch:** the same pre-run as `/green` — rebase first, then the ancestor-functionality gate.

### 🔵 Refactor Phase - Clean Up Code

**Improve code quality** while keeping all tests green:

1. Add proper Python typing (mypy strict) and remove `any` types
2. Follow clean code principles - small methods, reduced nesting
3. Extract duplicated logic
4. Ensure production readiness

**Run tests** after each refactoring to ensure they remain green.

**Purpose**: Polish implementation while maintaining test coverage and functionality.

## Phase Transitions

Follow this strict flow:

- **Red → Green**: Only proceed when you have comprehensive failing tests
- **Green → Refactor**: Only proceed when all tests are passing
- **Refactor → Red**: Start next feature cycle with new failing tests

**Never skip phases.** Each phase has a specific purpose in ensuring code quality.

## Testing Standards

### Test Quality Requirements

- Tests must be **deterministic** - no random values, no timing dependencies
- Tests must be **isolated** - each test runs independently
- Tests must be **readable** - use BDD-style descriptions
- Tests must **validate real behavior** - no false positives

### What to Test

**Red Phase checklist**:
- [ ] Happy path scenarios
- [ ] Edge cases and boundary conditions
- [ ] Error conditions and validation
- [ ] Integration points if applicable

### Test File Naming

- Unit tests: `*.test.ts`
- Integration tests: `*.it.test.ts`
- E2E tests: `*.e2e.test.ts`

## Handling Difficult Tests

When you encounter a test that's challenging to make pass:

### Step 1: Stop and Analyze
- What makes this test difficult?
- Is the API design problematic?
- Are there missing dependencies?
- Is the test exposing a design flaw?

### Step 2: Halt the Row With the Analysis
When quality code cannot get past it, halt the row ⛔. Result names the test and the core issue; the
summary's *Needs you* explains clearly:
- Which test is challenging
- Why it's difficult
- What the core issue is
- Potential approaches you've considered

### Step 3: Put the Decision as Options
Phrase each decision as options the developer answers on re-invocation:
- "a) redesign the API to make this testable, b) …"
- "a) add a dependency injection point here, b) …"
- "a) split this into smaller units, b) …"

### Step 4: Never Compromise
**Do NOT**:
- Skip the test "temporarily"
- Remove assertions to make it pass
- Add `Any` types to bypass mypy
- Use ranges/tolerances unless testing uncontrollable factors
- Add test-only code branches in production code
- Mock away the actual behavior being tested

## Running Tests

From repository root:
- `uv run pytest -q` - Run all tests (unit, integration, e2e)
- `uv run pytest -q:unit` - Run unit tests only
- `uv run pytest -q:it` - Run integration tests only
- `uv run pytest -q:e2e` - Run e2e tests only

**Run tests frequently** during each phase to verify state.

## Source Workflows

Use these repo prompts for additional detail when needed:

- `.agents/skills/pr-lifecycle/SKILL.md` for the `## Workflow` table, its presets and the step contract
- `.agents/skills/plan-tdd-one-shot/SKILL.md` for detailed one-shot TDD planning
- `.agents/commands/red.md` for strict red-phase expectations
- `.agents/commands/green.md` for quality-first green implementation
- `.agents/commands/green-attack.md` for exploratory implementation
- `.agents/commands/reproduce.md` for bug reproduction via failing tests

## References

Read these only when needed:

- `references/tdd.md`
- `references/testing-practices.md`
- `references/unit-test.md`
- `references/integration-test.md`
- `references/prod-test.md`
- `../deferred-work/SKILL.md` — when the green phase cannot finish planned scope, or the changeset
  names a restructure prerequisite

## Quality Gates

Before closing the phase's row ✅:

**Red Phase**:
- ✓ All new tests fail initially
- ✓ Tests fail for the right reasons
- ✓ Test names clearly describe behavior
- ✓ Edge cases are covered

**Green Phase**:
- ✓ All tests pass
- ✓ No tests were skipped or removed
- ✓ No workarounds or false positives
- ✓ Implementation is minimal and focused
- ✓ Restructure prerequisite executed first, in its own commit (or the changeset named none)
- ✓ Full planned scope delivered — anything deferred has a `<package-dir>/docs/todo/` file with a named
  blocker and recorded consent, and resolved records are deleted

**Refactor Phase**:
- ✓ All tests remain green
- ✓ Code quality improved
- ✓ Python types are proper (mypy strict)
- ✓ Production ready

## Example Workflow

**Starting a new feature:**

1. **Red Phase**:
```python
describe('UserService', () => {
  it('should create user with valid email', () => {
    const service = new UserService();
    const user = service.create('test@<service-host>');
    expect(user.email).toBe('test@<service-host>');
  });

  it('should throw error for invalid email', () => {
    const service = new UserService();
    expect(() => service.create('invalid')).toThrow('Invalid email');
  });
});
```
Run tests → they fail (UserService doesn't exist)

2. **Green Phase**:
```python
class UserService {
  create(email: string) {
    if (!email.includes('@')) throw new Error('Invalid email');
    return { email };
  }
}
```
Run tests → they pass

3. **Refactor Phase**:
```python
class UserService {
  create(email: string): User {
    this.validateEmail(email);
    return { email };
  }

  private validateEmail(email: string): void {
    if (!this.isValidEmail(email)) {
      throw new Error('Invalid email');
    }
  }

  private isValidEmail(email: string): boolean {
    return email.includes('@');
  }
}
```
Run tests → they still pass, code is cleaner

## Benefits

- **Comprehensive coverage** by design
- **Clear requirements** through failing tests
- **Regression prevention** with continuous validation
- **Maintainable codebase** through structured refactoring
- **Living documentation** via executable test specifications
- **Design feedback** - difficult tests reveal design issues early

## Summary

When using TDD:
1. Always write tests first (Red)
2. Implement minimal code to pass (Green)
3. Refactor while keeping tests green (Refactor)
4. Never skip or compromise on difficult tests
5. Halt the row with options when a challenge cannot be met with quality code
6. Run tests frequently to verify phase completion
