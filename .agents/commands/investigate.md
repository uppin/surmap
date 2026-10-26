---
description: Systematic issue investigation and troubleshooting
---
## Investigate Issue

This command provides structured approach to investigating technical issues.

**For TDD troubleshooting workflow, see `.agents/skills/tdd/references/tdd.md` rule.**

## Workflow

### 1. Make Analysis and Plan

Analyze possible causes:
- What is the issue symptom?
- What are potential root causes?
- What are possible fixes?

Create fix plan with prioritized approaches.

### 2. Create Investigation Document

Create `tmp/investigation-YYYY-MM-DD-HH-MM.md`:

```markdown
# Investigation: [Issue Description]

**Date**: YYYY-MM-DD HH:MM
**Issue**: [Brief description]
**Severity**: Critical/High/Medium/Low

## Symptoms
- Symptom 1
- Symptom 2

## Possible Causes
1. Cause 1 (most likely)
2. Cause 2
3. Cause 3

## Investigation Plan
1. [ ] Test hypothesis 1
2. [ ] Test hypothesis 2
3. [ ] Implement fix

## Troubleshooting Steps
[Detail steps taken]

## Findings
[Document discoveries]

## Solution
[Final fix implemented]

## Prevention
[How to prevent in future]
```

Output to User:
```
**CRITICAL FOR CONTEXT & SUMMARY**
Investigation document: tmp/investigation-YYYY-MM-DD-HH-MM.md
```

This helps memorize document in long-running conversations.

### 3. Choose Module for Investigation

**Prefer:** Create new module to not interfere with production
**Alternative:** Use existing module if necessary

### 4. Troubleshooting Sequence

Use TDD methodology (`.agents/skills/tdd/references/tdd.md`):
1. **Red**: Write failing test reproducing issue
2. **Green**: Fix with minimal implementation
3. Iterate red & green for feedback

### 5. Create Verbose Output

Make lots of verbose output to assert:
- What is succeeding
- What is failing
- Progress through investigation

### 6. Time Investigation

Take time from computer time (actual time spent, not wall clock).

## Investigation Document Structure

**Header:**
- Date and time
- Issue description
- Severity

**Analysis:**
- Symptoms observed
- Possible root causes (prioritized)
- Investigation plan with checkboxes

**Process:**
- Steps taken
- Tests created
- Findings discovered

**Resolution:**
- Solution implemented
- Verification steps
- Prevention strategies

## Output Format

```markdown
## 🔍 Investigation Started

### Issue
**Description**: [Issue summary]
**Severity**: [Critical/High/Medium/Low]

### Investigation Document
Created: `tmp/investigation-YYYY-MM-DD-HH-MM.md`

### Analysis
**Symptoms:**
- Symptom 1
- Symptom 2

**Possible Causes (prioritized):**
1. Most likely cause
2. Secondary cause
3. Tertiary cause

### Plan
1. [ ] Test hypothesis 1 - [description]
2. [ ] Test hypothesis 2 - [description]
3. [ ] Implement fix based on findings

### Approach
- **Module**: [new test module | existing module]
- **Method**: TDD (red-green cycle)
- **Output**: Verbose logging enabled

### Next Steps
1. Use `.agents/skills/tdd/references/tdd.md` to iterate through red-green cycles
2. Document findings in investigation document
3. Update progress as investigation proceeds

**Time tracking**: Started at [time]
```

## During Investigation

Track in investigation document:
- [x] Hypothesis tested
- Results observed
- Conclusions drawn
- Next steps identified

Update document frequently with findings.

## After Investigation

Complete investigation document:
```markdown
## ✅ Investigation Complete

### Root Cause
[Description of actual root cause]

### Solution Implemented
[What was fixed]

### Verification
- [x] Issue reproduced successfully
- [x] Fix implemented
- [x] Fix verified working
- [x] Tests passing

### Prevention
- Recommendation 1
- Recommendation 2

**Total Time**: [X hours/minutes]
```

## Best Practices

✅ **Do:**
- Create dedicated investigation document
- Use TDD methodology for systematic testing
- Make verbose output for visibility
- Document all findings
- Track time spent
- Prefer new module for testing
- Update document as investigation proceeds

❌ **Don't:**
- Don't interfere with production code unnecessarily
- Don't skip documentation
- Don't guess without testing
- Don't leave investigation document incomplete
- Don't forget prevention strategies

## Related

**Rules**: `.agents/skills/tdd/references/tdd.md`
**Commands**: `/visual-inspection`
**Commands**: `/red`, `/green`, `/fix-tests`
