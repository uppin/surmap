---
description: Persist complete conversation to docs/temporary for analysis
---
## Persist Full Conversation

This command captures and stores complete conversation exchanges for documentation and analysis.

## Purpose

Save conversations for:
- Documentation reference
- Analysis of problem-solving approaches
- Training and knowledge sharing
- Audit trail of technical decisions

## Location

All conversation logs saved in: `docs/temporary/`

**Naming**: `docs/temporary/conversation-YYYY-MM-DD-HH-MM.md`

## Conversation Format

```markdown
# Conversation Log - [Brief Topic]

**Date**: YYYY-MM-DD HH:MM
**Duration**: [conversation duration]
**Topic**: [main topic discussed]
**Outcome**: [what was accomplished]

---

## Conversation Exchange

### User [HH:MM]
[Exact user message]

### Assistant [HH:MM]
[Exact assistant response]

### User [HH:MM]
[Next user message]

### Assistant [HH:MM]
[Next assistant response]

[Continue for entire conversation...]

---

## Summary

### Topics Covered
- Topic 1
- Topic 2

### Actions Taken
- Action 1
- Action 2

### Files Modified
- `path/to/file1.ts` - [changes]
- `path/to/file2.ts` - [changes]

### Commands Executed
```bash
command1
command2
```

### Key Decisions
1. Decision 1: [rationale]
2. Decision 2: [rationale]

### Outcomes
- Outcome 1
- Outcome 2

### Follow-up Items
- [ ] Follow-up task 1
- [ ] Follow-up task 2
```

## Content Requirements

### Word-for-Word Accuracy
- Capture complete user messages
- Capture complete assistant responses
- Include timestamps for each message
- Preserve formatting and code blocks

### Proper Organization
- Chronological message order
- Clear speaker labels (User/Assistant)
- Timestamps for context
- Section breaks for readability

### Summary Section
- High-level overview
- Topics discussed
- Actions taken
- Files modified
- Commands executed
- Key decisions made
- Outcomes achieved
- Follow-up items

## Output Format

```markdown
## 💾 Conversation Persisted

### Conversation Log Details
- **File**: `docs/temporary/conversation-YYYY-MM-DD-HH-MM.md`
- **Duration**: [X minutes]
- **Messages**: [Y exchanges]

### Content Summary

**Main Topic**: [topic]

**Key Points:**
1. Point 1
2. Point 2

**Actions Taken:**
- Action 1
- Action 2

**Files Modified:**
- `file1.ts` - [description]
- `file2.ts` - [description]

**Commands Run:**
```bash
command1
command2
```

### Outcomes
- ✅ Outcome 1
- ✅ Outcome 2

### Follow-up Items
- [ ] Task 1
- [ ] Task 2

**Conversation log saved**: ✅

### Usage
This conversation log can be used for:
- Reference documentation
- Knowledge sharing
- Technical decision audit trail
- Training examples
```

## Example Conversation Log

```markdown
# Conversation Log - Stereo Reconstruction Implementation

**Date**: 2025-01-12 14:30
**Duration**: 45 minutes
**Topic**: Implementing stereo pairs to map-frame points
**Outcome**: Successfully implemented and tested stereo reconstruction feature

---

## Conversation Exchange

### User [14:30]
I need to implement stereo pairs to map-frame points using the surmap.geometry library.

### Assistant [14:30]
I'll help you implement stereo pairs to map-frame points. Let's start by:
1. Creating the rendering function
2. Adding proper error handling
3. Writing tests

First, let me create the implementation...

[Full conversation continues...]

---

## Summary

### Topics Covered
- stereo reconstruction implementation
- Error handling strategies
- Test creation
- Performance optimization

### Actions Taken
1. Created `to_map_frame()` function
2. Added comprehensive error handling
3. Wrote unit and integration tests
4. Optimized for performance

### Files Modified
- `packages/reconstruction/src/renderer.ts` - Core implementation
- `packages/reconstruction/src/renderer.test.ts` - Unit tests
- `packages/reconstruction/src/renderer.it.test.ts` - Integration tests

### Commands Executed
```bash
uv run mypy
uv run pytest -q
uv run ruff check src tests
```

### Key Decisions
1. **Use surmap.geometry over session fixtures**: Better performance for our use case
2. **Image format PNG**: Better quality than JPEG for documents
3. **DPI setting 300**: Balance between quality and file size

### Outcomes
- ✅ stereo reconstruction implemented
- ✅ All tests passing
- ✅ Error handling comprehensive
- ✅ Performance optimized

### Follow-up Items
- [ ] Add progress callback for long sessions
- [ ] Implement caching mechanism
- [ ] Add support for custom DPI
```

## When to Use

Persist conversation when:
- User requests conversation documentation
- Long technical discussion needs recording
- Complex problem-solving session
- Important decisions made
- Training material needed
- Audit trail required

## Best Practices

✅ **Do:**
- Capture complete messages
- Include timestamps
- Preserve formatting
- Add comprehensive summary
- Include all files modified
- Document key decisions
- List follow-up items

❌ **Don't:**
- Don't omit or summarize messages
- Don't skip timestamps
- Don't lose code block formatting
- Don't forget summary section
- Don't skip command documentation

## Related

**Rules**: `.agents/skills/planning/references/dev-doc.md`
**Commands**: `/investigate`, `/visual-inspection`
