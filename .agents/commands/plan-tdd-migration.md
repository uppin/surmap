---
description: Plan and execute code migrations (refactoring, architecture changes) without changing features, using collaborative planning in Plan mode to create comprehensive changeset
---
# Plan TDD Migration - Code Migration Without Feature Changes

This command creates a complete, actionable implementation plan for code migrations, refactoring, and architecture changes that **do not modify features**. It focuses on technical improvements while maintaining existing behavior.

**When to Use This Command**:

- Refactoring code without changing features
- Migrating to new architecture patterns
- Updating dependencies or frameworks
- Improving code quality or performance
- Changing implementation without changing behavior

**Prerequisites**:

- User has described the migration/refactoring they want to perform
- Context about affected code/packages
- Clear understanding that **features must remain unchanged**

## Workflow row

This command follows the step contract in `.agents/skills/pr-lifecycle/SKILL.md`. It writes
the changeset's `## Workflow` from the **migration** preset and owns its rows 1–3, run in order,
each closed before the next starts:

| Row | Step | Phase below | Result it records |
|---|---|---|---|
| 1 | Plan | Steps 1–3, Phase 1 | changeset path + per-package baseline counts |
| 2 | Preservation tests | Phase 2 — *Create Behavior Preservation Tests* | `<n> tests, green on State A @ <sha>` |
| 3 | Migrate | Phase 2 — *Implement Migration* through *Run All Tests* | `migrated, <n> preservation tests green @ <sha>` |

Phase 3 below is the detail the Wrap row (`/pr-wrap`) works through. What the former checkpoints
showed goes into the summary under **Decided without review**.

Writing the rows, it nests the plan-derived TODOs under the row that does them: migration milestones
under Migrate; under Wrap the wrap obligations (always `Verification executed — result recorded`)
plus the optional `/pr-wrap` steps this migration needs (`/pr-wrap` § *Workflow row*, *Row TODOs*),
which `/pr-wrap` may extend if scope grows.

**Row TODOs** — seeded under each row when it starts; a re-run resumes at the first open one:

- Plan: `Migration context and per-package baseline recorded` · `Initial discovery written` ·
  `Changeset with State A/B, strategy, preservation plan, rollback` · `Rows and their TODOs written`
- Preservation tests: `Preservation tests written against State A` · `All green on State A` ·
  `Committed with the changeset`
- Migrate: `Migration implemented, preservation tests green throughout` · `Affected packages' full
  suites green` · `Committed with the changeset`

Halts, beyond the skill's: the baseline cannot be established — a broken build or an unexplained failure in a
package being migrated (row 1); a preservation test cannot pass on State A without changing it
(row 2 — the "preserved" behaviour is not what the code does, so the plan is wrong); a preservation
test turns red and cannot be made green without changing its assertion, i.e. the migration changes
behaviour (row 3 — options *fix the migration*, *re-plan as a contract change under `/plan-red`*).

## Execution Flow

### Step 1: Gather Migration Context

**Before switching to Plan mode**, gather information about the migration:

**Actions**:

1. **MANDATORY**: Use the structured-question tool to gather migration details — `AskUserQuestion` on
   Muse, `AskUserQuestion` on Claude Code:
   - **CRITICAL**: ALWAYS use the structured-question tool for requirements gathering
   - DO NOT skip this step or make assumptions about the migration
   - Ask about:
     - What code/architecture needs to change?
     - What is the motivation for this migration?
     - Which packages/components are affected?
     - What technical constraints exist?
     - What is the target architecture/pattern?
     - Are there any breaking changes to internal APIs?
   - Present questions in organized multi-select widgets when appropriate
   - Wait for user responses before proceeding — this is the planning interview, which stays

2. **MANDATORY**: Run tests for affected packages to establish pre-existing baseline:
   ```bash
   # Run tests ONLY for packages being migrated
   cd packages/package-being-migrated
   uv run pytest -q

   # Or if using workspace commands
   uv run pytest -q

   # DO NOT run full test suite - too broad and slow
   # Focus on packages you're planning to refactor
   ```

   **Document results PER AFFECTED PACKAGE**:
   - Package names tested
   - Total test count per package (passing/failing/skipped)
   - Any pre-existing test failures in packages being migrated
   - Test execution time per package
   - Any pre-existing warnings or issues in affected packages

   **Why this matters**:
   - Establishes clean baseline vs. new issues in migration scope
   - Prevents confusion ("did migration break this?")
   - Enables accurate validation later
   - User needs to know about existing issues in areas being modified
   - Critical for behavior preservation verification
   - Faster execution (minutes vs. hours)
   - Clear scope boundaries for migration

3. Document initial migration context:
   - Brief summary of what's changing (code/architecture, not features)
   - Motivation (performance, maintainability, modernization, etc.)
   - Affected packages and components
   - High-level technical approach

**Outcome**: Clear understanding of migration scope and approach + Pre-existing test baseline established

**Example of good baseline documentation for migration**:
```
Pre-existing test baseline (packages being migrated):
- surmap: 123 passing, 3 failing
- surmap: 89 passing, 0 failing ✅

Pre-existing failures in surmap:
1. "should handle malformed input gracefully"
   - Error: TypeError: Cannot read property 'length' of undefined
   - Location: test/parser.test.ts:67
   - Cause: Known bug in legacy code
   - Tracking: Issue #234

2. "should parse large files efficiently"
   - Error: Timeout exceeded (10000ms)
   - Location: test/performance.test.ts:45
   - Cause: Performance issue in old implementation
   - Tracking: Issue #567

3. "should validate input schema correctly"
   - Error: AssertionError: expected true but got false
   - Location: test/validation.test.ts:123
   - Cause: Missing validation logic
   - Tracking: Issue #890

Note: Migration should preserve these test results (failing tests
should still fail for same reasons after migration).
```

### Step 2: Switch to Plan Mode

**After gathering context**, switch to Plan mode for collaborative technical planning:

**On Muse**:
```
Use plan mode tool with target_mode_id: "plan"
Explanation: "Migration context gathered, switching to Plan mode for collaborative technical planning and changeset creation"
```
**On other harnesses**: enter the harness's plan mode (in Claude Code, `/plan`), or ask the user to
switch to it before continuing.

Plan mode is the planning interview, held **before** the changeset is written. Once the
changeset exists, nothing in rows 1–3 waits for the developer except a halt.

**Why Plan Mode**:

- Collaborative discussion of migration strategy
- Multiple refactoring approaches can be explored
- Trade-offs can be discussed before implementation
- User can guide technical decisions
- Design the changeset and milestones together
- Ensure feature behavior preservation strategy is clear

### Step 3: Create Migration Changeset

**In Plan mode**, work collaboratively with the user to:

1. **Discuss migration strategy**: Explore approaches, trade-offs, and implementation steps
2. **Create changeset document**: Use `/plan-ft-dev`, which starts it per the `pr-lifecycle` skill § *Start a changeset* (`.agents/skills/pr-lifecycle/SKILL.md`) with the **migration** preset
3. **CRITICAL — changeset section order**: Include the entire Plan mode discussion/document **after** `## Initial Discovery` — not as the first section.
   - This preserves the collaborative planning context
   - Documents why certain approaches were chosen over others
   - Captures technical decisions and constraints discussed
4. **Document pre-existing test baseline** in changeset:
   - Add "Pre-existing Baseline" section with test results captured in Step 1
   - Document results PER AFFECTED PACKAGE (not full suite)
   - List any pre-existing test failures with details (name, error, cause)
   - List any pre-existing warnings or issues
   - Note that only packages being migrated were tested (scope boundary)
   - Report it in the summary so the developer sees the existing issues
   - Clarify these issues existed BEFORE the migration
   - Critical for behavior preservation: we can verify these same tests pass after migration
5. **Generate detailed TODO list**: Covering all phases from planning through production readiness
6. **Define behavior preservation tests**: Ensure existing features remain unchanged
7. **Deliver the plan** — once the migration implementation plan is fully formed (overview, State
   A/B, affected packages, migration strategy, behavior preservation approach, detailed TODOs,
   success criteria):
   - **On Muse**: you **MUST** call the `planning workflow` tool — it is how a Plan-mode session hands
     its plan over to be written. **Do NOT** finalize the plan as a plain-text message.
   - **On other harnesses**: present the plan inline, in the order given below, as the last step of
     the planning interview.
8. **Close row 1** ✅ with the changeset path and baseline counts, and start row 2.

Generate a detailed TODO list covering the entire migration lifecycle.

## TODO List Structure

The plan should include all phases for migration:

### Phase 1: Planning (Technical Only - No Feature Changes)

#### TODO: Create Migration Changeset

**Command**: `/plan-ft-dev`
**Purpose**: Plan technical migration without changing features

**Actions**:

- [ ] Start the changeset (§ *Start a changeset*, via `/plan-ft-dev`)
- [ ] Include the entire Plan mode MD document **after** `## Initial Discovery` (not as the first section)
  - This preserves the collaborative planning discussion
  - Documents technical decisions, trade-offs, and user input
  - Provides context for why migration approach was chosen
- [ ] Include in changeset:
  - **Affected Packages**: List ALL packages being migrated
  - **State A (Current)**: Describe current code/architecture
  - **State B (Target)**: Describe target code/architecture
  - **Migration Strategy**: Step-by-step technical approach
  - **Behavior Preservation**: How to ensure features don't change
  - **Implementation Milestones**: TODOs nested under the Migrate row
  - **Testing Plan**: How to verify behavior is preserved
  - **Rollback Strategy**: How to revert if issues arise
  - **Technical Decisions**: Document key choices made
  - **Row TODOs**: the `[wf]` rows with their TODOs nested — the only checkboxes in the changeset

**Outcome**: Comprehensive changeset with migration plan and context

**Note**: No feature documentation needed - this is internal refactoring only

### Phase 2: Development (TDD Cycle for Migration)

#### TODO: Create Behavior Preservation Tests

**Row**: 2 — Preservation tests (`/plan-tdd-migration`)
**Purpose**: Write tests that verify existing behavior before migration

**CRITICAL PRINCIPLE**: Write tests against **current implementation** to lock in behavior

**Actions**:

- [ ] Review changeset for list of behaviors to preserve
- [ ] Verify working on correct branch (not master/main)
- [ ] For each component being migrated:
  - [ ] Write tests against **current implementation** (State A)
  - [ ] Tests should capture all existing behavior
  - [ ] Tests should focus on **external behavior**, not implementation details
  - [ ] All tests should **PASS** with current code (verifying State A)
  - [ ] Follow `.agents/skills/tdd/references/testing-practices.md` standards
- [ ] Run tests to confirm all tests pass with current code
- [ ] Commit the tests with the changeset and close row 2 ✅
- [ ] **CRITICAL**: Record for the summary's **Decided without review** (this replaces the former
  test-coverage review, so it is never skipped):
  - Total number of tests created, and their categories/groups
  - List of all test titles created
  - Clickable links to test file locations (format: `path/to/file.test.ts#LX`)
  - Brief summary of what behavior each test preserves
  - Confirmation that all tests are currently PASSING (locking in State A)

**Outcome**: Comprehensive tests that pass with current code, locking in behavior

**Quality Gate**: Every behaviour the changeset lists to preserve has a test, and every test is green on State A

#### TODO: Implement Migration Using TDD

**Migration TDD Pattern**:

1. Tests are already passing (preserve behavior)
2. Refactor code (change implementation)
3. Tests should still pass (behavior preserved)
4. If tests fail: implementation change broke behavior (fix it)

##### TODO: Migration Cycle - Implement Changes

**Row**: 3 — Migrate (`/plan-tdd-migration`, using the `/green` procedure)
**Skill**: `tdd` (`.agents/skills/tdd/SKILL.md`) — on Muse, the `tdd-implementer` subagent
**Uses**: `.agents/skills/tdd/references/tdd.md` skill

**Actions**:

- [ ] Implement migration changes incrementally
- [ ] **CRITICAL**: Keep all tests passing throughout migration
- [ ] If tests fail, fix implementation (behavior must be preserved)
- [ ] Focus on code quality and maintainability
- [ ] Update changeset with migration progress
- [ ] Tick the Migrate row's completed milestone TODOs

**Quality Gate**: All tests pass after each migration step (behavior preserved)

##### TODO: Add New Tests for Improved Implementation

**Command**: `/red` (optional)
**Purpose**: Add tests for new implementation details (if needed)

**Actions**:

- [ ] Write tests for new implementation patterns (if applicable)
- [ ] Test new internal APIs (if exposed)
- [ ] Verify tests fail before implementation
- [ ] Implement to make tests pass
- [ ] Update changeset with test additions

**Note**: This step is optional - only needed if migration introduces new testable behaviors

##### TODO: Update Documentation

**Command**: `/update-context-docs`

**Actions**:

- [ ] Update changeset docs with migration progress
- [ ] Tick the Migrate row's completed milestone TODOs
- [ ] Document technical decisions made during implementation
- [ ] Track any technical debt discovered
- [ ] Update dev docs with new architecture patterns

**Repeat Migration cycle**: Continue implementing, testing, documenting until migration is complete

#### TODO: Run All Tests

**Actions**:

- [ ] Run the affected packages' tests: `uv run pytest -q` — every affected package
- [ ] Ensure all tests pass (unit + integration + e2e)
- [ ] **CRITICAL**: Verify behavior preservation tests still pass
- [ ] Fix any broken tests in unrelated code
- [ ] Verify no test anti-patterns introduced

**Quality Gate**: All tests pass, 100% success rate, behavior preserved

#### TODO: Close the Migrate Row

**Actions**:

- [ ] Commit the migration with the changeset and close row 3 ✅
- [ ] Record for the summary's **Decided without review** (this replaces the former
  migration-complete review):
  - All behavior preservation tests passing
  - Migration milestones completed
  - Code quality improvements achieved
  - Key technical decisions made

**Quality Gate**: Row 3 closed with the green preservation-test count as its evidence

### Phase 3: Production Readiness (PR Wrap Steps)

This phase is the **Wrap** row's detail, run by `/pr-wrap`; it is listed here so the plan's TODOs
cover the whole lifecycle.

**🚨 CRITICAL WARNING - VALIDATION STEPS ARE MANDATORY 🚨**

**ALL validation steps MUST be executed. NO EXCEPTIONS.**

Execute these steps in order to ensure code is production-ready:

#### TODO: Validate Changes

**Command**: `/validate-changes`

**🚨 MANDATORY - CANNOT SKIP 🚨**

**Actions**:

- [ ] Run `/validate-changes` to analyze code for:
  - Production threats
  - Testing infrastructure risks
  - Security vulnerabilities
  - Unsafe code patterns
- [ ] Review validation results in changeset
- [ ] Update changeset "Validation Results" section
- [ ] **NEVER skip this step regardless of test/lint status**

**Outcome**: List of issues to address

#### TODO: Refactor Issues from Change Validation

**Skill**: `code-cleaning` (`.agents/skills/code-cleaning/SKILL.md`) — on Muse, the `refactor` subagent

**Actions**:

- [ ] Apply `code-cleaning` to fix issues found in change validation
- [ ] Address production threats and unsafe patterns
- [ ] Verify fixes don't break tests
- [ ] Update changeset with fixes applied

**Quality Gate**: All critical risks resolved

#### TODO: Validate Tests

**Command**: `/validate-tests`

**🚨 MANDATORY - CANNOT SKIP 🚨**

**Actions**:

- [ ] Run `/validate-tests` to check:
  - Test anti-patterns (conditional logic, fallbacks, try/catch)
  - Deterministic behavior
  - Test-specific code branches in production code
  - Test quality standards
- [ ] Review test validation results
- [ ] Update changeset "Validation Results" section
- [ ] **NEVER skip this step - passing tests don't guarantee test quality**

**Outcome**: List of test quality issues

#### TODO: Refactor Test Issues

**Skill**: `code-cleaning` (`.agents/skills/code-cleaning/SKILL.md`) — on Muse, the `refactor` subagent

**Actions**:

- [ ] Apply `code-cleaning` to fix test issues
- [ ] Remove test anti-patterns
- [ ] Ensure deterministic test behavior
- [ ] Verify all tests still pass
- [ ] Update changeset with fixes applied

**Quality Gate**: All tests meet quality standards

#### TODO: Validate Production Readiness

**Command**: `/validate-prod-ready`

**🚨 MANDATORY - CANNOT SKIP 🚨**

**Actions**:

- [ ] Run `/validate-prod-ready` to check:
  - Mock code in production
  - TODO/FIXME markers
  - Unused code and imports
  - Test-specific branches in production code
  - Fallback logic without consent
- [ ] Review production readiness results
- [ ] Update changeset "Validation Results" section
- [ ] **NEVER skip this step - it catches production-specific issues**

**Outcome**: List of production readiness issues

#### TODO: Refactor Production Readiness Issues

**Skill**: `code-cleaning` (`.agents/skills/code-cleaning/SKILL.md`) — on Muse, the `refactor` subagent

**Actions**:

- [ ] Apply `code-cleaning` to fix production readiness issues
- [ ] Remove mocks and workarounds
- [ ] Address TODO/FIXME markers
- [ ] Clean up unused code
- [ ] Verify all tests still pass
- [ ] Update changeset with fixes applied

**Quality Gate**: Code is production-ready, no mocks or workarounds

#### TODO: Analyze Code Quality

**Command**: `/analyze-clean-code`

**🚨 MANDATORY - CANNOT SKIP 🚨**

**Actions**:

- [ ] Run `/analyze-clean-code` to analyze:
  - Function length and complexity
  - Nesting depth
  - Parameter count
  - Magic numbers
  - Code duplication
- [ ] Review code quality metrics
- [ ] Update changeset "Validation Results" section
- [ ] **NEVER skip this step - clean code principles matter**

**Outcome**: Code quality improvement recommendations

#### TODO: Refactor Code Quality Issues

**Skill**: `code-cleaning` (`.agents/skills/code-cleaning/SKILL.md`) — on Muse, the `refactor` subagent

**Actions**:

- [ ] Apply `code-cleaning` for code quality improvements
- [ ] Apply clean code principles
- [ ] Reduce complexity where needed
- [ ] Verify all tests still pass
- [ ] Update changeset with improvements applied

**Quality Gate**: Code meets clean code standards

#### TODO: Final Validation

**Command**: `/validate-changes`

**🚨 MANDATORY - CANNOT SKIP 🚨**

**Actions**:

- [ ] Re-run `/validate-changes` after all refactoring
- [ ] Ensure no new issues introduced during refactoring
- [ ] Confirm all previous issues resolved
- [ ] Update changeset with final validation status
- [ ] **NEVER skip this step - verify refactoring didn't introduce new issues**

**Quality Gate**: Clean final validation, ready for PR

#### TODO: Linting and Type Checking

**Actions**:

- [ ] Run `uv run ruff check src tests` to fix linting issues
- [ ] Run `uv run pytest -q` — every affected package — to verify types (mypy strict)
- [ ] Run `uv run pytest -q` — every affected package — to confirm all tests still pass
- [ ] Fix any issues that arise

**Quality Gate**: No linting errors, no type errors, all tests pass

#### TODO: Update and Wrap Documentation

**Command**: `/wrap-context-docs`

**Actions**:

- [ ] Update changeset with final migration status
- [ ] Confirm no TODO is open under the rows before Wrap
- [ ] If migration complete: wrap changeset into dev docs
  - Apply changeset to affected package READMEs and dev docs
  - Delete changeset from `docs/<area>/1-WIP/` once wrapped (not archived)
  - Delete `{slug}-initial-discovery.md` with the changeset (not archived, not merged into package docs)
  - Write `{package}/docs/changesets/YYYY-MM-DD-short-description.md`
- [ ] Update dev docs to reflect State B architecture

**Quality Gate**: Documentation reflects migrated state accurately

---

## Plan Template Format

**IMPORTANT**: This template shows the markdown **body structure** for readability and context. The
plan's frontmatter `todos:` array should contain **granular** workflow steps (planning → migration →
production readiness), not only high-level phases. See the example below.

**On Muse**: when the plan content below is ready you **MUST** deliver it through the `planning workflow`
tool, which hands the Plan-mode plan over to be written — **never** as a plain-text markdown
message. On other harnesses, present it inline. Either way the changeset written from it carries
`[wf]` rows (the migration preset), and the plan's TODOs are those rows' detail.

After gathering context, generate a plan with this markdown body structure:

```markdown
# Migration Implementation Plan: [Migration Name]

## Overview

[Brief description of what we're migrating and why]

## Affected Packages

- `surmap` - [what's changing technically]
- `surmap` - [what's changing technically]

## Pre-existing Test Baseline

[Summarize per-package baseline from Step 1 — pass/fail counts, known failures, scope]

## Workflow

[The migration preset from the `pr-lifecycle` skill § *Presets*, with the plan's TODOs nested under
the row that does them — the only checkboxes in the document:]

- [wf 1] ⏳ `/plan-tdd-migration` Plan — changeset, recorded baseline, initial discovery ·
  - [ ] Write `{slug}-initial-discovery.md`
  - [ ] Create migration changeset — first content section is `## Initial Discovery`; Plan-mode discussion after that
- [wf 2] ⬜ `/plan-tdd-migration` Preservation tests — green against the baseline, committed ·
- [wf 3] ⬜ `/plan-tdd-migration` Migrate — preservation tests still green ·
  - [ ] Milestone 1: [migration step] (the `/green` procedure; `/red` for new tests if needed)
  - [ ] Run all tests (`uv run pytest -q` — every affected package)
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded
  - [ ] Validate tests (`/validate-tests`)
  - [ ] Validate production readiness (`/validate-prod-ready`)
  - [ ] Analyze code quality (`/analyze-clean-code`)

## Migration Strategy

### State A (Current)

[Describe current code/architecture]

### State B (Target)

[Describe target code/architecture]

### Migration Approach

[High-level steps and key technical decisions]

### Behavior Preservation Strategy

[How to ensure features remain unchanged]

## Workflow Summary (Detailed in TODOs)

### Phase 1: Planning
- Gather migration context and per-package test baseline
- Create migration changeset (`/plan-ft-dev`) in `docs/<area>/1-WIP/`

### Phase 2: Migration Implementation
- Create behavior preservation tests (row 2) — tests pass on State A
- Migration cycle (row 3): implement (the `/green` procedure), keep tests passing, optional new tests (`/red`), update docs (`/update-context-docs`)
- Run all tests (`uv run pytest -q` — every affected package)

### Phase 3: Production Readiness (ALL MANDATORY — row 4, `/pr-wrap`)
- Validate changes (`/validate-changes`) → `code-cleaning`
- Validate tests (`/validate-tests`) → `code-cleaning`
- Validate production readiness (`/validate-prod-ready`) → `code-cleaning`
- Analyze code quality (`/analyze-clean-code`) → `code-cleaning`
- Final validation (`/validate-changes`)
- Linting and type checking
- Wrap documentation (`/wrap-context-docs`)
- Open the PR ready — the wrap's last act, not a TODO

## Technical Decisions

[Document key architectural decisions made during planning]

## Risks and Mitigations

[Identify potential risks and how to address them]

## Rollback Strategy

[How to revert if issues arise]

## Success Criteria

[What "done" looks like for this migration - all tests pass, behavior preserved, code quality improved]
```

### Frontmatter TODOs Array Example (Migration)

When creating the plan, the `todos:` array in the frontmatter should list discrete steps (adjust
IDs/content to your migration). Example structure:

```yaml
todos:
  - id: planning-context
    content: "Gather migration context + baseline tests (Step 1)"
    status: completed
  - id: planning-discovery
    content: "Write {slug}-initial-discovery.md before the changeset (/plan-ft-dev)"
    status: pending
  - id: planning-changeset
    content: "Create migration changeset in docs/<area>/1-WIP/ (/plan-ft-dev) — opens with ## Initial Discovery; Plan-mode discussion after that"
    status: in_progress
  - id: dev-behavior-tests
    content: "Row 2: create behavior preservation tests — passing on State A, committed"
    status: pending
  - id: dev-migrate
    content: "Row 3: implement migration; keep tests passing (/green procedure, /update-context-docs)"
    status: pending
  - id: dev-run-all-tests
    content: "Run full test suite (uv run pytest -q
    status: pending
  - id: prod-validate-changes
    content: "Validate changes (/validate-changes) - MANDATORY"
    status: pending
  - id: prod-refactor-changes
    content: "Refactor issues from change validation (code-cleaning)"
    status: pending
  - id: prod-validate-tests
    content: "Validate tests (/validate-tests) - MANDATORY"
    status: pending
  - id: prod-refactor-tests
    content: "Refactor test issues (code-cleaning)"
    status: pending
  - id: prod-validate-ready
    content: "Validate production readiness (/validate-prod-ready) - MANDATORY"
    status: pending
  - id: prod-refactor-ready
    content: "Refactor production readiness issues (code-cleaning)"
    status: pending
  - id: prod-analyze-quality
    content: "Analyze code quality (/analyze-clean-code) - MANDATORY"
    status: pending
  - id: prod-refactor-quality
    content: "Refactor code quality issues (code-cleaning)"
    status: pending
  - id: prod-final-validation
    content: "Final validation (/validate-changes) - MANDATORY"
    status: pending
  - id: prod-lint-typecheck
    content: "Lint and type-check (uv run ruff check src tests, uv run pytest -q
    status: pending
  - id: prod-wrap-docs
    content: "Wrap documentation (/wrap-context-docs) — when the PR is set ready for review"
    status: pending
```

**Remember**: Expand or merge TODOs as needed; keep validation steps as separate items. The
`## Workflow` rows are the sequence; the TODOs are their detail.

## Best Practices

### During Context Gathering (Step 1)

1. **MANDATORY - Use AskUserQuestion tool**: Always use AskUserQuestion tool for gathering migration details
   - Present organized questions in multi-select widgets
   - Gather technical constraints and target architecture details
   - Wait for user responses before planning
   - DO NOT make assumptions or skip this step
2. **Understand current state**: Get clear picture of State A (current code/architecture)
3. **Define target state**: Understand State B (desired code/architecture)
4. **Identify affected packages**: List all packages that will change
5. **Clarify constraints**: Technical limitations, backward compatibility requirements

### During Technical Planning (Plan Mode - Steps 2-3)

1. **Ask questions**: Clarify technical ambiguities
2. **Explore migration paths**: Discuss multiple refactoring approaches
3. **Consider trade-offs**: Discuss pros/cons of each approach
4. **Plan incrementally**: Break migration into safe, testable steps
5. **Document decisions**: Capture rationale for technical choices
6. **Define rollback**: Plan how to revert if issues arise
7. **Behavior preservation**: Define strategy to ensure features don't change

### During Execution (After Plan)

1. **Test first**: Write behavior preservation tests before changing code
2. **Keep tests passing**: Tests should pass throughout migration
3. **Migrate incrementally**: Small steps, verify at each step
4. **Close each row**: Record its evidence in its `[wf]` row, and put what a reviewer would want to see in the summary — never pause for it
5. **Document progress**: Update changeset as migration proceeds
6. **Quality first**: Use migration as opportunity to improve code quality

### Behavior Preservation Strategy

1. **Write tests against current code**: Lock in existing behavior
2. **Focus on external behavior**: Test what, not how
3. **Keep tests passing**: If tests fail, fix implementation
4. **Add integration tests**: Verify end-to-end behavior preserved
5. **Manual testing**: User should test critical paths after migration

## Related Commands and Skills

**Skills**:

- `.agents/skills/pr-lifecycle/SKILL.md` - The migration preset and the step contract
- `.agents/skills/tdd/references/tdd.md` - TDD methodology for migration implementation

**Planning Commands**:

- `/plan-ft-dev` - Technical planning and changeset creation (used for migration)

**Development Commands**:

- `/red` - Write additional tests (optional)
- `/green` - The implementation procedure row 3 uses
- `/update-context-docs` - Sync documentation with progress

**Production Readiness Commands**:

- `/validate-changes` - Critical change assessment
- `/validate-tests` - Test quality validation
- `/validate-prod-ready` - Production readiness check
- `/analyze-clean-code` - Code quality analysis
- `/wrap-context-docs` - Finalize documentation
- `/pr` - Create pull request

**Skills**:

- `tdd` (`.agents/skills/tdd/SKILL.md`) - Implements migration with quality-first approach
- `code-cleaning` (`.agents/skills/code-cleaning/SKILL.md`) - Improves code quality and fixes issues

**References**:

- `.agents/skills/planning/references/dev-doc.md` - Development documentation format
- `.agents/skills/pr-lifecycle/references/changeset.md` - Changeset structure and workflow
- `.agents/skills/tdd/references/testing-practices.md` - Test quality standards
- `.agents/skills/tdd/references/tdd.md` - TDD methodology
- `.agents/skills/coding/references/coding-practices.md` - Code quality standards

## Success Criteria

A successful migration plan should:

1. ✅ Gather migration context using AskUserQuestion tool (Step 1)
2. ✅ Switch to Plan mode for technical planning (Step 2)
3. ✅ Create comprehensive changeset in Plan mode (Step 3)
4. ✅ Include all phases: Planning → Migration → Production
5. ✅ Have detailed TODOs with clear actions and commands
6. ✅ Define behavior preservation strategy
7. ✅ Write `## Workflow` from the migration preset, and close rows 1–3 with evidence
8. ✅ Reference appropriate commands and skills
9. ✅ Include all PR wrap steps as individual TODOs
10. ✅ Emphasize behavior preservation throughout
11. ✅ Be actionable and easy to follow

## Key Differences from Feature Development

### What's Different

- ❌ **No feature documentation** - features don't change
- ✅ **Behavior preservation tests** - write tests against current code first
- ✅ **Tests should pass** - unlike feature dev, tests pass before implementation
- ✅ **Focus on refactoring** - improve code without changing behavior
- ✅ **State A → State B** - describe code/architecture transition, not feature transition

### What's the Same

- ✅ **Plan mode collaboration** - still plan in Plan mode
- ✅ **Changeset tracking** - still use changeset for progress
- ✅ **TDD cycle** - preservation tests first, then the Migrate row (`/plan-tdd-migration`) keeps them green
- ✅ **Validation steps** - all validation steps still mandatory
- ✅ **`[wf]` rows** - the same step contract; only the preset differs

## What the Summary Carries Instead of Checkpoints

The two former review checkpoints are gone. Their content is reported, not asked about; a
developer who wants to look before migrating edits the `[wf]` rows (an extra row, a different command)
and the command follows it.

**After row 2** — under **Decided without review**: every test title with its file link, what
behaviour each preserves, how complete the coverage is against the changeset's preserve list, and
confirmation that each is PASSING on State A. This is the safety net the migration relies on, so
it is never left out.

**After row 3** — under **Decided without review**: the migrated code structure, the preservation
tests still green, the milestones completed and the technical decisions made. A behaviour change
discovered here is a ⛔ halt (§ *Workflow row*), not a summary line.

---

**Last Revised:** 2026-02-14
