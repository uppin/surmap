---
description: Systematic approach to fixing failing tests
---
## Fix Failing Tests

This command guides systematic resolution of test failures by analyzing core production issues and improving both production and test code.

**For testing standards, see `.agents/skills/tdd/references/testing-practices.md` rule.**

## Prerequisites

Check for development documentation and active investigations:
- Dev docs: `{common,common-testing,mapping-pipeline,onboard-detection,surmap,packages}/*/docs/*.md`
- Changeset: `docs/<area>/1-WIP/*.md`
- Investigation docs: `docs/<area>/investigations/*.md`

## Workflow

### 1. Display Relevant Documents

List which documents are in context at the top of the report, so the developer can see what the fixes were aligned to.

### 2. Determine Test Scope

**Unless user specifies specific tests, run all tests:**
```bash
uv run pytest -q
```

**For specific tests:**
```bash
cd packages/package-name
uv run pytest -q
```

### 3. Analyze Failures

For each failing test:

**Step 1: Is there a core production issue?**
- Analyze error message
- Check stack trace
- Identify root cause in production code

**Step 2: Is the test code insufficient/flawed?**
- Does test follow `.agents/skills/tdd/references/testing-practices.md`?
- Is test deterministic?
- Does test have proper setup/teardown?
- Are assertions correct?

**Step 3: Is the test relevant and necessary?**
- Does test cover actual requirement?
- Is test duplicated elsewhere?
- Should test be removed?

**Step 4: Are additional tests needed?**
- Are there coverage gaps?
- Are edge cases missing?
- Should complementary tests be added?

### 4. Fix Core Issues

**Priority order:**
1. **Production code bugs** - Fix actual functionality issues
2. **Test infrastructure** - Fix test setup/helpers
3. **Test implementation** - Improve test code quality
4. **Test coverage** - Add missing tests

### 5. Use Debug Tools

Speed up troubleshooting with:
- DEBUG environment variables
- `debug` logging package (`createLogger` factory in each package)
- Visual inspection (`/visual-inspection` if stuck)
- Test isolation (run single test)

### 6. Validate Alignment with Standards

Ensure fixes comply with `.agents/skills/tdd/references/testing-practices.md`:
- ❌ No conditional test logic
- ❌ No try/catch workarounds
- ❌ No fallback assertions
- ✅ 100% deterministic behavior
- ✅ Single assertion path
- ✅ Clear failure mode

### 7. Improve Code Quality

Fixes should enhance:
- Production code correctness
- Test-support code reliability
- Test code clarity
- Overall system quality

## After Tests are Fixed

**🚨 CRITICALLY IMPORTANT**: Clean up debug code:
- Remove console.log statements added for debugging
- Remove temporary logging
- Remove investigation-specific code
- Restore production-quality code

### Verify All Tests Pass

```bash
uv run pytest -q
```

Ensure:
- ✅ All tests passing
- ✅ No skipped tests (without good reason)
- ✅ No flaky tests
- ✅ Debug code removed

## Output Format

```markdown
## 🧪 Test Fix Summary

### Tests Analyzed
- Total tests run: X
- Initially failing: Y
- Now passing: Z
- Still failing: W

### Fixes Applied

#### Production Code Fixes
- [x] Fixed bug in `functionName` (file:line)
  - Issue: [description]
  - Fix: [description]

#### Test Infrastructure Fixes
- [x] Fixed test helper `helperName` (file:line)
  - Issue: [description]
  - Fix: [description]

#### Test Implementation Improvements
- [x] Improved test "should do X" (file:line)
  - Issue: Conditional logic
  - Fix: Split into 2 deterministic tests

#### Additional Tests Added
- [x] Added test for edge case (file:line)
  - Coverage: [what was missing]

### Failures Analysis

#### Core Production Issues
- Issue 1: [description and fix]

#### Test Code Issues
- Issue 1: [description and fix]

### Test Quality Validation
- ✅ No conditional logic
- ✅ No try/catch workarounds
- ✅ No fallback assertions
- ✅ All tests deterministic
- ✅ Single assertion paths

### Debug Code Cleanup
- [x] Removed X console.log statements
- [x] Removed Y temporary logging calls
- [x] Restored production code quality

### Final Test Results
```bash
uv run pytest -q
```

**Status**: ✅ All Passing | ⚠️ Some Failing

- Passing: X tests
- Failing: Y tests (reasons)
- Skipped: Z tests (reasons)

### Next Steps
[If all passing: proceed with development]
[If still failing: describe remaining issues]
```

## Update Documentation

**If changeset exists**: Update "Validation Results":
```markdown
### Test Fixes (`/fix-tests`)
**Last Run**: YYYY-MM-DD
**Status**: ✅ All Passing | ⚠️ Issues Remain

**Summary**:
- Tests fixed: X
- Production bugs fixed: Y
- Test infrastructure improved: Z
```

Add completed items to "Refactoring Needed":
```markdown
### From `/fix-tests` (Test Fixes)
- [x] Fixed production bug in file:line ✅
- [x] Improved test quality in file:line ✅
```

## Common Failure Patterns

### Pattern 1: Async Timing Issues
**Symptom**: Test passes sometimes, fails other times
**Fix**: Use `-eventually` or proper async/await

### Pattern 2: Test Order Dependencies
**Symptom**: Test fails when run with others, passes alone
**Fix**: Ensure proper test isolation and cleanup

### Pattern 3: Mock/Stub Issues
**Symptom**: Test expects mocked data, real data returned
**Fix**: Verify mock setup or remove unnecessary mocking

### Pattern 4: Environment Dependencies
**Symptom**: Test passes locally, fails in CI
**Fix**: Remove environment-specific assumptions

### Pattern 5: Description-Body Mismatch
**Symptom**: Test description doesn't match implementation
**Fix**: Update test body to match description (never change description)

## Best Practices

✅ **Do:**
- Analyze core production issues first
- Follow `.agents/skills/tdd/references/testing-practices.md` standards
- Use debug tools to speed up troubleshooting
- Clean up all debug code
- Improve both production and test code
- Run all tests unless user specifies

❌ **Don't:**
- Don't add workarounds to make tests pass
- Don't skip tests without good reason
- Don't leave debug code in production
- Don't ignore test quality issues
- Don't fix symptoms without addressing root cause

## Related

**Rules**: `.agents/skills/tdd/references/testing-practices.md`
**Related Commands**: `/validate-tests`, `/validate-prod-ready`
**Commands**: `/visual-inspection`, `/reproduce`
