---
description: Validate test quality by detecting anti-patterns and ensuring deterministic behavior
---
## Validate Test Quality

This command validates test quality to ensure tests are reliable, maintainable, and provide production confidence by detecting anti-patterns and checking for deterministic behavior — and **scores readability** against the fluent rubric, because every test an agent writes must be fluent (`.agents/skills/testing/references/fluent-style.md`).

## Context Documents

**Expect in context**:
- Changeset document (`docs/<area>/1-WIP/YYYY-MM-DD-*.md`) - tracks implementation progress
- PRD document (`docs/*/1-WIP/YYYY-MM-DD-*.md`) - tracks requirement changes

**Use these documents to**:
- Understand expected test coverage from "Acceptance Tests" section
- Validate tests align with planned testing strategy
- Update "Validation Results" section in changeset

## When Invoked

1. **Check for context documents**:
   - Read changeset if provided
   - Review "Testing Plan" and "Acceptance Tests" sections

2. **Identify test files in changes**:
   ```bash
   err="${TMPDIR:-/tmp}/pr-base.err"
   if ! base=$(gh pr view --json baseRefName --jq .baseRefName 2>"$err"); then
     grep -q 'no pull requests found' "$err" \
       || { cat "$err" >&2; echo "ERROR: cannot resolve the PR's base — fix before proceeding, do not skip" >&2; exit 1; }
     base=master   # no PR yet: an ordinary branch, based on master
   fi
   git fetch origin "$base" --quiet \
     || { echo "ERROR: cannot fetch origin/$base — fix before proceeding, do not skip" >&2; exit 1; }
   mb=$(git merge-base "origin/$base" HEAD) \
     || { echo "ERROR: no merge-base with origin/$base — fix before proceeding, do not skip" >&2; exit 1; }
   git diff --name-only --diff-filter=d "$mb"..HEAD | grep -E '\.(test|spec)\.(ts|tsx|js|jsx)$'
   ```

   Also list the test files the PR **added** (`--diff-filter=A`): a suite this PR created is the
   PR's in full; in every other file only the tests the PR added or edited are.

   Diff the **whole PR range** (merge-base with the PR's base), never `HEAD~1` — on a multi-commit
   PR, `HEAD~1` analyzes only the last commit and every earlier commit passes unchecked.
   Only "no PR for this branch" means `master`; any other lookup failure aborts, because guessing
   the base of a stacked PR would analyze its predecessors' commits as this PR's.

2. **Read each test file** and analyze for issues.

## Anti-Patterns to Detect

### Always-Passing Tests
- Tests with no assertions
- Tests that catch and swallow errors
- Tests with `expect(true).toBe(true)`

### Skipped/Focused Tests
- `.skip` markers that shouldn't be committed
- `.only` markers that limit test runs
- Commented-out test cases

### Flaky Tests
- Timing-dependent assertions (`setTimeout`, fixed delays)
- Order-dependent tests
- Tests relying on external state

### Description-Body Misalignment
- Test name doesn't match what it actually tests
- Misleading `describe` blocks
- Generic names like "should work"

### Hardcoded Values
- Values that should be dynamic
- Dates/times that will break
- Environment-specific paths

### Missing Edge Cases
- Only happy path tested
- No error handling tests
- No boundary condition tests

## Fluent Readability Score

Load the `fluent-tests` skill (`.agents/skills/fluent-tests/SKILL.md`) and the rubric in
`.agents/skills/testing/references/fluent-style.md` § *The score*. For each changed test file:

1. **Score every test this PR added or edited** against the ten checks — one row per test, the
   failing checks named. A test below **8**, or failing check 3 (flat) or 9 (no sleeps), is
   🔴 **Critical**: this PR wrote it, so this PR fixes it. A suite this PR created must also reach a
   suite score of 8.
2. **Score the rest of the suite** — the tests this PR did not write — and report the suite score.
   Below **7** is a `non-fluent-tests` finding for the suite: ℹ️ in this report, never a reason to
   fail the PR. It is handed to `/analyze-code-issues` to file or update the suite's record
   (`<package-dir>/docs/code-issues/non-fluent-tests-<file-slug>.md`), which is how it reaches the
   migration that will take it (`fluent-style.md` § *Migrating a suite*).
3. **Do not rewrite** the suite's other tests to raise its score. That is a migration, its own PR.

Keep the per-test rows in the report: the score is judged, and the rows are what makes it
reproducible.

## Output Format

```markdown
## Test Validation Report

### Tests Analyzed
- test1.test.ts (X test cases)
- test2.test.ts (Y test cases)

### Quality Summary
| Metric | Count |
|--------|-------|
| Total test cases | X |
| Anti-patterns found | Y |
| Skipped tests | Z |
| Tests this PR wrote or edited below fluent 8 | N |

### Fluent Readability
| File | PR's tests (min / mean) | Rest of suite | Verdict |
|------|-------------------------|---------------|---------|
| `session-edit.it.test.ts` | 9 / 9.4 (5 tests) | 4.6 (31 tests) | ✅ PR's tests · ℹ️ suite → `non-fluent-tests` record |
| `asset-builder.test.ts` (new) | 6 / 7.8 (4 tests) | — | 🔴 2 tests below 8 |

<details><summary>Per-test rows</summary>

| File | Test | Score | Failing checks |
|------|------|-------|----------------|
| `asset-builder.test.ts` | `builds an asset` | 6 | 1 (name), 5 (literal), 6 (roulette), 10 |

</details>

### Issues Found

#### 🔴 Critical
1. **[file:line]** Always-passing test
   ```python
   // problematic code
   ```
   - Fix: Add meaningful assertions

2. **[file:line]** Test this PR wrote scores 6/10 — failing checks 5, 6
   - Fix: extract an `anAsset()` builder; assert with one intent-revealing matcher

#### ⚠️ Warnings
1. **[file:line]** Description-body mismatch
   - Test says: "should validate input"
   - Test does: Only checks output format

#### ℹ️ Suggestions
1. **[file:line]** Consider adding edge case for null input

### Run Tests
```bash
uv run pytest -q:unit
uv run pytest -q:it
```
```

## Update Changeset

If changeset document exists, update the **Validation Results** section:

```markdown
### Test Validation (`/validate-tests`)

**Last Run**: YYYY-MM-DD
**Status**: ✅ Passed | ⚠️ Warnings | ❌ Issues Found

**Summary**:
- Tests analyzed: X
- Anti-patterns found: Y
- Description-body mismatches: Z
- Fluent: PR's tests min <n>/10 · suites below 7 → `non-fluent-tests`: <list or none>

**Issues Found**:
- [List critical issues with file:line]

**Added to Refactoring Needed**:
- [List items added to refactoring section]
```

Also add issues to **Refactoring Needed** section under `### From `/validate-tests``.

## Reference

- **Command**: `/validate-tests`
- **Rules**: `.agents/skills/tdd/references/testing-practices.md`, `.agents/skills/pr-lifecycle/references/changeset.md`
