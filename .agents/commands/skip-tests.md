---
description: Controlled test skipping with FIXME documentation (last resort)
---
## Skip Tests

This command provides guidance for temporarily disabling tests when absolutely necessary.

**⚠️ WARNING**: Skipping tests is unwanted behavior that may compromise system correctness.

## Prerequisites

**First, try to fix the tests** using `/fix-tests` command.

Skipping should be last resort.

**Skipping is the developer's decision, given in the invocation.** This command never asks
mid-turn. Invoked without naming which tests to skip, it analyses (steps 1–3), fixes what has a quick
fix, skips nothing, and ends the turn with the step 3 summary. The developer's answer — the tests to
skip, named in a re-invocation — is the decision, and only then do steps 5–6 run. Run inside a
changeset's `## Workflow` row, the row halts ⛔ with the step 3 options instead (the step contract in
`.agents/skills/pr-lifecycle/SKILL.md` § *Halts*).

## Workflow

### 1. Check Status

Run tests to see what's failing:
```bash
# All tests (unless user specified specific tests)
uv run pytest -q

# Specific package
cd packages/package-name
uv run pytest -q
```

Analyze failures:
- What's failing?
- Why is it failing?
- Are there quick fixes?

### 2. Analyze Quick-Fix Issues

Look for easy-to-fix issues:
- Typos in tests
- Incorrect assertions
- Simple logic errors
- Missing test setup

**If quick fixes possible**: Fix immediately, don't skip.

### 3. Provide Summary to User

```markdown
## 🧪 Test Status Analysis

### Failing Tests
- **Test 1**: `test-file.test.ts:line` - [reason]
  - **Quick fix**: [description]
  - **Estimated time**: X minutes

- **Test 2**: `test-file.test.ts:line` - [reason]
  - **Quick fix**: None obvious
  - **Requires**: Investigation/refactoring

### Recommendations
1. **Fix immediately**: Test 1 (quick fix available)
2. **Skip temporarily**: Test 2 (requires investigation)

### Options
A. Fix all tests now (recommended)
B. Fix quick issues, skip complex ones
C. Skip all failing tests (not recommended)

**Re-invoke naming the option (and the tests to skip) to proceed.**
```

### 4. The Developer's Decision

End the turn here unless the invocation already names the tests to skip. Nothing is skipped on
inference.

### 5. Test Skipping (Only the Tests the Invocation Names)

**Skip in code** (so CI knows):
```python
// Vitest
it.skip('test description', () => {
  // Test code
});

// Jest
xit('test description', () => {
  // Test code
});

// Or describe block
describe.skip('feature tests', () => {
  // Multiple tests
});
```

### 6. Add FIXME Documentation

**CRITICAL**: Each skipped test needs FIXME annotation.

**Single test:**
```python
// FIXME: Test failing due to Unicode handling issue in rtabmap binding
// Investigation: rtabmap binding doesn't normalize Unicode characters
// Initial analysis: Need to add Unicode normalization in parseText()
// Proposed fix: Use unicode-normalization library, estimate 2-4 hours
// Related: Issue #123, packages/rtabmap binding/src/parser.ts:line
it.skip('should handle Unicode characters', () => {
  // Test code
});
```

**Block of tests:**
```python
// FIXME: RTAB-Map replay tests failing in CI (no native binding)
// Investigation: CI missing font dependencies
// Initial analysis: Fonts not available in GitHub Actions Ubuntu
// Proposed fix: Install font packages in CI script, add font fallbacks
// Alternative: Use headless rendering with embedded fonts
// Estimate: 3-5 hours to implement proper fix
// Related: .github/workflows/test.yml, packages/reconstruction/
pytestmark = pytest.mark.skip(reason='RTAB-Map binding unavailable in CI')
  def test_replay_renders_static_layer() -> None: ...
  it('should handle multiple pages', () => {});
});
```

## FIXME Annotation Template

```python
// FIXME: [Brief description of why skipped]
// Investigation: [What was discovered during initial analysis]
// Initial analysis: [Root cause hypothesis]
// Proposed fix: [How to fix, with alternatives if applicable]
// Estimate: [Time to implement fix]
// Related: [Links to files, issues, documentation]
it.skip('test description', () => {});
```

## Shared FIXME for Test Block

```python
/**
 * FIXME: [Feature name] tests skipped
 *
 * Reason: [Why entire block is skipped]
 *
 * Investigation:
 * - [Finding 1]
 * - [Finding 2]
 *
 * Initial Analysis:
 * - Root cause: [hypothesis]
 * - Impact: [what's affected]
 *
 * Proposed Fix:
 * 1. [Step 1]
 * 2. [Step 2]
 *
 * Alternative Approaches:
 * - Option A: [description] (estimate: X hours)
 * - Option B: [description] (estimate: Y hours)
 *
 * Estimate: [time to fix]
 * Priority: [High/Medium/Low]
 * Related: [files, issues, docs]
 */
describe.skip('Feature tests', () => {
  // Multiple tests
});
```

## Output Format

```markdown
## ⏭️ Tests Skipped

### Skipped Tests
- **Test**: `test-file.test.ts:line` - [description]
  - **Reason**: [why skipped]
  - **Fix estimate**: [time]
  - **FIXME added**: ✅

- **Test Block**: `test-file.test.ts:line-range`
  - **Tests affected**: X tests
  - **Reason**: [why skipped]
  - **Shared FIXME**: ✅

### FIXME Documentation

#### Test 1
```python
// FIXME: Unicode handling issue
// Investigation: Parser doesn't normalize
// Proposed fix: Add unicode-normalization library
// Estimate: 2-4 hours
it.skip('should handle Unicode', () => {});
```

#### Test Block (X tests)
```python
/** FIXME: Rendering tests - CI font issues
 * Investigation: Fonts missing in GitHub Actions
 * Proposed fix: Install fonts in CI, add fallbacks
 * Estimate: 3-5 hours
 */
pytestmark = pytest.mark.skip(reason='RTAB-Map binding unavailable in CI')
```

### Summary
- Total tests skipped: X
- FIXME annotations added: X
- Estimated fix time: Y hours
- Priority: [High/Medium/Low]

### ⚠️ Warning
Skipped tests reduce test coverage and may hide bugs.
**Action required**: Fix skipped tests as soon as possible.

### Next Steps
1. [ ] Create issue/ticket for fixing skipped tests
2. [ ] Schedule time to implement fixes
3. [ ] Run all tests regularly to catch regressions

**Tests skipped with documentation**: ✅
```

## Best Practices

✅ **Do:**
- Try to fix tests first
- Skip only the tests the developer named in the invocation
- Skip in code (not just locally)
- Add comprehensive FIXME documentation
- Provide fix estimate
- Track skipped tests
- Plan to fix soon

❌ **Don't:**
- Don't skip without FIXME annotation
- Don't skip without investigation
- Don't skip permanently
- Don't forget fix estimate
- Don't skip large numbers of tests without concern
- Don't skip a test the invocation did not name

## When Skipping is Acceptable

✅ **Acceptable reasons:**
- Known issue requiring significant refactoring
- External dependency not available (with plan to fix)
- Test environment limitation (with workaround planned)
- Feature temporarily disabled

❌ **NOT acceptable reasons:**
- Test is "flaky" (fix the test or production code)
- Too lazy to fix (fix it)
- Don't understand failure (investigate first)
- "Works on my machine" (fix environment issue)

## Related

**Rules**: `.agents/skills/tdd/references/testing-practices.md`
**Related Commands**: `/validate-tests`
**Commands**: `/fix-tests` (try this first)
