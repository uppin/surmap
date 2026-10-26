---
description: Split code into separate branches
---
## Split Branch - Export Code to Separate Branches

This command handles splitting current work into multiple branches for better organization.

## Use Cases

1. **Move all code to new branch** (default if unspecified)
2. **Split functionality** between current and new branch

## Prerequisites

Understand what needs to be split:
- What goes to new branch?
- What stays in current branch?
- Is this a full move or partial split?

## Workflow

### 1. Commit Uncommitted Code

Ensure all changes are committed before proceeding:
```bash
git add .
git commit -m "Work in progress before split"
```

### 2. Create Backup Branch

**🚨 SUPER CRITICAL: Keep backup frozen (never modify)**

```bash
git branch backup-YYYY-MM-DD-HH-MM
```

This preserves original state for recovery if needed.

### 3. Create Split Document

Create `tmp/split-YYYY-MM-DD-HH-MM.md` (don't add to git):

```markdown
# Branch Split - YYYY-MM-DD HH:MM

## Branches
- **Original**: [current-branch-name]
- **New**: [new-branch-name]
- **Backup**: backup-YYYY-MM-DD-HH-MM (FROZEN - do not modify)

## Split Type
[Full Move | Partial Split]

## Functionality Distribution

### Goes to New Branch
- Feature/functionality 1
- Feature/functionality 2
- Files: [list key files]

### Stays in Original Branch
- Feature/functionality 3
- Feature/functionality 4
- Files: [list key files]

## Procedure Followed
1. Created backup branch ✅
2. Created new branch from current ✅
3. Reset new branch to origin/master ✅
4. Removed non-relevant functionality from new branch ✅
5. Compiled and committed new branch ✅
6. Switched back to original branch ✅
7. Removed moved functionality from original ✅
8. Compiled original branch ✅

## Status
[In Progress | Complete]
```

### 4. Execute Split

#### A. Full Move (Default)

Move all current code to new branch:

```bash
# Create new branch from current (includes all changes)
git checkout -b new-feature-branch

# Current branch now has all changes
# Original branch needs reset

# Switch back to original
git checkout original-branch

# Reset to master (removes all changes)
git reset --hard origin/master

# Done: new-feature-branch has all code
```

#### B. Partial Split

Split functionality between branches:

**Step 1: Create new branch**
```bash
git checkout -b new-feature-branch
```

**Step 2: Reset to master (uncommits all changes)**
```bash
git reset origin/master
# All changes now uncommitted in new branch
```

**Step 3: Remove functionality staying in original**

Carefully revert files/changes that should NOT be in new branch:
```bash
git checkout -- files-to-remove.ts
# Or manually delete/modify files
```

**Step 4: Commit new branch**
```bash
git add .
git commit -m "Split: [new branch functionality]"
```

Verify code compiles:
```bash
for pkg in <affected-packages>; do
  uv run mypy && uv run pytest -q
done
```

**Step 5: Switch to original branch**
```bash
git checkout original-branch
```

**Step 6: Remove functionality moved to new branch**

"Negative" changes - remove what went to new branch:
```bash
# Identify what was added in new branch
git diff original-branch new-feature-branch

# Remove those changes from original
# Manually delete/modify files
```

**Step 7: Commit original branch**
```bash
git add .
git commit -m "Split: removed [moved functionality]"
```

Verify code compiles:
```bash
for pkg in <affected-packages>; do
  uv run mypy && uv run pytest -q
done
```

### 5. Verify Both Branches

**New branch:**
```bash
git checkout new-feature-branch
for pkg in <affected-packages>; do
  uv run mypy && uv run pytest -q
done
```

**Original branch:**
```bash
git checkout original-branch
for pkg in <affected-packages>; do
  uv run mypy && uv run pytest -q
done
```

Both should compile and have working tests.

### 6. Update Split Document

Mark procedure complete in `tmp/split-*.md`:
```markdown
## Status
✅ Complete

## Verification
- New branch compiles: ✅
- New branch tests pass: ✅
- Original branch compiles: ✅
- Original branch tests pass: ✅

## Final State
- New branch: [commits, functionality summary]
- Original branch: [commits, functionality summary]
- Backup: [commit hash] (preserved)
```

## Output Format

```markdown
## 🔀 Branch Split Complete

### Branches Created
- **New**: `new-feature-branch` - [functionality summary]
- **Original**: `original-branch` - [functionality summary]
- **Backup**: `backup-YYYY-MM-DD-HH-MM` - 🔒 Frozen (recovery only)

### Split Type
[Full Move | Partial Split]

### New Branch
**Functionality:**
- Feature A
- Feature B
- [X files changed]

**Status:**
- Compiles: ✅
- Tests pass: ✅
- Commit: [commit hash]

### Original Branch
**Functionality:**
- Feature C
- Feature D
- [Y files changed]

**Status:**
- Compiles: ✅
- Tests pass: ✅
- Commit: [commit hash]

### Backup Branch
**Commit**: [commit hash]
**Purpose**: Recovery if needed
**⚠️ NEVER MODIFY THIS BRANCH**

### Split Document
Created: `tmp/split-YYYY-MM-DD-HH-MM.md`
(Not in git - local reference only)

### Verification Results
- ✅ Both branches compile
- ✅ Both branches tests pass
- ✅ Functionality correctly distributed
- ✅ Backup preserved

### Next Steps
1. Continue work on new branch: `git checkout new-feature-branch`
2. Continue work on original: `git checkout original-branch`
3. Backup available if needed: `git checkout backup-YYYY-MM-DD-HH-MM`
```

## Recovery Process

If split went wrong, recover from backup:

```bash
# Delete failed branches (if needed)
git branch -D new-feature-branch

# Restore from backup
git checkout backup-YYYY-MM-DD-HH-MM
git checkout -b original-branch-recovered

# Start split process again
```

## Best Practices

✅ **Do:**
- Always create backup branch first
- Verify code compiles on both branches
- Run tests on both branches
- Document split in tmp directory
- Keep backup branch frozen
- Test functionality distribution

❌ **Don't:**
- Don't skip backup creation
- Don't modify backup branch
- Don't forget to compile/test both branches
- Don't lose track of what goes where
- Don't add split document to git
- Don't proceed with broken code

## Common Pitfalls

**Incomplete functionality separation:**
- Files shared between features not properly split
- Dependencies not updated correctly
**Fix**: Carefully analyze file-by-file what each branch needs

**Broken imports after split:**
- Code references removed functionality
**Fix**: Update imports and dependencies on both branches

**Tests failing after split:**
- Test helpers or fixtures not properly distributed
**Fix**: Ensure test infrastructure complete on both branches

## Related

**Rules**: `.agents/skills/pr/references/git-usage.md`
**Commands**: `/split-pr-to-stack` (when the slices must be a **stack** — `A→B1→B2`, not two
siblings off `master`), `/pr` (for each branch), `/merge` (if branches need merging later)
**Skill**: `pr-stack` (`.agents/skills/pr-stack/SKILL.md`) — only if the split should land as
stacked PRs; otherwise this command stays a sibling-branch split.
