---
description: Adopt planning material from docs/plans into PRD and changeset documents
---
## Plan to Context

This command converts planning documents from `docs/plans` into structured PRD and changeset documents, bridging informal planning with formal documentation.

## Purpose

> **Harness note**: `docs/plans/` is Muse's plan-mode output directory and is gitignored. On
> other harnesses, point this command at wherever the informal planning material lives — the
> distillation workflow below is otherwise identical.

**Problem**: Planning documents in `docs/plans` are informal, unstructured brainstorming.
**Solution**: Distill planning material into proper PRD and changeset documents with full structure and traceability.

**Benefits**:
- Preserves planning context and rationale
- Maintains link to original plan for historical reference
- Separates non-technical requirements (PRDs) from technical implementation (changesets)
- Integrates planning into formal documentation workflow

## Workflow row

This command is a planner: a changeset it creates is started per the `pr-lifecycle` skill
§ *Start a changeset* (`.agents/skills/pr-lifecycle/SKILL.md`), with row 1 (Plan) closed ✅ — command
`/plan-to-context`, **Result** the adopted plan's path — and every later row ⬜. Adopting into an existing changeset leaves its rows as they are, except that a
changeset without them is backfilled (the skill's step 2). Choosing which plan to adopt (§1) gathers
input, so those questions stay.

## Workflow

### 1. Discovery Phase

**Identify plan document:**

**If user specifies plan:**
- Use that specific plan document

**If user doesn't specify:**
1. **Analyze current context** to identify relevant plans:
   - Open files in editor
   - Current git branch name
   - Recent file changes (git status, git diff)
   - Working directory focus
   - Recent conversation topics

2. **Filter candidate plans** based on context:
   - Match plan filenames with branch names
   - Match plan content with open file paths
   - Match plan topics with conversation context
   - Match plan dates with recent activity

3. **Present candidates or ask for clarification:**
   - **If 1 clearly relevant plan found**: Use it automatically (inform user)
   - **If multiple relevant plans found**: List candidates with relevance reasoning, ask user to select
   - **If no relevant plans found**: List all available plans, ask user to specify or suggest creating new context docs
   - **If context is unclear**: List all plans with brief descriptions, ask user to specify

**Example context-aware selection:**
```
Context: User is on branch "feat/async-export", has open files related to export
Candidates found:
  ✓ 2025-01-15-async-export-plan.md (HIGH: matches branch + open files)
  ~ 2025-01-10-export-optimization-plan.md (MEDIUM: related to export)
  ✗ 2024-12-20-logging-standard-plan.md (LOW: unrelated)

Action: Automatically use 2025-01-15-async-export-plan.md (inform user)
```

**Example unclear context:**
```
Context: User on master branch, no specific files open, unclear intent
Action: List all available plans:
  1. 2025-01-15-track-enhancement-plan.md - Track toolbar with multi-color support
  2. 2025-01-10-async-export-plan.md - Background export processing with job queue
  3. 2024-12-20-logging-standard-plan.md - Standardized logging across all services

Prompt: "Which plan would you like to adopt into context documents? (1-3)"
```

**Example plan structure:**
```
docs/plans/
├── 2025-01-15-track-enhancement-plan.md
├── 2025-01-10-async-export-plan.md
└── 2024-12-20-logging-standard-plan.md
```

**Read selected plan completely** before proceeding to analysis phase.

### 2. Analysis Phase

**Extract key information from plan:**

**For PRD (Non-Technical Requirements):**
- Product requirements and use cases
- User stories and workflows
- Acceptance criteria (user-facing)
- Success metrics
- UX/UI requirements
- Feature scope and boundaries
- Business context and rationale

**For Changeset (Technical Implementation):**
- Architecture and design decisions
- Component structure and interactions
- API contracts and interfaces
- Data structures and algorithms
- Integration patterns
- Testing strategy
- Technical acceptance criteria
- Performance requirements
- Dependencies and prerequisites

**Determine affected scope:**
- Which feature documents are affected (for PRD)?
- Which packages are affected (for changeset)?
- Is this a new feature or update to existing feature?

### 3. Distillation Strategy

**Non-Technical → PRD:**

```markdown
Plan Section → PRD Section

Problem/Context → Background
User Requirements → Proposed Changes
Use Cases → User Stories
Success Criteria → Acceptance Criteria (user-facing)
UI/UX Notes → User Experience Requirements
```

**Technical → Changeset:**

```markdown
Plan Section → Changeset Section

Explore / codebase reads → docs/<area>/1-WIP/{slug}-initial-discovery.md
                         (changeset `## Initial Discovery` links here; first content section after the header)
Technical Approach → Technical Changes (State A → State B)
Architecture → Technical Changes (Architecture section)
Implementation Steps → Implementation Milestones (TODOs nested under the Green row)
Testing Notes → Testing Plan & Acceptance Tests
Dependencies → Related Feature Documentation
Technical Details → Delta (What's Changing)
```

### 4. Document Creation/Update

#### PRD Document

**Location**: `docs/{product-area}/1-WIP/PRD-YYYY-MM-DD-feature-name.md`

**If PRD exists:**
1. Read existing PRD
2. Merge plan material into appropriate sections
3. Preserve existing structure and content
4. Add reference to original plan

**If PRD doesn't exist:**
1. Create new PRD following `.agents/skills/pr-lifecycle/references/prd.md` template
2. Populate with distilled non-technical requirements
3. Add reference to original plan
4. Add "Adopted from Plan" section

**Reference to original plan:**
```markdown
## Adopted from Plan

This PRD was distilled from planning document:
- **Original Plan**: [YYYY-MM-DD-feature-name-plan.md](../../../docs/plans/YYYY-MM-DD-feature-name-plan.md)
- **Adoption Date**: YYYY-MM-DD
- **Planning Context**: Brief summary of what was planned

**Note**: Original plan will be archived when this PRD is wrapped via `/wrap-context-docs`.
```

#### Changeset Document

**Companion (mandatory)**: write or update the initial-discovery companion from the plan's
codebase reads and any Explore / Grep / Glob / Read done during distillation.

**If changeset exists:**
1. Read existing changeset
2. Merge plan material into appropriate sections
3. Preserve existing structure, milestones and `## Workflow` (backfill it when absent)
4. Add reference to original plan

**If changeset doesn't exist:**
1. Start it per § *Start a changeset*
2. Populate with distilled technical details (Plan-mode / `docs/plans` discussion goes **after** Initial Discovery, not as the first section)
3. Add reference to original plan and PRD
4. Add "Adopted from Plan" section

**Reference to original plan:**
```markdown
## Adopted from Plan

This changeset was distilled from planning document:
- **Original Plan**: [YYYY-MM-DD-feature-name-plan.md](../../docs/plans/YYYY-MM-DD-feature-name-plan.md)
- **Adoption Date**: YYYY-MM-DD
- **Planning Context**: Brief summary of technical approach planned
- **Related PRD**: [PRD-YYYY-MM-DD-feature-name.md](../ft/{product-area}/1-WIP/PRD-YYYY-MM-DD-feature-name.md)

**Note**: Original plan will be archived when this changeset is wrapped via `/wrap-context-docs`.
```

### 5. Bidirectional Linking

**PRD → Changeset:**
```markdown
## Related Development Documentation

Technical implementation planned in:
- [Changeset: Feature Name](../../dev/1-WIP/YYYY-MM-DD-changeset-name.md)
```

**Changeset → PRD:**
```markdown
## Related Feature Documentation

Requirements specified in:
- [Feature PRD](../ft/{product-area}/1-WIP/PRD-YYYY-MM-DD-feature-name.md)
```

### 6. Validation

**Validate PRD:**
- [ ] All non-technical requirements extracted
- [ ] Affected features listed
- [ ] User-facing acceptance criteria defined
- [ ] Reference to original plan added
- [ ] Follows `.agents/skills/pr-lifecycle/references/prd.md` structure

**Validate changeset:**
- [ ] Started per § *Start a changeset*, row 1 closed ✅
- [ ] Milestones and acceptance tests nested as TODOs under Green; wrap obligations (always
      `Verification executed — result recorded`) and the optional `/pr-wrap` steps it needs under Wrap
- [ ] All technical details extracted
- [ ] Affected packages listed
- [ ] State A, State B, Delta defined
- [ ] Testing plan complete
- [ ] Reference to original plan and PRD added
- [ ] Follows `.agents/skills/pr-lifecycle/references/changeset.md` structure

**Validate bidirectional links:**
- [ ] PRD links to changeset
- [ ] Changeset links to PRD
- [ ] Both link to original plan

### 7. Output

**If new files created:**
```
**CRITICAL FOR CONTEXT & SUMMARY**

Plan adopted from: docs/plans/YYYY-MM-DD-feature-name-plan.md

Created:
- PRD: docs/{product-area}/1-WIP/PRD-YYYY-MM-DD-feature-name.md
- Companion: docs/<area>/1-WIP/YYYY-MM-DD-changeset-name-initial-discovery.md
- Changeset: docs/<area>/1-WIP/YYYY-MM-DD-changeset-name.md

Affected features: [list]
Affected packages: [list]

Workflow: <preset> — row 1 Plan ✅; next row: <2> <step> — `<Run with>`
```

**If existing files updated:**
```
Plan material adopted from: docs/plans/YYYY-MM-DD-feature-name-plan.md

Updated:
- PRD: docs/{product-area}/1-WIP/PRD-YYYY-MM-DD-feature-name.md
- Companion: docs/<area>/1-WIP/YYYY-MM-DD-changeset-name-initial-discovery.md
- Changeset: docs/<area>/1-WIP/YYYY-MM-DD-changeset-name.md

Changes:
- [Summary of what was merged/updated]

Workflow: unchanged (or: backfilled) — next row: <k> <step> — `<Run with>`
```

## Plan Lifecycle

### 1. Planning Phase

```
User brainstorms → Creates plan in docs/plans/ → Informal, unstructured
```

### 2. Adoption Phase (THIS COMMAND)

```
/plan-to-context → Distill plan → Create/update PRD & changeset → Structured, formal
```

### 3. Implementation Phase

```
PRD & changeset guide implementation → Updated via /update-context-docs
```

### 4. Wrapping Phase

```
/wrap-context-docs → Apply to feature/dev docs → Delete changeset, PRD, and `{slug}-initial-discovery.md` → Archive original `docs/plans` file
```

## Integration with wrap-context-docs

**CRITICAL**: `/wrap-context-docs` **deletes** the WIP sources (changeset, PRD, and discovery companion). It does **not** archive them under `docs/<area>/1-WIP/1-ARCHIVE/` or `docs/*/1-WIP/1-ARCHIVE/`. The only archive this command still performs is the informal `docs/plans/` file.

When `/wrap-context-docs` is invoked:

1. **Detect plan reference:**
   - Check PRD and changeset for "Adopted from Plan" section
   - Extract original plan file path

2. **Delete the discovery companion** with the changeset (same step as wrap):
   - `docs/<area>/1-WIP/{slug}-initial-discovery.md` — delete, do not archive, do not merge into package docs
   - See `.agents/skills/pr-lifecycle/references/initial-discovery.md`

3. **Archive original `docs/plans` file only:**
   ```bash
   # After wrapping (WIP PRD, changeset, and companion are already deleted)
   if [ -f "docs/plans/YYYY-MM-DD-feature-name-plan.md" ]; then
     mkdir -p docs/plans/1-ARCHIVE
     git mv docs/plans/YYYY-MM-DD-feature-name-plan.md \
           docs/plans/1-ARCHIVE/
   fi
   ```

4. **Update plan reference in wrapped docs:**
   - When wrapping PRD: Update plan reference path to point to `docs/plans/1-ARCHIVE/`
   - When wrapping changeset: Update plan reference path to point to `docs/plans/1-ARCHIVE/`

5. **Git operations:**
   ```bash
   # Stage changes (WIP sources are deletions, not 1-ARCHIVE moves)
   git add docs/{product-area}/*.md
   git add docs/{product-area}/1-WIP/
   git add {group}/{package}/docs/
   git add docs/<area>/1-WIP/
   git add docs/plans/1-ARCHIVE/

   # Commit
   git commit -m "docs: wrap context docs and archive plan

   - Applied PRD PRD-YYYY-MM-DD-feature-name
   - Applied changeset YYYY-MM-DD-changeset-name
   - Deleted {slug}-initial-discovery.md with the changeset
   - Archived original plan YYYY-MM-DD-feature-name-plan
   - All documents updated to reflect final implemented state"
   ```

## Distillation Guidelines

### PRD Distillation (Non-Technical)

**Focus on:**
- What users need/want
- What problem this solves
- User-facing behavior and workflows
- Success metrics from user perspective
- UX/UI requirements
- Business value and context

**Extract from plan:**
- Problem statements
- User stories and scenarios
- Feature descriptions
- UI/UX sketches or descriptions
- Success criteria (user-facing)
- Scope and boundaries

**Example distillation:**
```
Plan: "We need to add support for multiple track colors because users
      asked for it. Blue ink is most requested. Also stylus pressure would
      make signatures look more realistic."

↓

PRD:
## Proposed Changes

### Enhanced Track Capabilities
- Multiple ink colors (black, blue, custom RGB)
- Pressure-sensitive rendering for realistic appearance
- Color picker integration in track toolbar

## Acceptance Criteria
- User can select blue ink from track toolbar
- User can choose custom color via color picker
- Stylus pressure affects line thickness and opacity
- Moving tracks keep their motion class in the final map
```

### Changeset Distillation (Technical)

**Focus on:**
- How to implement
- Architecture and design
- Technical approach and patterns
- Component interactions
- API contracts
- Testing strategy
- Performance considerations

**Extract from plan:**
- Technical approach descriptions
- Architecture decisions
- Component/module breakdown
- API/interface designs
- Data structures
- Integration points
- Testing approach
- Performance targets

**Example distillation:**
```
Plan: "Track engine needs to accept color parameter (RGB). Pressure
      data from stylus events (0-1 float). Render stroke with variable
      width based on pressure. Store color in track metadata."

↓

Changeset:
## Technical Changes

### State B (Target)

#### surmap
**Track API**:
```python
interface SignatureOptions {
  inkColor: { r: number; g: number; b: number };
  pressureSensitive: boolean;
}

interface StrokePoint {
  x: number;
  y: number;
  pressure: number; // 0-1
}
```

**Rendering**:
- Variable stroke width: `baseWidth * (0.5 + pressure * 0.5)`
- Color blending: Alpha channel based on pressure
- Metadata storage: Motion class preserved on the track record

### Testing Plan
- **Unit**: Color parameter correctly applied to stroke rendering
- **Integration**: Pressure data from stylus events captured
- **E2E**: Moving track renders as a timestamped track in the map export
```

## Best Practices

### Do's ✅

- **Read entire plan** before distilling
- **Separate concerns** clearly (non-technical vs technical)
- **Preserve planning context** via "Adopted from Plan" section
- **Create bidirectional links** between PRD and changeset
- **Reference original plan** for historical context
- **Follow templates** strictly (`.agents/skills/pr-lifecycle/references/prd.md`, `.agents/skills/pr-lifecycle/references/changeset.md`)
- **Validate completeness** - ensure all relevant plan material adopted
- **Update existing docs** when they exist (don't duplicate)

### Don'ts ❌

- **Don't copy plan verbatim** - distill and restructure
- **Don't mix technical and non-technical** in same document
- **Don't lose information** - capture all relevant context
- **Don't forget bidirectional links** - PRD ↔ changeset
- **Don't skip "Adopted from Plan" section** - traceability is critical
- **Don't leave plan orphaned** - must reference from both docs
- **Don't duplicate existing content** - merge thoughtfully

## Example Workflow

### Input: Planning Document

```markdown
# Async Export Feature Plan

## Problem
Users want to export large documents but UI freezes during processing.
Need async processing with progress tracking.

## Technical Approach
- Move export to background worker
- Store export job in database
- Poll for status via endpoint
- Send webhook when complete
- Archive stored in S3

## User Flow
1. User clicks export
2. See "Export started" toast
3. Poll status every 2 seconds
4. Download when ready
```

### Output: PRD Document

```markdown
# Async Export Feature - PRD

**Date**: 2025-01-15
**PRD Type**: Enhancement

## Affected Features
- **Export Workflow**: [export-workflow.md](../export-workflow.md) - Async processing
- **User Notifications**: [notifications.md](../notifications.md) - Progress updates

## Summary
Enable asynchronous document export with progress tracking for large files.

## Background
Synchronous exports cause UI freezes for large documents (>50 pages).
Users need ability to continue working while export processes in background.

## Proposed Changes

### Asynchronous Export Workflow
- Export initiated without blocking UI
- Real-time progress tracking
- Notification when export completes
- Download link provided in notification

### User Experience
1. User initiates export → Immediate confirmation toast
2. Export processes in background → User continues working
3. Progress indicator shows status → User informed of progress
4. Completion notification → Download link available

## Acceptance Criteria
- User receives immediate feedback when export starts
- UI remains responsive during export processing
- User can track export progress
- User receives notification when export completes
- Download link available after completion

## Adopted from Plan

This PRD was distilled from planning document:
- **Original Plan**: [2025-01-15-async-export-plan.md](../../../docs/plans/2025-01-15-async-export-plan.md)
- **Adoption Date**: 2025-01-15
- **Planning Context**: Background export processing with progress tracking

**Note**: Original plan will be archived when this PRD is wrapped via `/wrap-context-docs`.

## Related Development Documentation
- [Changeset: Async Export Implementation](../../dev/1-WIP/2025-01-15-async-export.md)
```

### Output: Changeset Document

```markdown
# Changeset: Async Export Implementation

**Date**: 2025-01-15
**Type**: Feature

## Affected Packages

- **surmap**: [README.md](../../mapping-pipeline/mapping-pipeline-server/README.md)
  - [architecture.md](../../mapping-pipeline/mapping-pipeline-server/docs/architecture.md) - Export job architecture
  - [api-reference.md](../../mapping-pipeline/mapping-pipeline-server/docs/api-reference.md) - Export endpoints

- **surmap**: [README.md](../../mapping-pipeline/mapping-pipeline/README.md)
  - [api-reference.md](../../mapping-pipeline/mapping-pipeline/docs/api-reference.md) - Export client API

## Related Feature Documentation
- [Async Export PRD](../ft/mapping-pipeline-editor/1-WIP/PRD-2025-01-15-async-export.md)

## Summary
Implement asynchronous export processing with job queue and status polling.

## Background
Current synchronous export blocks Node.js event loop for large documents.
Need background processing with job persistence and status tracking.

## Technical Changes

### State A (Current)
- Synchronous export processing
- Direct HTTP response with file
- No job tracking

### State B (Target)

#### Export Job Architecture
```python
interface ExportJob {
  id: string;
  userId: string;
  documentId: string;
  status: 'PENDING' | 'PROCESSING' | 'COMPLETED' | 'FAILED';
  progress: number; // 0-100
  resultUrl?: string;
  error?: string;
}
```

#### API Endpoints
- `POST /api/v1/exports` - Initiate export, return job ID
- `GET /api/v1/exports/{jobId}` - Poll job status
- `POST /api/v1/exports/{jobId}/webhook` - Register webhook (optional)

#### Background Processing
- Bull queue for job management
- Redis for job state storage
- S3 for archive storage
- Worker process for export execution

### Implementation Milestones
Written as TODOs under the Green row (`## Workflow`):
- [wf 3] ⬜ `/green` Green — implement until every red test passes ·
  - [ ] Create export job database schema
  - [ ] Implement export job API endpoints
  - [ ] Set up Bull queue and worker
  - [ ] Integrate S3 storage for archives
  - [ ] Add webhook notification support
  - [ ] Implement client polling logic

## Testing Plan

### Option 1: E2E Export Flow (Primary)
**Test Level**: E2E
**Description**: Full async export workflow from initiation to download

**Scope**:
- Initiate export via API
- Poll status until completion
- Verify archive creation in S3
- Download and verify archive contents

**Assertions**:
- Export job created with status PENDING
- Job progresses through PROCESSING to COMPLETED
- Archive URL returned in completed job
- Archive contains expected files with correct structure
- Archive downloadable from S3 URL

## Acceptance Tests

### surmap
- **E2E**: Export large document (100 pages) without blocking (async-export.e2e.test.ts)
- **Integration**: Export job persisted and retrieved correctly (export-job-dao.it.test.ts)
- **Integration**: S3 archive upload and retrieval (s3-storage.it.test.ts)

### surmap
- **E2E**: Client polls status and receives completion (export-client.e2e.test.ts)
- **Unit**: Progress calculation logic (export-progress.test.ts)

## Adopted from Plan

This changeset was distilled from planning document:
- **Original Plan**: [2025-01-15-async-export-plan.md](../../docs/plans/2025-01-15-async-export-plan.md)
- **Adoption Date**: 2025-01-15
- **Planning Context**: Background worker with queue-based processing
- **Related PRD**: [PRD-2025-01-15-async-export.md](../ft/mapping-pipeline-editor/1-WIP/PRD-2025-01-15-async-export.md)

**Note**: Original plan will be archived when this changeset is wrapped via `/wrap-context-docs`.
```

## Related Rules and Commands

**Related Rules**:
- `.agents/skills/pr-lifecycle/references/prd.md` - PRD document structure and workflow
- `.agents/skills/pr-lifecycle/references/changeset.md` - Changeset document structure and requirements
- `.agents/skills/planning/references/feature-doc.md` - Feature documentation standards
- `.agents/skills/planning/references/dev-doc.md` - Development documentation structure

**Related Commands**:
- `/plan-ft` - Create feature or PRD from scratch
- `/plan-ft-dev` - Create changeset from feature/PRD
- `/update-context-docs` - Update context docs during implementation
- `/wrap-context-docs` - Apply context docs; delete PRD, changeset, and `{slug}-initial-discovery.md`; archive original `docs/plans` file

**Workflow Integration**:
```
Planning in docs/plans/
        ↓
/plan-to-context → Create/update PRD & changeset (with `## Workflow`)
        ↓
Implementation guided by the changeset's `## Workflow` rows
        ↓
/wrap-context-docs → Delete PRD, changeset, and `{slug}-initial-discovery.md`; archive original `docs/plans` file
        ↓
Clean final documentation + archived planning artifacts
```

---

**Status**: ✅ Command Definition Complete
**Purpose**: Bridge informal planning with formal documentation workflow
**Key Benefit**: Preserves planning context while maintaining structured documentation
