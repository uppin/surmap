---
description: Complete Test-Driven Development workflow and phase coordination
---
# Test-Driven Development (TDD) Workflow

This document outlines the complete Test-Driven Development workflow using the red-green-refactor cycle for both human developers and AI assistants.

## TDD Cycle Overview

Test-Driven Development follows a strict three-phase cycle that ensures robust, well-tested code:

### 🔴 Red Phase - Write Failing Tests
**Rule Reference**: Apply `@red` rule

1. **Write comprehensive failing tests** before any implementation
2. **Define the public API** through test usage and expected behavior
3. **Establish clear test structure** with descriptive names and assertions
4. **Verify tests fail** for the right reasons (missing implementation, not bugs)

**Purpose**: Capture requirements and desired behavior before coding begins.

### 🟢 Green Phase - Make Tests Pass
**Rule Reference**: Apply `@green` rule

1. **Implement minimal code** to make all failing tests pass
2. **Focus on functionality over form** - don't worry about perfect code yet
3. **Avoid over-engineering** - write just enough to satisfy tests
4. **Keep test changes minimal** - tests define the requirements

**Purpose**: Create working implementation with the least amount of code changes.

### 🔵 Refactor Phase - Clean Up Code
**Rule Reference**: Apply `@refactor` rule

1. **Improve code quality** without changing functionality
2. **Add proper Python typing (mypy strict)** and remove `any` types
3. **Follow clean code principles** - small methods, reduced nesting
4. **Ensure production readiness** while keeping all tests green

**Purpose**: Polish the implementation while maintaining test coverage and functionality.

## Workflow Coordination

### Planning TDD Execution Before Coding

When the user wants a one-shot TDD rollout plan before implementation starts, treat that as part of the TDD workflow rather than a separate system.

Recommended planning sequence:

1. Gather the missing requirements first.
   Clarify scope, affected packages or product areas, constraints, and whether the change is new work or an update.

2. Create the product-level planning document first.
   Draft the PRD, feature doc, or equivalent product artifact before technical planning.

3. Ask the user to switch to Plan mode if they want collaborative planning there.
   Do not assume you can switch modes yourself. If they stay in the current mode, continue planning in-thread.

4. Create the technical delta in `docs/<area>/1-WIP/`.
   Capture affected packages, approach, acceptance tests, testing plan, risks, and milestones in the changeset workflow.

5. Produce a full-lifecycle TODO list.
   Break the work into discrete steps for:
   - planning completion
   - failing acceptance tests
   - red and green cycles
   - progress doc updates
   - validation
   - wrap-up and final review

6. Stop at planning unless the user asks for implementation.

Guardrails:
- Keep product requirements and technical delta separate.
- Use `docs/<area>/1-WIP/` for in-progress technical planning.
- Do not update `{common,common-testing,mapping-pipeline,onboard-detection,surmap,packages}/*/docs/` during planning.
- Reserve stable package docs for wrap/finalization.

### Phase Transitions
- **Red → Green**: Only proceed when you have comprehensive failing tests
- **Green → Refactor**: Only proceed when all tests are passing
- **Refactor → Red**: Start next feature cycle with new failing tests

### Testing Strategy
- **Run tests frequently** during each phase to verify state
- **Use BDD principles** to make tests readable and behavior-focused
- **Maintain test isolation** - each test should be independent
- **Focus on edge cases** during the red phase

### Quality Gates
- **Red Phase**: All new tests must fail initially
- **Green Phase**: All tests must pass with minimal implementation
- **Refactor Phase**: All tests remain green after improvements

## Benefits of This Approach

- **Comprehensive test coverage** by design
- **Clear requirements definition** through failing tests
- **Regression prevention** with continuous test validation
- **Maintainable codebase** through structured refactoring
- **Documentation** via executable test specifications
