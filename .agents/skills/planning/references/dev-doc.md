# Development Documentation

## Purpose

Development documentation serves as the **stable, read-only technical reference** for each package in the monorepo. This documentation:

1. Describes technical architecture, implementation details, and component structure
2. Provides guidance on how to develop, run, and test each package
3. Serves as the authoritative source for implementation milestones and technical decisions
4. Is **NOT modified directly** - changes come through changeset documents (see [Changeset Workflow](#changeset))
5. Complements **feature documentation** ([feature-doc.mdc](/.agents/skills/planning/references/feature-doc.md)) by providing the "how" to feature doc's "what"

## Relationship with Feature Documentation

**Feature Documentation** (`docs/<area>/`) defines **WHAT** to build:
- Product requirements and use cases
- User stories and acceptance criteria
- Business context and success metrics
- See [feature-doc.mdc](/.agents/skills/planning/references/feature-doc.md) for complete guidelines

**Development Documentation** (`{common,common-testing,mapping-pipeline,onboard-detection,surmap,packages}/*/docs/`) defines **HOW** to build it:
- Technical architecture and implementation
- Component structure and code organization
- Integration patterns and dependencies
- Testing strategies and best practices

**Cross-References**:
- Package READMEs should link to both feature docs (what) and dev docs (how)
- Dev docs should reference relevant feature docs to provide product context
- Changesets bridge the gap by tracking technical changes driven by feature requirements

## Documentation Structure

### Package-Level Documentation

Each package in `packages/` has a two-tier documentation structure:

#### 1. Package README.md (Entry Point)

**Location**: `packages/{package-name}/README.md`

**Purpose**: Concise entry point with essential information and references to detailed docs.

**CRITICAL Principles**:

1. **Single README Principle** - Each package must have ONLY ONE README.md file at the package root. No nested READMEs in subdirectories (e.g., `test/README.md`, `src/README.md`). All documentation belongs either in the main README.md or in detailed docs under `packages/{package-name}/docs/`.

2. **Conciseness Principle** - README must be **brief** (target: < 100 lines, max: 150 lines). It's an **entry point**, not comprehensive documentation.

3. **No Implementation Details** - README contains NO:
   - ❌ Detailed feature descriptions
   - ❌ User workflows or UX flows
   - ❌ Code examples or implementation patterns
   - ❌ API usage examples
   - ❌ Integration patterns
   - ❌ File structure details
   - ❌ Technical implementation details
   - ❌ Artifact specifications

   **All these belong in `packages/{package-name}/docs/` detailed docs!**

**Content** (ONLY):
- Brief package description (2-3 sentences max)
- Quick start: how to develop, run, and test (commands only, no explanations)
- Architecture overview (**1 paragraph**, high-level concept only)
- Links to detailed technical documentation in `packages/{package-name}/docs/`
- Links to related packages and dependencies

**Think of README as**: A business card with contact info, NOT a resume with full work history.

**Template** (strict, DO NOT add more):
```markdown
# {Package Name}

Brief description of what this package does (2-3 sentences max).

## Quick Start

### Development
\`\`\`bash
uv run pytest -q
\`\`\`

### Testing
\`\`\`bash
uv run pytest -q
\`\`\`

## Architecture

High-level architecture description (1 paragraph ONLY, no diagrams, no details).

## Documentation

### Product Requirements (What)
- [Feature Documentation](../../../../docs/{product-area}/1-OVERVIEW.md) - Product requirements and features

### Technical Implementation (How)
- [Architecture](./docs/architecture.md) - System design and components
- [API Reference](./docs/api-reference.md) - API documentation
- [Integration Guide](./docs/integration.md) - Service integrations
- [Changesets](./docs/changesets/) - Applied changeset history

## Related Packages
- [surmap](../related-package/README.md)
```

**What NOT to Include** (common violations):
```markdown
❌ ## Features (with subsections and bullet points)
❌ ## User Workflows (step-by-step flows)
❌ ## Export Workflow (detailed process descriptions)
❌ ## Integration Patterns (code examples)
❌ ## Platform Integration (implementation details)
❌ ## File Structure (ZIP contents, naming conventions)
❌ ## Usage Examples (code snippets)
❌ ## Configuration (detailed config options)
```

**Where These Belong Instead**:
- Features → `docs/{product-area}/` (feature docs define WHAT)
- Workflows → `packages/{package-name}/docs/integration.md`
- Code examples → `packages/{package-name}/docs/api-reference.md`
- Implementation details → `packages/{package-name}/docs/architecture.md`
- Integration patterns → `packages/{package-name}/docs/integration.md`
- Configuration → `packages/{package-name}/docs/configuration.md`

**Golden Rule**: If it requires scrolling past one screen, it doesn't belong in README.

#### 2. Package README.md (Agent Briefing)

**Location**: `packages/{package-name}/AGENTS.md`

**Purpose**: Tool-agnostic agent briefing for AI coding assistants. Under 60 lines.

**Content**: Mission (1-2 sentences), Toolchain (table), Key Dependencies, Architecture (3-5 bullets), Judgment Boundaries (NEVER/ALWAYS), Documentation pointers to `./docs/`.

**CRITICAL**: Never auto-generate README.md — it must be hand-authored.

#### 3. Detailed Documentation (package docs/)

**Location**: `packages/{package-name}/docs/`

**Purpose**: Comprehensive technical documentation that is **stable and read-only**.

**Structure**:
```
packages/{package-name}/docs/
├── architecture.md          # System design, component structure
├── api-reference.md         # Public API documentation
├── implementation.md        # Implementation details, algorithms
├── testing.md              # Testing strategy and patterns
├── integration.md          # Integration with other packages
├── changesets/              # Applied changeset history (one file per wrap)
│   └── YYYY-MM-DD-slug.md
└── decisions/              # Architecture decision records
    ├── 001-decision.md
    └── 002-decision.md
```

**Content Guidelines**:
- **Architecture**: Component diagrams, data flow, design patterns
- **API Reference**: Public interfaces, types, function signatures
- **Implementation**: Core algorithms, data structures, technical details
- **Testing**: Test strategy, patterns, acceptance criteria
- **Integration**: How package integrates with others, dependencies
- **Changesets**: One file per wrapped changeset applied to this package
- **Decisions**: Timestamped ADRs (Architecture Decision Records)

### Cross-Package References

Documentation can reference other packages using relative markdown links:

```markdown
This package depends on [surmap](../../stereo-ingest/docs/architecture.md) for parsing.

See [mapping-pipeline-server integration](../../mapping-pipeline-server/docs/integration.md#native-parser) for details.
```

## Changeset Workflow

### Overview

**CRITICAL**: Development documentation is **read-only**. Changes come through **changeset documents**.

**Changeset** = Delta between documentation State A (before change) and State B (after change)

**Workflow**:
```
Feature requirement → Create changeset → Implement → Wrap changeset → Update dev docs
```

### Changeset Documents

**Location**: `docs/<area>/1-WIP/YYYY-MM-DD-changeset-name.md`

**Purpose**: Track changes to development documentation across one or more packages.

**Full Documentation**: See [the changeset structure](/.agents/skills/pr-lifecycle/references/changeset.md) for complete changeset structure, requirements, and lifecycle details.

**Quick Reference Structure**:
```markdown
# Changeset: {Feature/Change Name}

**Date**: YYYY-MM-DD
**Status**: 🚧 In Progress | ✅ Complete
**Type**: Feature | Refactor | Bug Fix | Architecture Change

## Initial Discovery
[Link to `./YYYY-MM-DD-feature-name-initial-discovery.md` — see changeset-doc.mdc §2]

## Affected Packages
[List ALL packages - see changeset-doc.mdc for details]

## Related Feature Documentation
[Links to feature docs and PRD docs - see [the PRD guide](/.agents/skills/pr-lifecycle/references/prd.md) for PRD structure]

## Summary
[Brief description]

## Background
[Why needed]

## Scope
[High-level deliverables, no checkboxes — their progress is TODOs under the `[wf]` rows; see changeset-doc.mdc]

## Technical Changes
[State A, State B, Delta - see changeset-doc.mdc for format]

## Implementation Milestones
[Written as TODOs nested under the Green row - see changeset-doc.mdc]

## Acceptance Tests
[Per-package tests - see changeset-doc.mdc]

## Technical Debt & Production Readiness
[Gaps tracking - see changeset-doc.mdc]

## Decisions & Trade-offs
[Technical decisions - see changeset-doc.mdc]

## Refactoring Needed
[Code quality issues by source rule - see changeset-doc.mdc]

## Validation Results
[Findings from validation rules - see changeset-doc.mdc]

## References
[Related docs - see changeset-doc.mdc]
```

**For complete template, section requirements, and examples**: See [the changeset structure](/.agents/skills/pr-lifecycle/references/changeset.md)

### Changeset Lifecycle

1. **Created** (by a planning command — `/plan-red`, `/plan-ft-dev`, …): Changeset document created with `## Workflow` (from a preset in [the `pr-lifecycle` skill](../../pr-lifecycle/SKILL.md)), State A, State B, milestones
2. **In Progress**: Each `## Workflow` row closed by the command that runs it, its TODOs (milestones, acceptance tests) ticked as done
3. **Complete**: No open TODO under the rows before Wrap — milestones complete, acceptance tests passing
4. **Wrapped** (`/wrap-context-docs`): Applied to dev docs, **deleted** (not archived). Also delete `{slug}-initial-discovery.md` — do not merge it into package docs.

**Detailed lifecycle documentation**: See [the changeset structure](/.agents/skills/pr-lifecycle/references/changeset.md)

## Package Change History Tracking

**Purpose**: Track the history of technical changes applied to package development documentation in release note style. This provides traceability without linking to deleted source files.

**When updated**: `/wrap-context-docs` writes a **new file** when a changeset is wrapped. Do **not**
append to a shared `changesets.md` — that file conflicts on every parallel wrap.

**Location**: `{group}/{package-name}/docs/changesets/YYYY-MM-DD-short-description.md`

### File Format

```markdown
# Icon Export Quality Fixes

**Date:** 2026-01-22
**Type:** Bug Fix
**Packages:** surmap

Fixed blurry PNG at small sizes, gradient stop-color not themed, background visible at 0% opacity.
```

### Guidelines

**Filename**: `YYYY-MM-DD-kebab-case-slug.md` — ISO date of the wrap, then a slug that names the
change (what landed, not `update` or `fix`). Unique in that directory.

**Rules**:
- **One file per wrapped changeset** — never append to a shared `changesets.md`
- **No index file** that lists every entry — directory order by the date prefix is the chronology
- **Nothing links in.** An entry is terminal: no stable document — the package `README.md`, its
  `README.md`, a page under `docs/`, a `docs/<area>/` feature doc — may reference an individual entry
  under `docs/architecture.md` or `docs/<area>/*/changelog/`, in any form (a `See [changesets/…](…)`
  trailer, an `**Implementation**: see …` line, a `(see [changesets/](…))` parenthetical, a
  "Change history" list of entries, or a **bare path in backticks** — the test is what it points
  at, not how it is spelled). An entry records one dated delta and is never revised, so a
  document stating current behaviour that links to one goes stale as soon as a later entry
  supersedes it; if the fact still matters, write the **fact** into the stable doc in State B. A
  single pointer at the `docs/architecture.md` **directory** in the package's documentation list is
  the permitted exception. Links out of an entry — to PRs, stable docs, other entries — are free
- **No file references** — source changesets are deleted after wrapping
- **Past tense** — "Fixed X", "Added Y", "Refactored Z"
- **Type in the `**Type:**` field** — `Feature`, `Bug Fix`, `Refactor`, `Architecture Change`

## Acceptance Tests

**Purpose**: Define what "done" looks like for a changeset.

**Types**:
- **Unit tests**: For isolated component/function changes
- **Integration tests**: For package-to-package integration changes
- **E2E tests**: For user-facing feature changes

**Format and examples**: See [the changeset structure](/.agents/skills/pr-lifecycle/references/changeset.md) for acceptance test format and detailed examples.

## Best Practices

### Do's ✅
- Keep package READMEs concise (< 200 lines)
- Use detailed docs in `packages/{package-name}/docs/` for complexity
- Always create changeset for documentation updates
- Reference related packages explicitly
- Document technical decisions in ADRs
- Keep changesets timing-agnostic (milestones, not deadlines)
- Update acceptance tests as implementation progresses
- **Maintain single README.md per package** - consolidate all package-level info there

### Don'ts ❌
- Don't modify dev docs directly (use changesets)
- Don't put implementation details in package README
- Don't create changesets without affected packages list
- Don't skip acceptance criteria in changesets
- Don't add process instructions (e.g., "use TDD") to docs
- Don't modify original changeset after wrapping
- **Don't create nested READMEs** (e.g., `test/README.md`, `src/README.md`) - use main README or detailed docs

## Related Rules and Commands

**Related Rules**:
- [feature-doc.mdc](/.agents/skills/planning/references/feature-doc.md) - **Product requirements** (WHAT to build) that drive technical implementation
- [the PRD guide](/.agents/skills/pr-lifecycle/references/prd.md) - PRD documents for tracking feature requirement changes
- [the changeset structure](/.agents/skills/pr-lifecycle/references/changeset.md) - Complete changeset document structure and requirements
- [plan-ft-dev.mdc](/.agents/commands/plan-ft-dev.md) - Creates changeset documents

**Related Commands**:
- `/wrap-context-docs` - Applies changeset to dev docs and archives it

**Documentation Hierarchy**:
```
Feature docs (WHAT)          Dev docs (HOW)
docs/<area>/                     {common,common-testing,mapping-pipeline,onboard-detection,surmap,packages}/*/docs/
├── Product requirements  →  ├── Architecture
├── User stories          →  ├── Implementation
├── Acceptance criteria   →  ├── Testing strategy
└── Success metrics       →  └── Integration patterns

{common,common-testing,mapping-pipeline,onboard-detection,surmap,packages}/*/AGENTS.md         Agent briefing (per package)

              ↓
         Changeset (DELTA)
         docs/<area>/1-WIP/
         └── Technical changes (State A → State B)
```

**Workflow Integration**:
```
Feature docs (what) → Changeset (how) → Implementation → Wrap → Updated dev docs
```
