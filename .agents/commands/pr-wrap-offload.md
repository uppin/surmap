---
description: PR preparation using offline_dev MCP for external validation
---
## PR Wrap Offload - External Validation

This command performs PR preparation using offline_dev MCP tool to clone codebase externally and perform validation in isolation.

**Note**: This command requires offline_dev MCP tool to be available.

**Not a `## Workflow` row.** It validates in an external clone and reports; it neither wraps the
docs nor closes the changeset's Wrap row, which stays `/pr-wrap`'s (step contract:
`.agents/skills/pr-lifecycle/SKILL.md`). It names no successor command.

## Prerequisites

- offline_dev MCP tool must be available
- Current changes should be committed
- Repository should be accessible for cloning

## Workflow

### 1. Verify offline_dev Availability

Check if offline_dev MCP tool is available:
- Tool can clone repository
- Tool can run validation commands
- Tool has necessary permissions

### 2. Clone Codebase Externally

Use offline_dev to clone current branch:
- Clone to external working directory
- Preserve current branch state
- Avoid switching branches in main repo

### 3. External Validation Sequence

**In external clone, run:**

#### A. Validate Changes
```bash
# In external directory
# Note: validate-changes is now a command (/validate-changes), not a script
# Run it through the AI assistant instead
```
Analyze code changes, risks, testing infrastructure.

#### B. Validate Tests
```bash
# Note: validate-tests is now a command (/validate-tests), not a script
# Run it through the AI assistant instead
```
Check test quality, anti-patterns, determinism.

#### C. Production Readiness
```bash
uv run pytest -q && uv run ruff check src tests && uv run mypy
```
Remove mocks, fallbacks, ensure production standards.

#### D. Code Quality Analysis
```bash
# Note: analyze-clean-code is now a command (/analyze-clean-code), not a script
# Run it through the AI assistant instead
```
Assess code quality, identify improvements.

#### E. Refactor
```bash
uv run ruff check src tests
```
Implement quality improvements.

### 4. Collect Results

Gather validation results from external clone:
- Change validation report
- Test quality report
- Production readiness status
- Code quality metrics
- Refactoring summary

### 5. Apply Learnings to Main Repo

Based on external validation:
- Identify issues in main repo
- Apply necessary fixes
- Improve code quality
- Update documentation

### 6. Prevent Branch Switching

**CRITICAL**: Never switch branches during process:
- Keep main repo on current branch
- All validation happens externally
- Apply fixes to current branch only

## Benefits

### External Validation Advantages
- ✅ No branch switching required
- ✅ Isolated environment for testing
- ✅ Fresh clone ensures clean state
- ✅ Can run destructive operations safely
- ✅ Parallel validation possible

### Use Cases
- When branch switching is problematic
- When need clean environment
- When validating destructive operations
- When testing from fresh clone

## Output Format

```markdown
## 🔄 PR Wrap Offload - External Validation Complete

### External Clone
**Working Directory**: [external path]
**Branch**: [current branch]
**Commit**: [current commit hash]

### Validation Results

#### 1. Change Validation
**Status**: ✅ Passed | ⚠️ Warnings | ❌ Issues
- Risk level: [Low/Medium/High]
- Critical issues: X
- Test impact: Y tests affected

#### 2. Test Validation
**Status**: ✅ Passed | ⚠️ Warnings | ❌ Issues
- Tests analyzed: X
- Anti-patterns found: Y
- Quality: [Good/Fair/Poor]

#### 3. Production Readiness
**Status**: ✅ Ready | ⚠️ Gaps | ❌ Blockers
- Mock code removed: X instances
- Fallbacks removed: Y instances
- Blockers: [list or none]

#### 4. Code Quality
**Status**: ✅ Good | ⚠️ Fair | ❌ Poor
- Overall score: X/10 ⭐
- Critical issues: Y
- Improvements needed: Z

#### 5. Refactoring
**Status**: ✅ Complete | ⚠️ Partial | ⏭️ Skipped
- Score improvement: X/10 → Y/10
- Issues fixed: Z

### Issues to Address in Main Repo

#### Critical
- [ ] Issue 1: [description] (file:line)
- [ ] Issue 2: [description] (file:line)

#### Major
- [ ] Issue 3: [description] (file:line)

#### Minor
- [ ] Issue 4: [description] (file:line)

### Comprehensive Change Summary

**Files Changed**: X files
**Quality Improvement**: Y/10 → Z/10 ⭐
**Production Ready**: ✅ Yes | ⚠️ Gaps | ❌ No

**From External Validation:**
- All checks run in isolated environment
- No branch switching in main repo
- Clean state validation complete

### Remaining in the main repo

1. **Address issues** in main repo (current branch)
2. **Apply fixes** based on validation findings
3. **Re-validate** in main repo

**External validation complete**: ✅
**Main repo ready for fixes**: ✅
**Branch switching avoided**: ✅
```

## Detailed Process

### Clone and Validate

```bash
# Using offline_dev MCP tool
offload_dev {
  "repoPath": "/Users/user/Code/project",
  "contextFiles": [
    "src/changed-file1.ts",
    "src/changed-file2.ts"
  ],
  "prompt": "Run complete PR validation workflow"
}
```

Tool executes externally:
1. Clones repository
2. Checks out current branch
3. Runs validation commands
4. Collects results
5. Reports back

### Apply Findings

In main repository:
1. Review external validation results
2. Fix identified issues
3. Improve code quality
4. Update tests
5. Verify fixes

No branch switching required.

## Comparison: pr-wrap vs pr-wrap-offload

### /pr-wrap (Standard)
- Runs in current repository
- May require branch switching
- Direct file access
- Faster for simple cases

### /pr-wrap-offload (External)
- Runs in external clone
- No branch switching
- Isolated validation
- Better for complex cases
- Safer for destructive operations

Choose based on needs and tool availability.

## Best Practices

✅ **Do:**
- Verify offline_dev availability first
- Let tool handle cloning
- Collect comprehensive results
- Apply findings systematically
- Avoid branch switching in main repo

❌ **Don't:**
- Don't switch branches during process
- Don't skip external validation results
- Don't apply changes without reading the external findings
- Don't proceed if tool unavailable

## Related

**Related Commands**: `/validate-changes`, `/validate-tests`, `/validate-prod-ready`
**Commands**: `/pr-wrap` (standard approach), `/pr`
**Tools**: offline_dev MCP tool
