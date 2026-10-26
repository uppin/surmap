---
description: Plan new features or PRDs to existing features
---
## Plan Feature

This command guides feature planning, creating either feature documents for new features or PRD documents for changes to existing features.

**For feature documentation standards, see `.agents/skills/planning/references/feature-doc.md` rule.**
**For PRD document structure and requirements, see `.agents/skills/pr-lifecycle/references/prd.md` rule.**

## Workflow row

This command writes a PRD, not a changeset, so it writes no `[wf]` rows: the sequence
belongs to the changeset planned from the PRD, whose planning command picks the preset
(`.agents/skills/pr-lifecycle/SKILL.md` § *Presets*). When a changeset already resolves and
it has a `[wf]` row whose command is `/plan-ft` (a PRD row the developer added), it follows the
step contract for that row and records the PRD path in **Result**. The product-area and intent
questions below gather input, so they stay.

## Prerequisites

Understand the user's intent:
1. **New feature?** → Create PRD document first (proposal/spec)
2. **Updating existing feature?** → Create PRD document referencing affected features

## Workflow

### 1. Identify Product Area

Determine which product area the feature belongs to:
- `onboard-capture` - Stereo + GPS capture on the CM5 (Machine 1)
- `onboard-detection` - Coral Edge TPU detection and tracking (Machine 1)
- `slam-mapping` - RTAB-Map registration and static-scene points (`src/surmap/slam/`)
- `reconstruction` - 3D points of detected objects, motion split, map layers
- `base-station` - SAM 3.1 segmentation, semantic labelling, semantic map (Machine 2)
- `simulation` - Synthetic sessions and recorded-session replay (Machine 3)
- `infrastructure` - Logging, observability, session storage

### 2. Create PRD Document

**CRITICAL**: Always start with PRD document, even for new features.

**Location**: `docs/{product-area}/1-WIP/PRD-YYYY-MM-DD-feature-name.md`

**New features**: PRD acts as proposal/spec
**Feature changes**: PRD references ALL affected feature documents

### 3. Write PRD Content

Use `.agents/skills/planning/references/feature-doc.md` rule template for structure:
- Summary of feature/change
- Background and rationale
- Requirements and acceptance criteria
- For updates: List ALL affected feature documents with links

### 4. Product Area Overview — a new feature doc only

When this command creates a **new feature document** in the product area, add it to
`docs/{product-area}/1-OVERVIEW.md`. **Never reference the PRD itself** there or in any other
stable document — nothing links into `1-WIP/` (`docs/AGENTS.md` § *Nothing links into `1-WIP/`*).
A requirement change to an existing feature leaves `1-OVERVIEW.md` untouched until wrap.

### 5. Add Assets (if needed)

Place diagrams, screenshots in `docs/{product-area}/appendices/`

## Output

Print this line (replace with actual path):
```
**CRITICAL FOR CONTEXT & SUMMARY**
PRD created: docs/{product-area}/1-WIP/PRD-YYYY-MM-DD-feature-name.md
[For updates: Affected features: path1.md, path2.md, ...]
```

When a `## Workflow` row was run, end with the skill's summary instead.

## Best Practices

✅ **Do:**
- Always create PRD first (even for new features)
- Use descriptive filenames (kebab-case)
- List ALL affected features in PRDs
- Add a new feature document to 1-OVERVIEW.md
- Place features in correct product area

❌ **Don't:**
- Don't modify original feature documents when requirements change
- Don't create PRDs without listing affected features
- Don't link a PRD, changeset or discovery file from 1-OVERVIEW.md or any stable doc — nothing
  links into `1-WIP/`
- Don't mix product areas

## Related

**Rules**: `.agents/skills/planning/references/feature-doc.md`, `.agents/skills/pr-lifecycle/references/prd.md`, `/requirements-change`
**Commands**: `/plan-ft-dev`, `/plan-red` (the planning commands that turn a PRD into a changeset)
