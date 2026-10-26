---
description: Run and validate acceptance criteria tests
---
## Test Acceptance Criteria

This command validates acceptance criteria defined in development documentation by running acceptance tests.

## Prerequisites

Development documentation with acceptance tests:
- Changeset: `docs/<area>/1-WIP/YYYY-MM-DD-changeset.md`
- Feature/PRD docs with acceptance criteria

## Workflow

### 1. Identify Acceptance Tests

Read the changeset's "Acceptance Tests" section (what each test is) and its TODOs under the Green row
(or the kind's implementing row) — the only place their checkboxes live:
```markdown
- [wf 3] ⏳ `/green` Green — implement until every red test passes ·
  - [ ] Acceptance: **E2E/Integration/Unit** Test description (test-file.test.ts)
```

### 2. Run Acceptance Tests

For each test file:
```bash
cd packages/package-name
uv run pytest -q
```

Or run all tests:
```bash
uv run pytest -q
```

### 3. Analyze Results

For each acceptance test:
- ✅ **Passing**: Tick its TODO under the row
- ❌ **Failing**: Identify root cause
- ⏭️ **Skipped**: Identify why skipped

### 4. Update Changeset Status

Tick passing tests' TODOs; a failing one stays open, its reason and next action in this command's
report (not in the changeset):
```markdown
  - [x] Acceptance: **E2E** Test description (test-file.test.ts)
  - [ ] Acceptance: **Integration** Test description (test-file.test.ts)
```

### 5. Verify Acceptance Criteria

Cross-reference with feature/PRD document:
- Are all acceptance criteria covered by tests?
- Are all tests passing?
- Any gaps in coverage?

## Output Format

```markdown
## Acceptance Test Results

**Overall Status**: ✅ All Passing | ⚠️ Some Failing | ❌ Multiple Failures

### surmap
- [x] **E2E**: Complete workflow test ✅
- [x] **Integration**: Service integration test ✅
- [ ] **Unit**: Edge case handling ❌
  - Reason: Edge case not properly handled
  - Action: Fix edge case logic in src/handler.ts

### surmap
- [x] **Integration**: Database operations ✅

**Summary**:
- Total tests: 4
- Passing: 3
- Failing: 1
- Coverage: 75% acceptance criteria met

**Next actions**:
1. Fix edge case handling in package-1
2. Re-run failing test
3. Verify all criteria met
```

## Update Documentation

**If changeset exists**: Update "Validation Results" section:
```markdown
### Test Acceptance (`/test-acceptance`)
**Last Run**: YYYY-MM-DD
**Status**: ✅ Passed | ⚠️ Partial | ❌ Failed
**Results**: X/Y tests passing
```

**If feature/dev doc exists**: Update acceptance criteria status

## When All Tests Pass

This is a check, not a `## Workflow` row: it records its result in `## Validation Results` and
leaves the `[wf]` rows (`.agents/skills/pr-lifecycle/SKILL.md`) to the commands that own the
rows. Print:
```
✅ All acceptance criteria validated!

Changeset: docs/<area>/1-WIP/YYYY-MM-DD-changeset.md
Test results: X/X passing
Workflow: next row <k> <step> — `<Run with>` (the skill's next-row grep)
```

## Best Practices

✅ **Do:**
- Run all acceptance tests, not just some
- Update changeset with actual results
- Investigate failing tests thoroughly
- Cross-reference with acceptance criteria

❌ **Don't:**
- Don't skip failing tests without fixing
- Don't mark tests as passing if they're flaky
- Don't ignore test warnings
- Don't report the criteria as met with failing tests

## Related

**Rules**: `.agents/skills/tdd/references/testing-practices.md`, `.agents/skills/planning/references/dev-doc.md`, `.agents/skills/planning/references/feature-doc.md`, `.agents/skills/pr-lifecycle/references/prd.md`
**Related Commands**: `/validate-changes`, `/validate-tests`, `/validate-prod-ready`
**Commands**: `/plan-red` (writes the acceptance tests in its Red row)
