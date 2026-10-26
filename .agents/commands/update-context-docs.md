---
description: Auto-update feature and development documentation based on current implementation state
---
# Update Context Documentation

**Purpose**: Automatically update feature and development documentation based on current implementation state, test results, and codebase analysis.

**When to use**: After completing major development milestones, before code reviews, or when documentation needs to reflect current reality.

---

## Command Workflow

### 1. Discovery Phase

**Scan for relevant documentation:**
- **CRITICAL**: Check for PRD documents FIRST in `docs/{product-area}/1-WIP/`
  - If PRD document exists: ONLY modify the PRD document
  - If NO PRD document exists: Modify the original feature document
  - **NEVER modify original feature document if PRD exists**
- Find all dev docs in `{common,common-testing,mapping-pipeline,onboard-detection,surmap,packages}/*/docs/` that reference current work
- Identify feature-dev doc relationships
- Check product area overview: `docs/{product-area}/1-OVERVIEW.md`

**Priority Order for Feature Documentation:**
1. **PRD document** (if exists): `docs/{product-area}/1-WIP/PRD-YYYY-MM-DD-feature-name.md`
2. **Original feature document** (only if no PRD): `docs/{product-area}/feature-name.md`

**Analyze current implementation:**
- Search codebase for completed features (implemented files, functions, classes)
- Identify passing/failing tests (test files, test results)
- Analyze git commits for completed work
- Check session-replay tests for UI implementations
- Review E2E test results

### 2. Feature Documentation Update

**CRITICAL DECISION POINT:**

**IF PRD document exists:**
- ✅ **Update ONLY the PRD document**
- ❌ **DO NOT modify the original feature document**
- PRD document path: `docs/{product-area}/1-WIP/PRD-YYYY-MM-DD-feature-name.md`
- Update "Affected Features" section to reflect which features are impacted
- Update acceptance criteria within the PRD document

**IF NO PRD document exists:**
- ✅ **Update the original feature document**
- Feature document path: `docs/{product-area}/feature-name.md`
- Update acceptance criteria checkboxes normally

**Update acceptance criteria checkboxes:**
- **Search pattern**: Look for `- [ ]` (unchecked) or `- [x]` (checked) patterns
- **Verify implementation**: Check if feature exists in codebase
- **Update status**: Convert `- [ ]` → `- [x]` for implemented features
- **Add completion markers**: Add "✅ Implemented" or "❌ Not Started" status

**Update sections (in PRD OR original feature doc):**
- **Success Criteria**: Mark functional/performance/UX requirements as complete
- **Implementation Phases**: Update phase status (Planning/In Progress/Complete)
- **User Stories**: Mark acceptance criteria as met based on test results
- **Affected Features** (PRD only): List all feature documents being modified

**Preservation Rule:**
- Original feature documents = historical record (DO NOT MODIFY if PRD exists)
- PRD documents = current changes (ALWAYS MODIFY when they exist)

**Example transformation:**
```markdown
<!-- BEFORE -->
### Functional Requirements
- [ ] Text Markup Undo: Highlight, underline, strikethrough undoable via Ctrl+Z
- [ ] Form Field Undo: Form field changes undoable via Ctrl+Z
- [ ] Unified Stack: object-layer operations integrated with motion classification

<!-- AFTER -->
### Functional Requirements
- [x] Text Markup Undo: Highlight, underline, strikethrough undoable via Ctrl+Z ✅
- [x] Form Field Undo: Form field changes undoable via Ctrl+Z ✅
- [x] Unified Stack: object-layer operations integrated with motion classification ✅
```

### 3. Development Documentation Update (`docs/<area>/1-WIP/*.md`, `{common,common-testing,mapping-pipeline,onboard-detection,surmap,packages}/*/docs/*.md`)

**CRITICAL: Changesets are living documents - always update them during development.**

**Tick the rows' TODOs (in changeset documents):**
- **The only checkboxes in a changeset** are the TODOs nested under its `[wf]` rows
  (`  - [ ]` / `  - [x]`, open or done — no `[~]`); Scope, Milestones and Acceptance Tests sections
  carry none (`.agents/skills/pr-lifecycle/SKILL.md` § *Workflow rows*)
- **Find them**: `grep -E '^(- \[wf |  - \[[ x]\] )' "$cs"`
- **Tick** `[ ]` → `[x]` each TODO the codebase demonstrably completed — a milestone whose files
  exist, an acceptance test that passes — under the row this run serves (under `/green`, the Green
  row). Never tick on intent, never untick, and never change a row's status
- **Mapping to rows**: milestones, Scope deliverables and acceptance tests sit under Green (or the
  kind's implementing row); package-doc updates and wrap obligations under Wrap

**Example:**
```markdown
<!-- BEFORE -->
- [wf 3] ⏳ `/green` Green — implement until every red test passes ·
  - [ ] Milestone 1: Command interface and types
  - [ ] Acceptance: `undo-redo.e2e.test.ts` passes

<!-- AFTER (file exists, test green) -->
- [wf 3] ⏳ `/green` Green — implement until every red test passes ·
  - [x] Milestone 1: Command interface and types
  - [ ] Acceptance: `undo-redo.e2e.test.ts` passes
```

**Update implementation milestones (dev docs outside a changeset; in a changeset they are the Green row's TODOs above):**
- **Find all milestone sections** (e.g., `### Milestone 1: Command Interface & Types`)
- **Check deliverables** against codebase (file exists, exports correct types)
- **Mark completed**: Convert `- [ ]` → `- [x]` for completed deliverables
- **Update acceptance criteria**: Mark as complete based on test results

**Add/Update status sections:**
- **Implementation Status**: Current progress percentage, completed/pending tasks
- **Test Results**: E2E/integration/unit test pass/fail counts
- **Known Issues**: Extract from linter errors, TODO comments, failing tests
- **Technical Debt**: Identify code smells, console.log statements, abandoned files

**Update TODO lists:**
- Mark completed tasks as `[x]`
- Add new tasks discovered during analysis
- Re-prioritize based on current needs

**Example transformation:**
```markdown
<!-- BEFORE -->
### Milestone 2: Yjs Document Setup
**Deliverables**:
- [ ] Create `motion.py`
- [ ] Implement `classify_motion` class
- [ ] Set up Y.Doc with metadata and commands
- [ ] Configure Y.UndoManager

**Acceptance Criteria**:
- [ ] Y.Doc initializes correctly
- [ ] Commands can be added to Y.Array

<!-- AFTER -->
### Milestone 2: Yjs Document Setup ✅
**Status**: Complete (2025-11-06)

**Deliverables**:
- [x] Create `motion.py` ✅
- [x] Implement `classify_motion` class ✅
- [x] Set up Y.Doc with metadata and commands ✅
- [x] Configure Y.UndoManager ✅

**Acceptance Criteria**:
- [x] Y.Doc initializes correctly ✅
- [x] Commands can be added to Y.Array ✅

**Evidence**:
- File: `src/surmap/motion.py` (200 lines)
- Tests passing: `test_motion.py` (8/8)
```

### 4. Add Implementation Evidence

**For feature docs:**
- Add links to key implementation files
- Reference E2E tests that prove functionality
- Add session-replay tests URLs for UI features

**For dev docs:**
- Add file paths for implemented deliverables
- Add test file references with pass/fail status
- Add git commit SHAs for completed work
- Add known issues with tracking IDs

### 5. Update Technical Debt Sections

**Scan codebase for:**
- `// TODO:` comments → add to technical debt list
- `// FIXME:` comments → add to known issues
- `// eslint-disable-next-line` → identify code quality issues
- Abandoned files (not imported anywhere) → mark for deletion
- Non-null assertions (`!`) → add runtime guard requirements

**Example technical debt entry:**
```markdown
#### Issue #3: Excessive Console Logging
**Location**: `src/surmap/motion.py`
**Issue**: 25+ console statements in production code
**Risk**: Performance impact, console pollution
**TODO**: Replace with `debug` package logging
**Priority**: High
```

### 6. Update Test Results

**Extract from test runs:**
- Total tests: X passed, Y failed
- Test files: List with pass/fail counts
- Test coverage: Extract from coverage reports
- Performance metrics: Test execution times

**Add to dev docs:**
```markdown
### 🧪 Test Results
**Last Run**: 2025-11-06
**Status**: ✅ All Passing (10/10 tests)

**E2E Tests**:
- `test_slam_replay.py`: 2/2 passed ✅
- `test_motion.py`: 8/8 passed ✅

**Test Quality**:
- ✅ No mocks in E2E tests
- ✅ Computer vision validation
- ✅ Real geometry, real RTAB-Map adapter (stub binding in tests)
```

---

## Usage

### Interactive Invocation
```bash
/update-context-docs
```

The command will:
1. Ask which feature/dev doc to update (or detect from current work) — input, asked before any edit
2. Analyze codebase for implementation evidence
3. Update documentation files
4. Report completion summary, with the changes as a diff — no confirmation step; the diff is the
   record of what was decided, and the developer reverts what they disagree with

### Automated Invocation (in workflows)
```bash
/update-context-docs --auto --doc=mapping-pipeline-app-undo-redo-integration
```

---

## Detection Heuristics

### How to find relevant docs:

**From current branch:**
```bash
# Extract feature from branch name
# e.g., feat/undo-redo-yjs-clean → "undo-redo"
FEATURE=$(git branch --show-current | grep -oE 'feat/([^/]+)' | cut -d'/' -f2)

# CRITICAL: Check for PRD docs FIRST
find docs/*/1-WIP/ -iname "*${FEATURE}*.md"

# If no PRDs found, then check original feature docs
if [ $? -ne 0 ]; then
  find docs/<area>/ -type f -iname "*${FEATURE}*.md" ! -path "*/1-WIP/*"
fi

# Find matching dev docs
find {common,common-testing,mapping-pipeline,onboard-detection,surmap,packages}/*/docs/ -iname "*${FEATURE}*.md"
```

**From recent commits:**
```bash
# Get files changed in last 10 commits
git log -10 --name-only --pretty=format:"" | grep -E "^(docs/ft|docs/dev)" | sort -u

# Prioritize PRDs over feature docs
PRDS=$(git log -10 --name-only --pretty=format:"" | grep -E "^docs/<area>/.*/1-WIP/")
FEATURES=$(git log -10 --name-only --pretty=format:"" | grep -E "^docs/<area>/.*\.md$" | grep -v "/1-WIP/")

# Use PRDs if they exist, otherwise use feature docs
[ -n "$PRDS" ] && echo "$PRDS" || echo "$FEATURES"
```

**From current file context:**
- If user is viewing a PRD doc, update that PRD
- If user is viewing a feature doc, CHECK if PRD exists first
- If PRD exists: update PRD, NOT the feature doc
- If user is viewing implementation file, find related docs by keyword matching

### How to verify implementation:

**For deliverables:**
```bash
# Check if file exists
test -f src/surmap/motion.py && echo "✅" || echo "❌"

# Check if class/function exists
grep -q "export class classify_motion" src/surmap/motion.py && echo "✅" || echo "❌"
```

**For acceptance criteria:**
```bash
# Check if tests exist and pass
uv run pytest -q -k replay
```

---

## Output Format

### Summary Report (Console)
```
📝 Documentation Update Summary
═══════════════════════════════

📄 PRD Doc: docs/mapping-pipeline/mapping-pipeline-editor/1-WIP/PRD-2025-01-05-undo-redo-integration.md
   ✅ Updated 15 acceptance criteria checkboxes
   ✅ Marked 3 implementation phases as complete
   ✅ Added evidence links to 8 implementation files
   ✅ Updated "Affected Features" section (3 features impacted)
   ℹ️  Original feature doc preserved (not modified)

📄 Dev Doc: docs/<area>/1-WIP/motion-layers-undo-redo-phase1-command-logging.md
   ✅ Updated 4 milestone statuses
   ✅ Marked 32 deliverables as complete
   ✅ Added test results section (10/10 tests passing)
   ✅ Added 6 known issues to technical debt
   ✅ Updated TODO list (18 completed, 4 remaining)

📊 Implementation Evidence:
   - Files created: 8
   - Tests passing: 10/10
   - session-replay tests: 2
   - E2E coverage: 100% of user stories

⚠️  Warnings:
   - 3 TODO comments need tracking numbers
   - 1 abandoned file should be deleted
   - 25 console.log statements in production code

✅ Documentation is now up-to-date with codebase reality!
```

---

## Implementation Checklist

When running this command, verify:

- [ ] **CRITICAL**: Checked for PRD documents FIRST
- [ ] **CRITICAL**: If PRD exists, ONLY modified PRD (not original feature doc)
- [ ] **CRITICAL**: If no PRD, modified original feature doc
- [ ] **CRITICAL**: Ticked the changeset rows' TODOs the implementation demonstrably completed
- [ ] PRD "Affected Features" section is up-to-date (if applicable)
- [ ] Feature/PRD doc acceptance criteria match test results
- [ ] Dev doc milestones reflect actual file existence
- [ ] All "✅ Implemented" claims have file evidence
- [ ] Test result counts match actual test runs
- [ ] Known issues have tracking IDs
- [ ] Technical debt items have priority levels
- [ ] Git commit references are valid
- [ ] session-replay tests URLs work
- [ ] File paths are accurate
- [ ] TODO comments are tracked

---

## Error Handling

**If feature/dev doc not found:**
- Check PRD directory first: `docs/*/1-WIP/`
- If no PRD, check original feature docs: `docs/<area>/*/*.md`
- Prompt user to specify manually
- Search by keywords in doc titles
- List all available docs for selection

**If both PRD and feature doc exist:**
- ✅ **Update PRD document ONLY**
- ❌ **DO NOT update original feature document**
- Inform user: "PRD document found - original feature doc preserved"

**If implementation files not found:**
- Mark deliverable as incomplete
- Add warning to report
- Suggest checking file paths in dev doc

**If tests fail to run:**
- Capture error output
- Add to known issues section
- Mark acceptance criteria as incomplete

**If git commands fail:**
- Skip commit SHA references
- Use file modification timestamps instead

---

## Rules

- Check for PRD documents FIRST
- If a PRD exists, ONLY modify the PRD (not the original feature doc)
- Tick the changeset rows' TODOs the implementation completed, under the row this run serves
  (`.agents/skills/pr-lifecycle/SKILL.md` § *Workflow rows*); never a row's status — the rows belong
  to the commands that run them
- All "Implemented" claims must have file evidence
- Test result counts must match actual test runs
- File paths must be accurate

## Related Rules

- **`.agents/skills/planning/references/feature-doc.md`**: Feature documentation structure and requirements
- **`.agents/skills/pr-lifecycle/references/prd.md`**: PRD document structure and workflow
- **`.agents/skills/pr-lifecycle/references/changeset.md`**: Changeset document structure and requirements
- **`/plan-ft`**: Feature planning and PRD creation workflow
- **`/plan-ft-dev`**: Changeset document creation workflow
- **`.agents/skills/planning/references/dev-doc.md`**: Development documentation structure and requirements
- **`/test-acceptance`**: Acceptance testing guidelines
- **`/requirements-change`**: Guidance on when to create PRDs vs direct updates

- **`/validate-tests`**: Test validation for acceptance criteria

## PRD Document Priority

**Key Principle**: PRD documents take precedence over original feature documents.

**Why?**
- Original feature docs = historical record (immutable)
- PRD docs = current requirements (mutable)
- Preserves evolution of requirements
- Maintains audit trail

**When updating documentation:**
1. Search for PRD document first
2. If found: update PRD ONLY
3. If not found: update original feature doc
4. Never modify both for the same feature
