---
description: Create comprehensive knowledge base articles
---
## Create Knowledge Base Article

This command guides creation of comprehensive KB articles documenting technical processes, migrations, troubleshooting, and lessons learned.

## KB Article Structure

### 1. Header Metadata

```markdown
# [Title - Clear and Descriptive]

**Document Type**: Knowledge Base Article
**Created**: YYYY-MM-DD
**Status**: Draft | Review | Production Ready
**Applies To**: [Technologies, processes, or teams]
```

### 2. Required Sections

#### Overview
- Brief summary of article content
- Context and background
- When this documentation is useful

#### Table of Contents
- Numbered sections for navigation
- Include all major sections and subsections

#### Main Content

**Structure based on article type:**

**Process Documentation:**
- Background/Context
- Step-by-step procedures
- Configuration examples
- Validation steps

**Migration Guides:**
- Migration rationale
- Before/after comparisons
- Step-by-step migration process
- Rollback procedures
- Validation and testing

**Troubleshooting Guides:**
- Problem symptoms
- Root cause analysis
- Solution implementation
- Prevention strategies

#### Lessons Learned
- Key insights and takeaways
- What worked well and what didn't
- Recommendations for future work

#### Best Practices
- Recommended approaches
- Configuration examples
- Code snippets with proper formatting

#### Troubleshooting Guide
- Common issues and symptoms
- Diagnostic steps
- Solutions with examples
- When to escalate

### 3. Footer Information

```markdown
---

**Last Updated**: YYYY-MM-DD
**Next Review**: YYYY-MM-DD
**Maintainers**: [Team/Individual]
```

## Content Guidelines

### Technical Accuracy
- Include specific version numbers, commit hashes, timestamps
- Provide exact error messages and symptoms
- Include complete configuration examples
- Validate all code snippets and commands

### Code Documentation
- Use appropriate syntax highlighting
- Include complete, runnable examples
- Add comments explaining complex logic
- Show before/after comparisons for changes

### Error Documentation
- Include full error messages
- Document error symptoms and diagnostic steps
- Provide step-by-step solution procedures
- Include validation steps to confirm fixes

### Migration Documentation
- Document migration rationale
- Include before/after state comparisons
- Provide complete migration steps with validation
- Document rollback procedures
- Include testing and verification steps

## Location

All KB articles go in: `docs/<area>/kb/`

**Naming convention**: `docs/<area>/kb/descriptive-name.md`

## Example KB Article

```markdown
# Replaying a Recorded Survey Session in Tests

**Document Type**: Knowledge Base Article
**Created**: 2025-01-12
**Status**: Production Ready
**Applies To**: Session replay, `src/surmap/slam/`, pytest

## Overview

This article documents how a session recorded on the drone (stereo pairs +
GPS checkpoints, architecture §5 format) is replayed on the base station and
in tests, so a mapping defect found in the field can be reproduced from the
recording alone. It includes the rationale, the replay procedure, common
issues, and prevention strategies.

## Table of Contents

1. Overview
2. Rationale
3. Before and After
4. Replay Steps
5. Common Issues
6. Lessons Learned
7. Best Practices

## Rationale

- A field failure without its session is not reproducible — the recording
  is the bug report.
- Replay must be indistinguishable in format from live capture
  (`docs/architecture.md` §2.3), so one pipeline serves flight and tests.
- Tests drive the SLAM port through `InMemorySlamBackend`; the native
  RTAB-Map binding is never required in CI.

## Before and After

### Before (ad-hoc, hardware-bound)

```python
def test_map() -> None:
    backend = RtabmapBackend("flight.db")  # needs a system RTAB-Map install
    ...
```

### After (replay through the port)

```python
def test_recorded_session_places_the_parked_car() -> None:
    session = load_session_fixture("car-park")  # stereo pairs + GPS, §5 format
    result = run_pipeline(session, backend=InMemorySlamBackend())
    assert result.static_layer.contains(label="car")
```

## Replay Steps

### Step 1: Fetch the session

```bash
uv run pytest -q -k replay   # recorded sessions under tests/fixtures/
```

### Step 2: Replay with the in-memory backend

[Detailed steps with frame/checkpoint examples]

### Step 3: Compare against ground truth

[Position tolerance, layer membership, track identity]

### Step 4: Validation

```bash
uv run pytest -q
uv run ruff check src tests
uv run mypy
```

## Common Issues

### Issue 1: Session produces an empty static layer

**Symptom**: Replay completes, no static points.

**Cause**: The RTAB-Map binding is absent (`RtabmapUnavailable` swallowed
upstream) or the session's `calibration_id` has no calibration record.

**Solution**: Replay through `InMemorySlamBackend` to isolate geometry from
the native adapter; surface, never swallow, the unavailable-binding error.

## Lessons Learned

### What Worked Well

- Replaying one session end to end before adding synthetic sessions
- Asserting layer membership (static vs moving track), not internals

### What Didn't Work

- Reproducing from a description instead of the recording
- Letting a test depend on the reviewer's RTAB-Map install

### Recommendations

1. Start with the shortest failing session
2. Keep the gates green between steps
3. Record the model ID (`detector_model_id`) with every fixture

## Best Practices

### Assertion priority

1. Map outcome — object in the right layer at the right position
2. Track identity over time
3. Contract fields (`frame_id`, `t_ns`, `calibration_id`)
4. Internal call counts — last resort

### Determinism

```python
# Fixed timestamps and calibration; recorded detector output, never a live model
frame = StereoFramePair(1, 1_000_000, "left.png", "right.png", "cal-1")
```

---

**Last Updated**: 2025-01-12
**Next Review**: 2025-04-12
**Maintainers**: Survey pipeline team

```

## Output Format

```markdown
## 📚 Knowledge Base Article Created

### Article Details
- **Title**: [article title]
- **Location**: `docs/<area>/kb/article-name.md`
- **Type**: [Process/Migration/Troubleshooting]
- **Status**: Draft

### Content Summary

**Overview**: [Brief summary]

**Sections**:
- [x] Header metadata
- [x] Overview and TOC
- [x] Main content (X sections)
- [x] Lessons learned
- [x] Best practices
- [x] Troubleshooting guide
- [x] Footer information

**Technical Details:**
- Version numbers included: ✅
- Code examples: X snippets
- Error messages documented: Y cases
- Before/after comparisons: Z examples

### Quality Checklist
- [x] Technical accuracy verified
- [x] All code snippets tested
- [x] Complete examples provided
- [x] Proper syntax highlighting
- [x] Clear section structure
- [x] Maintainer identified

### Next Steps
1. Review article for accuracy
2. Update status to "Review"
3. Incorporate feedback
4. Mark as "Production Ready"

**Article ready for review**: ✅
```

## Best Practices

✅ **Do:**
- Use clear, descriptive titles
- Include specific version numbers
- Provide complete, runnable examples
- Add comments to complex code
- Show before/after comparisons
- Document lessons learned
- Include troubleshooting section
- Specify maintainer

❌ **Don't:**
- Don't skip table of contents
- Don't use vague descriptions
- Don't provide partial examples
- Don't forget validation steps
- Don't skip footer metadata
- Don't leave status as draft indefinitely

## Related

**Rules**: `.agents/skills/planning/references/dev-doc.md`, `.agents/skills/planning/references/feature-doc.md`
