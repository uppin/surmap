---
name: fluent-tests
description: "Write fluent, human-readable tests that read like plain English while using the type system. Use when writing tests, improving test readability, designing matchers, or structuring Given-When-Then patterns."
---

# Fluent Tests

Write tests that a human or AI can read like a specification. Every test should answer three questions at a glance: what is set up, what happens, and what is expected.

## When to Use

- Writing new tests in any language or framework
- Refactoring existing tests for readability
- Designing custom matchers or assertion helpers
- Creating test data builders or factory functions
- Reviewing test code for clarity

## When NOT to Use

- For TDD workflow/process — use `tdd` or `tdd-workflow` instead
- - For fixing flaky tests — use `e2e-framework-flaky-doctor` or `fix-flaky-test` instead

## Core Principles

1. **Three-act structure** — every test has Given (setup), When (execute), Then (verify), visually separated
2. **Flat and deterministic** — no nesting beyond one describe block, no conditionals or loops in tests
3. **Intent-revealing names** — test names form a sentence describing the behavior, not the implementation
4. **Builders for data** — complex objects built fluently with sensible defaults, override only what matters
5. **Custom matchers** — domain-specific assertions that read as English phrases
6. **One behavior per test** — each test proves exactly one thing
7. **Concrete values** — use meaningful literals ("alice@<service-host>"), not random or placeholder data
8. **No noise** — extract setup helpers, hide irrelevant defaults, show only what the test is about

## Workflow

### 1. Detect Context

Read existing tests in the project. Identify:
- Language and test framework (for SurMap: Python with pytest; read the existing tests first)
- Existing patterns, matchers, builders, or drivers
- Naming conventions and file locations

### 2. Apply Language-Specific Patterns

Read the reference file matching the project's language:

- **Any language**: [references/generic-guidelines.md](references/generic-guidelines.md) — principles, anti-patterns, builders, matchers, async, mocking
- **Python (pytest)**: [references/python/pytest.md](references/python/pytest.md) — Given/When/Then with SurMap contracts, builders, adapter-seam fakes, domain assertions

Always read `generic-guidelines.md` first for the universal anti-patterns, then the framework-specific file for idiomatic examples.

### 3. Write or Refactor Tests

Apply in order of impact:
1. Restructure into Given/When/Then blocks
2. Extract builders or factories for test data
3. Replace raw assertions with matchers that express intent
4. Rename tests to describe behavior
5. Remove dead setup, irrelevant fields, and commented-out code
6. For async code: replace sleeps with event synchronization or `eventually`, and suggest production code changes (return promises, emit events) when the code isn't testable — see the "Testing Async Code" section in generic-guidelines.md

### 4. Verify Readability

For each test, ask: can someone who has never seen this code understand what it does by reading just the test name and the Then block? If no, the test needs more work.
