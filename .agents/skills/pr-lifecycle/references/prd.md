---
description: PRD (Product Requirements Document) structure, workflow, and requirements for tracking feature requirement changes
---
# PRD (Product Requirements Document) Standards

## Purpose

PRD documents track requirement changes to existing features without modifying original feature documents. They provide:

1. **Historical context** - Shows how requirements evolved over time
2. **Audit trail** - Clear record of what changed, when, and why
3. **Multi-feature tracking** - Can affect multiple feature documents in one PRD
4. **Rollback capability** - Original requirements preserved for reference
5. **Traceability** - Links all affected features and their specific changes

## When to Create a PRD Document

Create a PRD document when:
- Requirements change for an existing feature
- New capabilities are added to an existing feature
- Scope is reduced or expanded
- Technical approach changes significantly
- Multiple features are affected by related changes

**CRITICAL**: Never modify original feature documents when requirements change. Always create a PRD document.

## PRD Document Location

**Directory**: `docs/<area>/1-WIP/`

All PRD documents are created in a single global directory regardless of which product area they affect.

**Naming Convention**: `PRD-YYYY-MM-DD-feature-name.md`

**Examples**:
- `docs/<area>/1-WIP/PRD-2025-01-05-signature-styles.md`
- `docs/<area>/1-WIP/PRD-2024-11-15-revision-support.md`

## PRD Document Template

```
# [Feature Name] - PRD

**Date**: YYYY-MM-DD
**PRD Type**: Enhancement | Bug Fix | Requirement Update | Technical Improvement

## Affected Features

**CRITICAL**: List ALL feature documents affected by this PRD:

- **Primary Feature**: [Feature Name](../mapping-pipeline-editor/feature-name.md) - Description of primary changes
- **Related Feature 1**: [Feature Name](../stereo-ingest/related-feature-1.md) - Description of secondary impact
- **Related Feature 2**: [Feature Name](../mapping-pipeline-api/related-feature-2.md) - Description of dependency changes

## Summary
Brief description of what is changing across the affected features.

## Background
Why this PRD is needed.

## Proposed Changes

### What's Changing
- List specific changes to requirements for each affected feature
- Include new capabilities or removed capabilities
- Note any API changes
- Cross-reference affected feature documents

### What's Staying the Same
- List what remains unchanged in affected features
- Provide context for stability

## Impact Analysis

### Technical Impact
- Code changes required (per affected feature)
- Dependencies affected
- Performance implications
- Integration points affected

### User Impact
- UX changes (per affected feature)
- Workflow modifications
- Breaking changes
- Migration requirements

## Implementation Plan
1. Step-by-step plan referencing affected features
2. Migration strategy (if applicable)
3. Testing approach for each affected feature
4. Rollout/deployment strategy

## Acceptance Criteria
- [ ] Updated requirement 1 ([Feature Name](../product-area/feature-name.md))
- [ ] Updated requirement 2 ([Related Feature](../product-area/related-feature.md))
- [ ] Migration completed
- [ ] Tests passing for all affected features

## References

### Affected Features (Complete List)
- [Feature 1](../product-area/feature-1.md) - Specific changes
- [Feature 2](../product-area/feature-2.md) - Specific changes

### Related Documentation
- Related tickets: [links]
- Design assets: [links to appendices]
- Technical specs: [links to appendices]
```

## Change History for Feature Documents

### Purpose

Track the history of changes applied to a feature document in release note style. This provides traceability without cluttering the main content or linking to deleted source files.

The traceability runs **one way**. Entries point outward at PRs and stable docs; stable docs never point back at entries — see **Rules** below.

### When Added

`/wrap-context-docs` writes a **new file** under `docs/{product-area}/changelog/` when a PRD is applied. Do not append to a shared changelog.

### Location

**Directory**: `docs/{product-area}/changelog/`

Each product area has a `changelog/` directory. Each wrapped PRD is its own file, named
`YYYY-MM-DD-short-description.md`. Do **not** append to a shared `changelog.md` — that file
conflicts on every parallel wrap.

### Format

```markdown
# Signature Styles Enhancement

**Date:** 2025-01-05
**Feature:** Signature Tool

Added multiple ink styles, pressure sensitivity, and color picker integration.
```

### Guidelines

**Filename**: `YYYY-MM-DD-kebab-case-slug.md` — ISO date of the wrap, then a slug that names the
change (what landed, not `update` or `fix`). Unique in that directory.

**Rules**:
- **One file per wrapped PRD** — never append to a shared changelog
- **No index file** that lists every entry — directory order by the date prefix is the chronology
- **Nothing links in.** An entry is terminal: no stable document — `1-OVERVIEW.md`, a feature doc,
  an `README.md`, a `README.md` — may reference an individual entry, in any form (`See
  [changelog/…](…)`, `**Implementation**: see [changelog](…)`, `([changelog](…))`, a "Change
  History" list, or a **bare path in backticks** — the test is what it points at, not how it is
  spelled). A single link to the `changelog/` **directory** in a product area's document
  list is the only permitted mention. An entry records one dated delta and is never revised, so a
  document stating current behaviour that links to one goes stale as soon as a later entry
  supersedes it; if the fact still matters, write the fact into the stable doc in State B. The
  entry itself may cite PRs, stable docs and other entries freely
- **Feature name in the `**Feature:**` field**, not as an H2 grouping header
- **No file references** — source PRDs are deleted after wrapping. The one exception is the
  **Deferred answers** block (`/wrap-context-docs` § *History files*, step 7c): the Product
  deferred-answer records this change left open, by backticked path, each with its question and
  decision, so the release note says which of its behaviours the developer has not reviewed yet
- **Past tense** — "Added X", "Enhanced Y", "Removed Z"
- One `changelog/` directory per product area (not per feature)

## PRD Lifecycle

### 1. Created

**When**: Requirements change for existing features

**Command**: `/plan-ft` (creates PRD document)

**Content**:
- List all affected features
- Describe what's changing and what's staying the same
- Impact analysis (technical and user)
- Implementation plan
- Acceptance criteria

### 2. In Progress

**Status**: 🚧 In Progress

**Activities**:
- Implementation based on updated requirements
- Update acceptance criteria checkboxes as work progresses
- Track testing for each affected feature
- Document any discovered issues or additional impacts

### 3. Complete

**Status**: ✅ Complete

**Criteria**:
- All acceptance criteria checked
- All affected features implemented
- Tests passing for all affected features
- Documentation updated

### 4. Wrapped

**Command**: `/wrap-context-docs` (applies PRD to feature docs)

**Actions**:
1. Applies changes to all affected feature documents
2. Writes `docs/{product-area}/changelog/YYYY-MM-DD-short-description.md` for this PRD
3. **Deletes** PRD document (not archived)
4. Updates any related changeset documents

**Result**: PRD document deleted, feature documents updated, changelog file written

## Preserving History

**CRITICAL PRINCIPLE**: Never modify original feature documents directly when requirements change.

**Why?**
- Maintains historical context
- Shows evolution of requirements
- Enables rollback if needed
- Provides audit trail
- Clear traceability to affected features

**How?**
1. Create PRD document in `docs/<area>/1-WIP/` directory
2. List all affected features
3. Describe changes without modifying originals
4. Implement changes based on PRD
5. Use `/wrap-context-docs` to apply and archive

**Nothing links to a PRD.** No stable document — `1-OVERVIEW.md`, a feature doc, a changelog
entry, a package `README.md` / `README.md` / `docs/` page — references a PRD in `1-WIP/`, by link
or by path (`docs/AGENTS.md` § *Nothing links into `1-WIP/`*). The PRD points out at the features it
affects; the reverse link would die at wrap.

## Multi-Feature PRDs

### When to Use

Use a single PRD document when:
- Changes affect multiple related features
- Changes span multiple product areas
- Technical approach change impacts multiple features
- Refactoring affects feature boundaries

### Structure for Multi-Feature PRDs

```
## Affected Features

**CRITICAL**: List ALL feature documents affected by this PRD:

### Primary Features
- **[Feature A](../mapping-pipeline-editor/feature-a.md)** - Major changes to core functionality
- **[Feature B](../mapping-pipeline-api/feature-b.md)** - API changes for integration

### Secondary Features
- **[Feature C](../mapping-pipeline-editor/feature-c.md)** - UI updates to reflect new capabilities
- **[Feature D](../stereo-ingest/feature-d.md)** - Documentation updates

### Dependencies
- **[Feature E](../infrastructure/feature-e.md)** - No code changes, but updated integration examples
```

### Impact Analysis for Multi-Feature PRDs

```
Break down impact by feature:
## Impact Analysis

### Feature A Impact
- **Technical**: Code changes to X, Y, Z
- **User**: New UI for A functionality

### Feature B Impact
- **Technical**: API contract change, breaking change
- **User**: Migration required for existing integrations

### Feature C Impact
- **Technical**: UI component updates
- **User**: Visual changes only, no behavior change
```

## Best Practices

### Do's ✅
- Always list ALL affected features
- Create PRD before implementing changes
- Cross-reference all affected feature documents
- Include impact analysis for each affected feature
- Preserve original feature documents unchanged
- Use clear PRD types (Enhancement, Bug Fix, etc.)
- Update acceptance criteria as work progresses
- Link to related design assets and technical specs

### Don'ts ❌
- Don't modify original feature documents when requirements change
- Don't create PRD without listing affected features
- Don't skip impact analysis
- Don't forget User Impact section
- Don't modify archived PRDs
- Don't create PRDs for new features (use feature docs instead)
- Don't mix unrelated changes in one PRD

## Related Rules and Commands

**Related Rules**:
- [feature-doc.mdc](/.agents/skills/planning/references/feature-doc.md) - Feature documentation standards and templates
- [dev-doc.mdc](/.agents/skills/planning/references/dev-doc.md) - Development documentation and changeset workflow

**Related Commands**:
- `/plan-ft` - Creates feature PRD document
- `/wrap-context-docs` - Applies PRD to feature docs and archives it
- `/requirements-change` - Guides decision on PRD vs direct update

**Workflow Integration**:
```
Requirements change → Create PRD → Implement → Wrap → Updated feature docs
```

## Examples

### Example 1: Single Feature PRD

**File**: `docs/<area>/1-WIP/PRD-2025-01-05-signature-styles.md`

**Affected**: Single feature (`mapping-pipeline-editor/signature-toolbar.md`)

**Type**: Enhancement

**Changes**: Added multiple ink styles and pressure sensitivity

**Impact**: Code changes to signature rendering, new UI controls

### Example 2: Multi-Feature PRD

**File**: `docs/<area>/1-WIP/PRD-2024-12-10-async-processing.md`

**Affected**: Multiple features
- `mapping-pipeline-api/upload-endpoint.md` (primary)
- `mapping-pipeline-api/status-polling.md` (secondary)
- `mapping-pipeline-api/webhook-notifications.md` (new capability)

**Type**: Architecture Change

**Changes**: Migration from synchronous to asynchronous processing

**Impact**: Breaking API change, requires migration guide

### Example 3: Cross-Product PRD

**File**: `docs/<area>/1-WIP/PRD-2025-03-15-logging-standard.md`

**Affected**: Features across multiple product areas
- `mapping-pipeline-editor/error-handling.md`
- `mapping-pipeline-api/observability.md`
- `stereo-ingest/diagnostics.md`

**Type**: Technical Improvement

**Changes**: Standardized logging format across all products

**Impact**: Code changes to logging calls, no user-visible impact
