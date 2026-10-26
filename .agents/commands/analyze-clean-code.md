---
description: Analyze code quality metrics - function length, nesting, parameters, magic values, duplication
---
## Analyze Clean Code

This command analyzes code quality metrics to identify maintainability issues and assess code quality.

## Context Documents

**Expect in context**:
- Changeset document (`docs/<area>/1-WIP/YYYY-MM-DD-*.md`) - tracks implementation progress
- PRD document (`docs/*/1-WIP/YYYY-MM-DD-*.md`) - tracks requirement changes

**Use these documents to**:
- Focus analysis on affected packages
- Update "Validation Results" section in changeset
- Update Scope checkbox for "Code Quality"

## When Invoked

1. **Check for context documents**:
   - Read changeset if provided
   - Focus on affected packages listed

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
   git diff --name-only --diff-filter=d "$mb"..HEAD | grep -E '\.(ts|tsx|js|jsx)$'
   ```

   Diff the **whole PR range** (merge-base with the PR's base), never `HEAD~1` — on a multi-commit
   PR, `HEAD~1` analyzes only the last commit and every earlier commit passes unchecked.
   Only "no PR for this branch" means `master`; any other lookup failure aborts, because guessing
   the base of a stacked PR would analyze its predecessors' commits as this PR's.

2. **Analyze each file** for clean code metrics.

## Metrics to Analyze

### Function Length
| Threshold | Rating |
|-----------|--------|
| ≤20 lines | ⭐⭐⭐ Excellent |
| 21-40 lines | ⭐⭐ Good |
| 41-60 lines | ⭐ Needs work |
| >60 lines | 🔴 Must refactor |

### Nesting Depth
| Threshold | Rating |
|-----------|--------|
| ≤2 levels | ⭐⭐⭐ Excellent |
| 3 levels | ⭐⭐ Good |
| 4 levels | ⭐ Needs work |
| >4 levels | 🔴 Must refactor |

### Parameter Count
| Threshold | Rating |
|-----------|--------|
| ≤3 params | ⭐⭐⭐ Excellent |
| 4 params | ⭐⭐ Good |
| 5 params | ⭐ Needs work |
| >5 params | 🔴 Use options object |

### Magic Values
Any literal value that should be a named constant:
- Numbers (except 0, 1, -1)
- Strings (except empty string)
- Repeated values

### Code Duplication
- Identical code blocks
- Similar logic that could be abstracted
- Copy-paste patterns

### Source File Length
Tracked source files (`.ts`, `.tsx`, `.js`, `.jsx`, `.mjs`, `.cjs`, `.mts`, `.cts`, `.rs`, `.py`) under the analyzed path. Line count is total lines in the file.

| Threshold | Rating |
|-----------|--------|
| < 300 lines | ⭐⭐⭐ Great |
| 300–499 lines | ⭐⭐ OK — reduce when possible |
| ≥ 500 lines | 🔴 Too large — prioritize for splitting |

`code-analysis issues` reports files in the two non-great buckets and intersects **too large (≥ 500)** files with git hot-files for restructuring candidates.

### Naming Quality
- Descriptive variable names
- Clear function names (verb + noun)
- Consistent naming conventions

### Slop (added lines only)
Score only the lines this PR **added**, each judged against the file it lands in:

```bash
git diff -U0 "${mb:?resolve the merge-base in step 2 first}"..HEAD -- <file>
```

`$mb` does not survive into a separate shell invocation — re-run step 2's block in the same shell, or
pass the resolved SHA literally. With `mb` unset, `git diff ..HEAD` is an empty diff and the check
would silently pass. Slop already in the file before this PR is not this PR's finding — record it
under `<package-dir>/docs/code-issues/` (`/analyze-code-issues`) instead of fixing it here.

- **Local inconsistency** — the surrounding file is the baseline, not this command's thresholds.
  Flag new code that does not match it: a different error-handling style, naming scheme or level of
  abstraction, or a re-implementation of a helper the file or package already has.
- **Defensive noise in trusted paths** — `try`/`catch` that only rethrows, or logs and carries on;
  `null`/`undefined` checks or `?.` on values whose types already rule them out; re-validating input
  a caller has already validated. Error handling belongs at trust boundaries (I/O, user input,
  external services), not between internal functions. A `catch` that swallows the error and returns
  a default is a **fallback** — forbidden without developer consent (README.md).
- **Type escapes** — `as any`, `: any`, `as unknown as T`, `@ts-ignore`, or `@ts-expect-error` with
  no stated reason, used to silence the checker instead of modelling the type. Fix the type. Where an
  escape is genuinely unavoidable (an untyped third-party boundary), keep it at that boundary.

## Output Format

```markdown
## Clean Code Analysis Report

### Files Analyzed
- file1.ts
- file2.ts

### Overall Score: X/10 ⭐

### Metrics Summary
| Metric | Score | Issues |
|--------|-------|--------|
| Function length | X/10 | Y functions too long |
| Nesting depth | X/10 | Y deeply nested blocks |
| Parameter count | X/10 | Y functions with many params |
| Magic values | X/10 | Y magic values found |
| Duplication | X/10 | Y duplicated blocks |
| File length | X/10 | Y files ≥ 500 lines |
| Naming | X/10 | Y unclear names |
| Slop (added lines) | X/10 | Y local inconsistencies, Z defensive blocks, W type escapes |

### Priority Fixes

#### 🔴 Critical (Score impact: high)
1. **[file:line]** Function `processData` is 85 lines
   - Current: Single function doing everything
   - Suggested: Split into 3-4 focused functions

#### ⚠️ Important (Score impact: medium)
1. **[file:line]** Magic number `86400`
   - Meaning: Seconds in a day
   - Fix: `const SECONDS_PER_DAY = 86400;`

#### ℹ️ Minor (Score impact: low)
1. **[file:line]** Variable `d` could be more descriptive
   - Suggested: `document` or `data`

### Refactoring Suggestions
1. Extract `validateInput()` from `processRequest()`
2. Create constant file for magic values
3. Use options object for `createUser(name, email, age, role, dept)`
```

## Update Changeset

If changeset document exists:

1. **Update Validation Results** section:

```markdown
### Code Quality (`/analyze-clean-code`)

**Last Run**: YYYY-MM-DD
**Overall Score**: X/10 ⭐

**Summary**:
- Critical issues: X
- Major issues: Y
- Minor issues: Z

**Priority Fixes**:
- [List critical issues with file:line]

**Added to Refactoring Needed**:
- [List items added]
```

2. **Update Scope** checkbox for "Code Quality" if score ≥ 7/10.

3. **Add issues** to **Refactoring Needed** section under `### From `/analyze-clean-code``.

## Reference

- **Command**: `/analyze-clean-code`
- **Rules**: `.agents/skills/coding/references/python-code-style.md`, `.agents/skills/pr-lifecycle/references/changeset.md`
