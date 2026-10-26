---
description: Validate code is production ready - mock code, fallbacks, TODOs, unused code
---
## Validate Production Readiness

This command validates that code is ready for production deployment by checking for mock code, development fallbacks, TODO markers, and unused code.

## Context Documents

**Expect in context**:
- Changeset document (`docs/<area>/1-WIP/YYYY-MM-DD-*.md`) - tracks implementation progress
- PRD document (`docs/*/1-WIP/YYYY-MM-DD-*.md`) - tracks requirement changes

**Use these documents to**:
- Review "Technical Debt & Production Readiness" section
- Validate all tracked debt is addressed
- Update "Validation Results" section in changeset
- Tick the row's technical-debt TODO, if it has one

## When Invoked

1. **Check for context documents**:
   - Read changeset if provided
   - Review "Technical Debt & Production Readiness" section

2. **Identify changed files**:
   ```bash
   err="${TMPDIR:-/tmp}/pr-base.err"
   if ! base=$(gh pr view --json baseRefName --jq .baseRefName 2>"$err"); then
     grep -q 'no pull requests found' "$err" \
       || { cat "$err" >&2; echo "ERROR: cannot resolve the PR's base — fix before proceeding, do not skip" >&2; exit 1; }
     base=master   # no PR yet: an ordinary branch, based on master
   fi
   git fetch origin "$base" --quiet \
     || { echo "ERROR: cannot fetch origin/$base — fix before proceeding, do not skip" >&2; exit 1; }
   mb=$(git merge-base "origin/$base" HEAD) \
     || { echo "ERROR: no merge-base with origin/$base — fix before proceeding, do not skip" >&2; exit 1; }
   git diff --name-only --diff-filter=d "$mb"..HEAD
   ```

   Diff the **whole PR range** (merge-base with the PR's base), never `HEAD~1` — on a multi-commit
   PR, `HEAD~1` analyzes only the last commit and every earlier commit passes unchecked.
   Only "no PR for this branch" means `master`; any other lookup failure aborts, because guessing
   the base of a stacked PR would analyze its predecessors' commits as this PR's.

2. **Scan for production readiness issues**.

## Checks to Perform

### Mock/Fake Code in Production
Search for patterns that indicate test code leaked into production:
- `mock`, `Mock`, `MOCK`
- `fake`, `Fake`, `FAKE`
- `stub`, `Stub`, `STUB`
- `spy`, `Spy`
- `jest.fn()`, `vi.fn()`

**Exception**: Files in `test/`, `__tests__/`, `*.test.*`, `*.spec.*`

### Development Fallbacks
Look for fallbacks that bypass production behavior:
- `|| 'default'` without proper configuration
- `process.env.NODE_ENV === 'test'` in production code
- `if (isDevelopment)` blocks with different behavior

### TODO/FIXME Markers
Find unresolved work items:
- `TODO:`
- `FIXME:`
- `HACK:`
- `XXX:`

Determine if they should be:
- **Resolved before merge** — the default. A marker in code this changeset wrote is unfinished work,
  not documentation.
- **Recorded as deferred work** — a `<package-dir>/docs/todo/` file naming the blocker, the refuted
  alternatives and, for **planned** scope, the developer's recorded decision (their answer to a ⛔
  halt — `.agents/skills/pr-lifecycle/SKILL.md` § *Halts*). Cross-check: every
  marker this changeset introduced should either be gone or traceable to a file in `<package-dir>/docs/todo/`
  (`deferred-work` skill). A marker with neither is a silent scope cut — report it as ⚠, not ✅.
- **Pre-existing debt in code this changeset only passed through** — a
  `<package-dir>/docs/code-issues/` record and somebody's future Step 2b problem, not a blocker here.
- **`TODO(pr-<k>)`** — a stack planning stub. Owned by PR *k*; a hit for **this** PR's own `k` is a
  blocker, a hit for another `k` is not this PR's business.
- Converted to a tracked issue (`/tech-backlog`) when it is long-lived technical work rather than a
  gap this changeset left.

### Unused Code
Identify dead code:
- Unused imports
- Unused variables
- Unreachable code
- Commented-out code blocks

### Console Statements
Find debug output:
- `console.log`
- `console.debug`
- `debugger` statements

## Output Format

```markdown
## Production Readiness Report

### Files Analyzed
- X production files
- Y test files (excluded from checks)

### Issues Summary
| Category | Count | Status |
|----------|-------|--------|
| Mock code | X | 🔴/✅ |
| Dev fallbacks | X | 🔴/✅ |
| TODO/FIXME | X | ⚠️/✅ |
| Unused code | X | ⚠️/✅ |
| Console statements | X | ⚠️/✅ |

### Issues Detail

#### 🔴 Must Fix Before Merge
1. **[file:line]** Mock implementation in production
   ```python
   # problematic code
   ```

#### ⚠️ Should Address
1. **[file:line]** TODO marker
   - Content: "TODO: implement validation"
   - Recommendation: Create issue or implement

#### ✅ Acceptable
1. **[file:line]** TODO with issue reference
   - Content: "TODO(#123): optimize query"
2. **[file:line]** TODO backed by a deferred-work record
   - Content: "TODO: analyzer port wiring"
   - Record: `<package-dir>/docs/todo/2026-09-02-analyzer-port-wiring.md` — blocker named, consent recorded
3. **[file:line]** `TODO(pr-3)` — a stub owned by another stack PR, not this one

### Verification
```bash
uv run pytest -q
uv run mypy
```
```

## Update Changeset

If changeset document exists:

1. **Update Validation Results** section:

```markdown
### Production Readiness (`/prod-ready`)

**Last Run**: YYYY-MM-DD
**Status**: ✅ Ready | ⚠️ Gaps | ❌ Blockers

**Summary**:
- Mock code in production: X instances
- TODO/FIXME markers: Y (of which Z backed by a `<package-dir>/docs/todo/` record, W unaccounted for)
- Unused code: Z

**Blockers**:
- [List must-fix items]

**Added to Technical Debt**:
- [List items added]
```

2. **Tick the row's technical-debt TODO**, if it has one, when all items are addressed.

3. **Add issues** to **Refactoring Needed** section under `### From `/prod-ready``.

## Reference

- **Command**: `/validate-prod-ready`
- **Rules**: `.agents/skills/coding/references/coding-practices.md`, `.agents/skills/pr-lifecycle/references/changeset.md`
