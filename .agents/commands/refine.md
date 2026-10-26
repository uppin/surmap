---
description: Improve implementation based on user feedback
---
## Refine Implementation

This command handles user dissatisfaction with implementation by improving quality across multiple dimensions.

## Intent

User is not happy with the last output and wants to refine the implementation.

## Workflow

### 1. Understand User's Concern

**If user specified improvement:**
- Focus on that specific aspect
- Address the stated concern

**If reason not specified:**
- Ask for clarification
- Or proceed with general quality improvements

### 2. Improvement Dimensions

Evaluate and improve across these areas:

#### A. Coding Practices (`.agents/skills/coding/references/coding-practices.md`)
- Production-ready code quality
- Permanent solutions (not temporary fixes)
- No fallbacks without consent
- Proper TODO/FIXME annotations
- No code branches for test-only behavior
- Identical behavior in test and production

#### B. Testing Practices (`.agents/skills/tdd/references/testing-practices.md`)
- 100% deterministic tests
- No conditional logic in tests
- No try/catch workarounds
- No fallback assertions
- Tests that reliably indicate production issues
- Single assertion path per test

#### C. Repository Structure (`.agents/skills/planning/references/repo-structure.md`)
- Commands available from root
- File naming conventions correct
- Test files properly named (*.test.ts, *.it.test.ts, *.e2e.test.ts)
- Package structure consistent
- Typing (mypy strict) and contract usage

#### D. Tech Stack (`.agents/skills/tech-stack/references/tech-stack.md`)
- Technology decisions aligned
- Integration patterns followed
- Development environment correct
- Proper tool usage

### 3. Analyze Current Implementation

**Review recent changes:**
- What was implemented?
- What issues exist?
- What can be improved?

**Run checks:**
```bash
uv run pytest -q
uv run pytest -q
uv run pytest -q
```

### 4. Apply Improvements

**Priority order:**
1. **Critical issues**: Fix bugs, violations, failures
2. **Major improvements**: Code quality, test reliability
3. **Minor enhancements**: Cleanup, optimization

**For each dimension:**
- Identify violations or issues
- Fix systematically
- Verify improvements

### 5. Validate Improvements

**Run all checks again:**
```bash
uv run pytest -q
uv run pytest -q
uv run pytest -q
```

Ensure all passing.

## Output Format

```markdown
## ✨ Implementation Refined

### User Concern
[User's stated concern or "General quality improvement"]

### Analysis Performed

#### Coding Practices
**Issues Found**:
- Issue 1: [description]
- Issue 2: [description]

**Fixed**:
- [x] Removed fallback code at file:line
- [x] Added proper error handling at file:line
- [x] Fixed test-specific branch at file:line

#### Testing Practices
**Issues Found**:
- Test 1: Conditional logic
- Test 2: Fallback assertion

**Fixed**:
- [x] Removed conditional logic from test at file:line
- [x] Split test into 2 deterministic tests
- [x] Removed try/catch workaround

#### Repository Structure
**Issues Found**:
- File naming: Wrong convention
- Package structure: Missing exports

**Fixed**:
- [x] Renamed test file to match convention
- [x] Updated package exports

#### Tech Stack
**Issues Found**:
- Technology misalignment
- Integration pattern violation

**Fixed**:
- [x] Aligned with tech stack standards
- [x] Fixed integration pattern

### Changes Made

**Files Modified**:
- `file1.ts` - [improvements]
- `file2.test.ts` - [improvements]
- `file3.ts` - [improvements]

**Quality Improvements**:
- Code quality: [before] → [after]
- Test reliability: [before] → [after]
- Structure: [issues fixed]
- Tech stack alignment: ✅

### Validation Results

**Linting**: ✅ Passing
**Type Checking**: ✅ Passing
**Tests**: ✅ All passing (X tests)

**Quality Metrics**:
- Functions within standards: ✅
- Tests deterministic: ✅
- Structure compliant: ✅
- Tech stack aligned: ✅

### Summary

**Before refinement**:
- Issues: X
- Quality score: Y/10

**After refinement**:
- Issues fixed: X
- Quality score: Z/10
- Improvement: +N points

**Implementation quality**: ✅ Improved

### Remaining
[If further refinement needed: specify areas — otherwise "none"]
```

## Example

```markdown
## ✨ Implementation Refined

### User Concern
"The tests are flaky and production code has fallbacks"

### Analysis Performed

#### Coding Practices
**Issues Found**:
- Fallback code in production for test environment
- Mock implementation in production file

**Fixed**:
- [x] Removed test fallback from `src/handler.ts:45`
- [x] Removed mock implementation from `src/api.ts:23`
- [x] Added proper error handling instead

#### Testing Practices
**Issues Found**:
- Test using conditional logic (if/else)
- Try/catch hiding failures
- Fallback assertion "just in case"

**Fixed**:
- [x] Split conditional test into 2 focused tests
- [x] Removed try/catch, let failures show
- [x] Removed fallback assertion
- [x] Made all tests 100% deterministic

### Changes Made

**Files Modified**:
- `src/handler.ts` - Removed test fallback, added real error handling
- `src/api.ts` - Removed mock, added production implementation
- `src/handler.test.ts` - Fixed conditional logic, made deterministic
- `src/api.test.ts` - Removed try/catch workaround

**Quality Improvements**:
- Code quality: 5/10 → 8/10
- Test reliability: Flaky → 100% deterministic
- Production readiness: 60% → 95%

### Validation Results
✅ Linting: Passing
✅ Type Checking: Passing
✅ Tests: All 24 passing (no flaky tests)

**Implementation quality**: ✅ Production-ready
```

## When to Use

Use `/refine` when:
- User unhappy with implementation
- Code quality below standards
- Tests unreliable or flaky
- Structure violations exist
- Tech stack misalignment

## Best Practices

✅ **Do:**
- Understand user's specific concern
- Evaluate all quality dimensions
- Fix issues systematically
- Validate all improvements
- Run complete test suite
- Ensure production readiness

❌ **Don't:**
- Don't guess at user's concern
- Don't skip validation
- Don't ignore failing tests
- Don't leave violations unfixed
- Don't compromise quality for speed

## Related

**Rules**: `.agents/skills/coding/references/coding-practices.md`, `.agents/skills/tdd/references/testing-practices.md`, `.agents/skills/planning/references/repo-structure.md`, `.agents/skills/tech-stack/references/tech-stack.md`
**Related**: Skill `code-cleaning` (`.agents/skills/code-cleaning/SKILL.md`; on Muse, the `refactor` subagent), Commands `/validate-changes`, `/validate-tests`, `/validate-prod-ready`
