---
description: Refresh the repo's assistant guidance catalog and revision tracking for the unified `.agents` setup
---
# Update All Rules

Use this command when the repo's active assistant guidance has changed and the shared catalog needs
to be brought back into sync.

## Goal

Keep the repo's assistant-facing documentation accurate, skill-centric, and easy for humans to use.

The main source of truth to refresh is:

- `.agents/skills/repo-maintenance/references/ALL-RULES.md`

Supporting docs to check when needed:

- `README.md`
- `.agents/README.md`
- `.agents/skills/*/SKILL.md`
- `.agents/commands/*.md`

## When To Use

Apply this command when:

- a skill or command was added, removed, renamed, or materially repurposed
- repo guidance changed in a way that affects how users should invoke workflows
- `README.md` or `.agents/README.md` drifted from the current `.agents` structure
- a regular file has appeared under `.claude/commands/`, `.claude/skills/`, `.muse/commands/` or
  `.muse/skills/` where a symlink belongs (see step 2)
- the user explicitly asks to "update all rules"

Do not use it for wording-only edits that do not affect structure, mapping, or usage guidance.

## Scope

This repo uses a single canonical `.agents` tree:

- `README.md` is the top-level repo briefing (Claude Code loads it natively; the former `CLAUDE.md` was removed in its favour)
- `.agents/commands/*.md` are the slash-command entrypoints, shared by every harness
- `.agents/skills/*/SKILL.md` define active reusable workflows
- `.agents/skills/*/references/*.md` hold supporting material for those workflows

`.claude/` and `.muse/` hold only **symlinks** into `.agents/`, plus their own per-harness
`agents/`, `hooks/` and MCP configuration, which are intentionally not shared.

## Revision Tracking Rules

1. Every tracked item in `ALL-RULES.md` should have a `**Last Revised**: YYYY-MM-DD` line.
2. The revision date must come from the source file's filesystem modification date.
3. Only update a recorded revision date when the source file's date is newer than what
   `ALL-RULES.md` already shows.
4. If an item was removed from the current system, remove its entry rather than preserving stale
   revision metadata.

Source paths:

- Commands: `.agents/commands/<name>.md`
- Skills: `.agents/skills/<skill>/SKILL.md`
- Compatibility aliases: the alias skill's own `SKILL.md`

Date command:

```bash
stat -f "%Sm" -t "%Y-%m-%d" <path>
```

## Update Process

### 1. Discover current components

Review only the files needed to understand the current state: `README.md`,
`.agents/README.md`, the relevant `.agents/commands/*.md` and `.agents/skills/*/SKILL.md`, and
`.agents/skills/repo-maintenance/references/ALL-RULES.md`.

### 2. Verify the symlink farms have not drifted

Every entry under `.claude/commands`, `.claude/skills`, `.muse/commands` and `.muse/skills` must
resolve into `.agents/`. A regular file there is unmigrated drift — the exact failure this unified
layout exists to prevent.

```bash
for d in .claude/commands .claude/skills .muse/commands .muse/skills; do
  [ -L "$d" ] && continue                     # whole-directory symlink: fine
  find "$d" -maxdepth 1 -mindepth 1 ! -type l -print
done
```

Report anything this prints, and fold its content into the matching `.agents/` file before
replacing it with a symlink.

### 3. Compare against the catalog

Check whether `ALL-RULES.md` is missing or misrepresenting active commands, active skills, renamed
items, compatibility aliases, preferred invocation examples, or revision dates.

### 4. Update documentation

Refresh `ALL-RULES.md` so it is skill-centric, consistent with `README.md`, and
explicit about invocation examples and compatibility aliases. Update `README.md` and
`.agents/README.md` only if they need to change to stay aligned.

### 5. Validate consistency

Check for broken file references, stale command or skill names, references to removed directories or
old layouts, and mismatched invocation syntax.

### 6. Report back

Summarize what changed, which revision dates were updated, and any remaining drift that was
intentionally left alone.

## Editing Guidance

- Prefer the active `.agents` structure over preserved historical wording.
- Keep `ALL-RULES.md` practical for humans, not exhaustive.
- Show concrete invocation examples for each harness, e.g. `/tdd`, `$tdd reproduce this bug with a
  failing test`.
- Do not invent runtime features a harness does not actually support; when a workflow is
  harness-specific, label it as such rather than describing it as shared.

## Related

**Skill**: `repo-maintenance` (`.agents/skills/repo-maintenance/SKILL.md`)
**Catalog**: `.agents/skills/repo-maintenance/references/ALL-RULES.md`
