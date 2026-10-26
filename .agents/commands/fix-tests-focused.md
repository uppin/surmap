---
description: Focused test fixing - one test at a time with DEBUG=* enabled
---
## Fix Tests (Focused Mode)

This command provides systematic resolution of test failures through detailed investigation, executing tests one at a time with full debug logging enabled.

## Key Differences from Standard Test Fixing

1. **Run tests one at a time** - Execute each failing test individually for better focus
2. **Enable debug logging** - Turn on DEBUG environment variables for full visibility during test execution

## When Invoked

Check for development documentation and active investigations:
- Dev docs: `{common,common-testing,mapping-pipeline,onboard-detection,surmap,packages}/*/docs/*.md`
- Changeset: `docs/<area>/1-WIP/*.md`
- Investigation docs: `docs/<area>/investigations/*.md`

List the relevant documents at the top of the report, so the developer can see what the fixes were aligned to.

## Workflow

### 1. Identify Failing Tests

**First, run all tests to identify failures:**
```bash
uv run pytest -q
```

Note all failing test files and specific test names.

### 2. Execute Tests One at a Time

For each failing test, run it individually with debug logging:

```bash
cd packages/package-name
DEBUG=* uv run pytest -q
```

**Benefits of focused execution:**
- Isolate specific failure without noise from other tests
- Full debug output for single test
- Easier to identify root cause
- Clear understanding of test behavior

### 3. Analyze Each Failure

For each failing test, systematically investigate:

**Step 1: Is there a core production issue?**
- Analyze error message carefully
- Review stack trace for root cause location
- Identify production code bug or missing functionality
- Use debug output to understand execution flow

**Step 2: Is the test code insufficient/flawed?**
- Does test follow `.agents/skills/tdd/references/testing-practices.md` standards?
- Is test deterministic (no conditional logic)?
- Does test have proper setup/teardown?
- Are assertions correct and meaningful?
- Does test have try/catch workarounds?

**Step 3: Is the test relevant and necessary?**
- Does test cover actual requirement?
- Is test duplicated elsewhere?
- Should test be removed or refactored?

**Step 4: Are additional tests needed?**
- Are there coverage gaps revealed by failure?
- Are edge cases missing?
- Should complementary tests be added?

### 4. Apply Focused Fixes

**On Muse**: delegate the fixing work to the `bug-fixer` subagent (`.muse/agents/bug-fixer.md`),
passing it the items below. It implements the fix, verifies with DEBUG enabled, cleans up debug code,
and reports completion.

**On other harnesses**: apply the fixes yourself — the `testing` skill folds in the same behaviour.

Once root cause is identified for each test, apply the fix in the same priority order:

- Root cause analysis from diagnostics
- Debug output findings
- Specific test file and test name
- Priority: Production code bugs → Test infrastructure → Test code → Coverage gaps

The focused fixing workflow should:
- Implement the fix with extensive logging
- Verify each fix by running tests with DEBUG enabled
- Clean up debug code
- Report completion with verification results

**Repeat for each failing test** until all tests pass.

### 5. Use Debug Tools Extensively

Leverage debug capabilities:
- `DEBUG=*` - Enable all debug logging
- `DEBUG=namespace:*` - Enable specific namespace logging
- Logging tools from the `debug` package (`createLogger`)
- Visual inspection if stuck
- Test isolation (already doing this)

**Example debug patterns:**
```bash
# Full debug output
DEBUG=* uv run pytest -q

# Package-specific debug
DEBUG=onboard-detection:* uv run pytest -q

# Multiple namespaces
DEBUG=surmap.slam:*,surmap.geometry:* uv run pytest -q
```

### 6. Validate Alignment with Standards

Ensure all fixes comply with `.agents/skills/tdd/references/testing-practices.md`:
- ❌ No conditional test logic (if/else, switch)
- ❌ No try/catch workarounds
- ❌ No fallback assertions
- ❌ No test-specific production code branches
- ✅ 100% deterministic behavior
- ✅ Single assertion path per test
- ✅ Clear failure modes
- ✅ Tests fail for right reasons

### 7. Improve Code Quality

Ensure fixes enhance overall quality:
- Production code correctness and clarity
- Test-support code reliability
- Test code clarity and maintainability
- System robustness

## After Each Test is Fixed

Verify each fix, and confirm:
- ✅ Test passes consistently
- ✅ Debug output is clean
- ✅ No workarounds added
- ✅ Fix addresses root cause (not symptoms)

## After All Tests are Fixed

Clean up debug code for each fix, then perform final verification:

**Verify all tests pass together:**
```bash
uv run pytest -q
```

Ensure:
- ✅ All tests passing
- ✅ No skipped tests (without good reason)
- ✅ No flaky tests
- ✅ All debug code removed
- ✅ Production code clean
- ✅ Fixes address root causes, not symptoms

## Output Format

When returning results, provide:

```markdown
## 🔍 Focused Test Fix Summary

### Investigation Approach
- **Execution**: One test at a time
- **Debug logging**: Enabled (DEBUG=*)
- **Total tests analyzed**: X
- **Initially failing**: Y
- **Fixing**: Applied directly in priority order

### Test-by-Test Diagnostics

#### Test 1: "should do X" (file:line)
**Failure**: [error message]
**Root cause**: [production bug | test issue | both]
**Debug findings**: [key insights from debug output]
**Result**: ✅ Passing (verified with DEBUG enabled)

#### Test 2: "should do Y" (file:line)
**Failure**: [error message]
**Root cause**: [description]
**Debug findings**: [key insights]
**Result**: ✅ Passing (verified with DEBUG enabled)

[Continue for each test...]

### Fixes Applied

#### Production Code Fixes
- [x] Fixed bug in `functionName` (file:line)
  - Issue: [description]
  - Fix: [description]
  - Debug insight: [what debug output revealed]

#### Test Infrastructure Fixes
- [x] Fixed test helper `helperName` (file:line)
  - Issue: [description]
  - Fix: [description]

#### Test Implementation Improvements
- [x] Improved test "should do X" (file:line)
  - Issue: [description]
  - Fix: [description]

#### Additional Tests Added
- [x] Added test for edge case (file:line)
  - Coverage gap: [what was missing]

### Test Quality Validation
- ✅ No conditional logic
- ✅ No try/catch workarounds
- ✅ No fallback assertions
- ✅ All tests deterministic
- ✅ Single assertion paths
- ✅ Tests fail for right reasons

### Debug Code Cleanup
- [x] Removed X console.log statements
- [x] Removed Y temporary logging calls
- [x] Restored production code quality
- [x] Verified clean test output

### Final Test Results
```bash
uv run pytest -q
```

**Status**: ✅ All Passing

- Passing: X tests
- Failing: 0 tests
- Skipped: Z tests (with reasons)

### Debug Insights Summary
Key findings from debug logging:
1. [Important insight 1]
2. [Important insight 2]
3. [Important insight 3]

### Workflow Used
1. Focused diagnostics (one test at a time with DEBUG=*)
2. Root cause identification for each failure
3. Applied focused fixes in priority order
4. Verified all tests passing

### Next Steps
[Recommendations for proceeding]
```

## Update Documentation

If changeset exists, update "Validation Results":
```markdown
### Test Fixes (`/fix-tests`-focused)
**Last Run**: YYYY-MM-DD
**Status**: ✅ All Passing

**Approach**: Focused diagnostics with debug logging, fixes applied in priority order

**Summary**:
- Tests diagnosed: X (one at a time with DEBUG=*)
- Root causes identified: Y
- All fixes verified: ✅
- Debug insights: [key findings]
```

## Common Failure Patterns

### Pattern 1: Async Timing Issues
**Symptom**: Test passes sometimes, fails other times
**Debug approach**: Enable async operation logging
**Fix**: Use `-eventually` or proper async/await

### Pattern 2: Test Order Dependencies
**Symptom**: Test fails with others, passes alone
**Debug approach**: Check debug output for shared state
**Fix**: Ensure proper test isolation and cleanup

### Pattern 3: Mock/Stub Issues
**Symptom**: Test expects mocked data, real data returned
**Debug approach**: Log mock setup and invocations
**Fix**: Verify mock setup or remove unnecessary mocking

### Pattern 4: Environment Dependencies
**Symptom**: Test passes locally, fails in CI
**Debug approach**: Compare debug output in both environments
**Fix**: Remove environment-specific assumptions

### Pattern 5: Event Handler Issues
**Symptom**: Multiple listeners causing conflicts
**Debug approach**: Log event registrations and invocations
**Fix**: Namespace event handlers properly

## Best Practices

✅ **Do:**
- Execute tests one at a time for focus
- Enable full debug logging (DEBUG=*)
- Analyze debug output carefully for root cause
- Apply fixes in priority order: production code → test infrastructure → test code
- Verify each fix addresses the root cause, not the symptom
- Follow `.agents/skills/tdd/references/testing-practices.md` standards
- Document key debug insights

❌ **Don't:**
- Don't run multiple tests together until all diagnosed
- Don't skip debug logging analysis
- Don't proceed to next test until fix verified
- Don't accept workarounds in place of a root-cause fix
- Don't ignore test quality issues

## Critical Reminders

1. **One test at a time** - Focus diagnostics for clarity
2. **Debug logging enabled** - Use DEBUG=* for full visibility
3. **Analyze debug output** - Debug logs reveal root causes
4. **Fix in priority order** - production code bugs before test code
5. **Verify root cause** - Ensure fixes address cause, not symptoms
6. **Standards compliance** - Verify each fix follows `.agents/skills/tdd/references/testing-practices.md`

## Related

**Rules**:
- `.agents/skills/tdd/references/testing-practices.md` - Testing quality standards
- `.agents/skills/coding/references/coding-practices.md` - Production code quality
- `docs/architecture.md` - `debug` logging usage
