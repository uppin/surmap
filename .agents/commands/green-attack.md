---
description: Exploratory green implementation - deep dive without requiring tests to pass
  Explore the “green” implementation direction without expecting tests to pass.
  Deep dive into the failing scenario, try meaningful changes, surface lessons,
  and capture what to attempt next.
---
## Green-Attack Flow

## Workflow row

Follows the `pr-lifecycle` skill (`.agents/skills/pr-lifecycle/SKILL.md`). It owns no
preset row: it runs as a row only when the developer swaps it into a Green row, and invoked by hand
outside a row it changes no `## Workflow` row. As a row, it closes per its outcome:

- **✅** only when every red test the row is responsible for passes **and** the diff is
  production-quality — the diagnostics and temporary checks removed. Result: the commit SHA and the
  red → green count.
- **⛔** otherwise — the normal outcome of an exploration. Result: the likely root cause in one line;
  the options go in the summary's *Needs you* (for example a) swap the row back to `/green` with these
  findings, b) another `/green-attack` on approach X, c) re-plan). The findings are written into the
  changeset (*Documentation Updates* below) and committed with the row; exploratory diagnostics are
  reverted, and only production-quality progress is committed.
- **⛔** also for the stack gates in step 0, with the evidence in Result.

**Row TODOs** (as a row only):

- Stack rebased, ancestor-functionality gate passed (step 0 — stack branch only)
- Failures identified (1)
- Findings written into the changeset (*Documentation Updates*)
- Diagnostics reverted, production-quality progress committed

### 0. If This PR Is Part of a Stack — Pre-run (HARD GATE)

Detect **before** running tests or exploring. Bind every check to **this branch**. A
`Stack Context` in some other PR's changeset does not make this branch stacked. An empty
`git branch --show-current` (detached HEAD) is **not** a match — do not grep with it.

```bash
BRANCH=$(git branch --show-current)
# 1. Registered stack that includes this branch (fails if this branch is not in a stack)
gh stack view 2>/dev/null | grep -F "$BRANCH"
# 2. This branch's own changeset: same file has ## Stack Context AND this branch name
if [ -n "$BRANCH" ]; then
  grep -l "## Stack Context" docs/<area>/1-WIP/*.md 2>/dev/null \
    | xargs grep -l --fixed-strings "$BRANCH" 2>/dev/null
fi
# 3. This branch's open PR is based on another stack branch (not trunk)
gh pr view --json baseRefName --jq .baseRefName 2>/dev/null
```

**Stack branch** if (1) lists `$BRANCH`, or (2) returns a file, or (3) returns a base that is not
`master` / `main` / the repo default trunk. Load the `pr-stack` skill
(`.agents/skills/pr-stack/SKILL.md`) and run **0a then 0b before step 1**.

If none of those hit, skip this section — this is an ordinary branch.

Do **not** `grep -l "Inherited Dependencies"` or `grep -l "Stack Context"` across `1-WIP` without
requiring this branch's name in the same file.

**0a. Rebase first — `/pr-stack-rebase`**

Run **`/pr-stack-rebase`** (this branch only) and follow `.agents/commands/pr-stack-rebase.md`.
A ⚠-free `gh stack view` is **not** a skip: exploration must start from the latest pushed ancestor
implementation. If the branch is already on the latest base tip and `origin/<base>..HEAD` is this
PR's commits only, that command verify-and-publishes (no rewrite, but it pushes the branch if the remote lacks this
state); that still counts as having run it. Exploration starts only after the rebased state is on
the remote (`/pr-stack-rebase` Step 4b).

Do **not** explore on a stale parent. Do **not** run `gh stack sync` / `gh stack rebase` from this
worktree.

**0b. Ancestor-functionality gate — MUST halt if unmet**

After the rebase, check that **functionality this PR depends on from ancestor PRs is implemented**.
A stacked branch inherits predecessors' **code**, including their stubs. Compiling against a stub is
not the same as depending on its behaviour.

1. Read this PR's changeset: `## Inherited Dependencies — do not implement here` and
   `## Stack Context` → **`### Green wave`** and **Greenable independently?**. The wave is the quick
   read; this gate is the fact. If they disagree, the tree wins — correct the wave in this PR's
   changeset.
2. After rebase, inspect each predecessor-owned symbol this PR uses in the current tree. A symbol
   is **still unimplemented** when its body is a planning stub: `NotImplementedError`, a typed
   placeholder, or `TODO(pr-<ancestor>)`.
3. This PR **depends on that functionality** when any of the following is true:
   - The changeset says **Greenable independently? no — blocked by n\<j\>** (node numbers, not PR
     numbers — see the `pr-stack` skill § *Node numbers*; `n<j>` is branch `pr-<j>-<slug>`) and that
     node still owns those stubs.
   - This PR's tests drive the **real** predecessor object (not a test double) and would need its
     behaviour — not merely its signature — to pass.
   - The Inherited Dependencies table describes a runtime call that needs the ancestor's real
     behaviour, not compile-only use of the type.
4. Compile-only use is **not** a dependency on implementation: coding against the stub's signature,
   or injecting a double at the test seam, is how an independently greenable PR proceeds while the
   ancestor is still a stub. Those cases pass this gate.
5. If this PR **does** depend on ancestor functionality that is still a stub: **halt ⛔. Do not
   explore or implement anything.** Result and the summary's *Needs you* state:
   - which symbols are still stubs, with file:line;
   - which ancestor PR owns each (number, URL, branch);
   - why this PR needs the real behaviour (which tests / greenability line);
   - that you will **not** implement a predecessor-owned symbol from here.

   The options, for example: a) wait for that ancestor's Green row to land and re-invoke; b) inject
   doubles and proceed as independently greenable; c) drop or rescope the blocked tests; or another
   instruction the developer gives on re-invocation. Do not pick for them. Do not silently continue.

An undeclared dependency is the same halt: if the changeset says independently greenable but the
tests actually require ancestor behaviour that is still stubbed, halt ⛔.

Do **not** implement a predecessor-owned symbol during exploration, even if filling the stub looks
like the fastest way to learn.

### 1. Run Tests to Identify Failures

**Run the test suite to see current state:**
```bash
cd packages/package-name
uv run pytest -q
```

Capture:
- Which tests are failing?
- What error messages appear?
- What functionality is missing?
- What edge cases are broken?

### 2. Switch to Plan Mode

**CRITICAL**: Switch to Plan mode for exploratory thinking:

```
On Muse: use the plan mode tool to switch to 'plan' mode.
On other harnesses: enter the harness's plan mode (in Claude Code, `/plan`).
```

**Reason for Plan mode:**
- Need to explore multiple approaches without committing
- Can think through complex scenarios collaboratively
- User can guide exploration direction
- Better for discussing trade-offs and unknowns

### 3. Exploratory Implementation (in Plan Mode)

**This differs from `/green`**: The explicit goal is **not actually to make the tests pass**. The purpose is to:
- Dig into the failure and understand root causes
- Exercise plausible fixes and see what happens
- Learn how close we are to a solution
- Uncover assumptions and constraints

**Spend maximum effort and maximal iterations**:
- Modify code with different approaches
- Add diagnostics and logging
- Adjust dependencies
- Try real, production-quality adjustments
- Do **everything** you can to dig into the root cause

**Important**: Don't stress about finishing all the way to a passing suite. Try real adjustments that might unblock the failure.

### 4. Success Metrics

It is **perfectly acceptable** if tests still fail at the end. The success metric is:
- **What did we uncover?**
- **How much progress toward the root cause?**
- **What assumptions were validated or busted?**
- **What lessons were learned?**

### 5. Critical Rules

**STRONGLY FORBIDDEN**:
- ❌ Skipping tests
- ❌ Deleting tests
- ❌ Commenting out failing tests
- ❌ Using `.skip` or `.only`
- ❌ Starting exploration on a stack branch without `/pr-stack-rebase` and the ancestor-functionality gate
- ❌ Implementing a predecessor-owned symbol (even as an experiment)

**Better to keep tests failing** to convey real status of implementation.

## Output Format

```markdown
## 🔬 Green-Attack Exploration Report

### Test Status
**Initial state:**
```bash
uv run pytest -q
```
- X tests failing
- Y tests passing
- Key failures: [list main issues]

**Final state:**
```bash
uv run pytest -q
```
- X tests failing (changed from initial)
- Y tests passing (changed from initial)
- Progress: [improvement percentage or description]

### Plan Mode Exploration ✅

**Switched to Plan Mode**: ✅

**Approaches Explored:**
1. **Approach A**: [description]
   - What was tried
   - What happened
   - What was learned

2. **Approach B**: [description]
   - What was tried
   - What happened
   - What was learned

3. **Approach C**: [description]
   - What was tried
   - What happened
   - What was learned

### Changes Made

**Files Modified:**
- `src/feature.ts` - [what was changed and why]
- `src/helpers.ts` - [what was added for diagnostics]

**Diagnostics Added:**
- Logging at key points
- Debug output for state inspection
- Temporary validation checks

**Dependencies Adjusted:**
- [Any dependency changes attempted]

### Key Lessons Learned

**Assumptions Validated:**
- ✅ [Assumption that turned out correct]
- ✅ [Another validated assumption]

**Assumptions Busted:**
- ❌ [Assumption that was wrong]
- ❌ [Another incorrect assumption]

**Unexpected Behavior:**
- [Surprising behavior discovered]
- [Another unexpected finding]

**Useful Insights:**
- [Technical insight gained]
- [Another learning point]

### Root Cause Progress

**Understanding Level**: [None → Partial → Good → Complete]

**What we know now:**
- [Key finding 1]
- [Key finding 2]
- [Key finding 3]

**What's still unclear:**
- [Unknown 1]
- [Unknown 2]

**Likely root cause**: [Best hypothesis based on exploration]

### Next Steps Recommended

**Immediate Actions:**
1. [Next experiment to try]
2. [Code area to focus on]
3. [Missing instrumentation to add]

**Alternative Approaches:**
- Option A: [description and pros/cons]
- Option B: [description and pros/cons]

**⛔ Needs you** (when the row halts):
- [Decision about requirements/constraints, with options a) … b) …]
- [Decision about approach preference, with options a) … b) …]

### Documentation Updates

**If changeset exists**, add exploration findings:
```markdown
### Green-Attack Exploration (YYYY-MM-DD)

**Goal**: Explore [feature] implementation approaches

**Findings**:
- [Key lesson 1]
- [Key lesson 2]

**Progress**: [X% toward passing tests]

**Next Actions**:
- [Recommended next step]
```

### Summary

**Technical Outcome**: [Tests still failing | Some progress | Closer to solution]

**Learning Journey**: [High-level summary of what was discovered and value gained]

**Row**: [✅ <commit>, N/N green | ⛔ <likely root cause>] — inside the skill's summary
```

## Workflow Summary

```
/green-attack invoked
       ↓
0. If stack branch: /pr-stack-rebase, then ancestor-functionality gate
   (halt ⛔ if a required ancestor is still a stub)
       ↓
1. Run tests to see failures (Agent mode)
       ↓
2. Switch to Plan mode (Muse: plan mode tool; Claude Code: `/plan`)
       ↓
3. Explore implementation approaches (Plan mode)
       ↓
4. Try multiple approaches, add diagnostics
       ↓
5. Document findings and learnings
       ↓
Close the row ✅ / ⛔ and report exploration results (tests may still fail ✓)
```

**Key Difference from `/green`**:
- `/green`: Plan → Implement → Tests must pass
- `/green-attack`: Plan → Explore directly → Tests may still fail (learning is the goal)

## When to Use

Use `/green-attack` when:
- Tests are complex and you need to explore
- Root cause is unclear and need investigation
- Want to try multiple approaches collaboratively
- Learning and discovery is more valuable than immediate passing tests
- Need user guidance on which direction to pursue

Use `/green` when:
- Tests are straightforward
- Implementation approach is clear
- Ready to commit to an approach
- Want tests to pass in one go

**Stack branches:** both `/green` and `/green-attack` run `/pr-stack-rebase` and the
ancestor-functionality gate before doing anything else. See `/green` and the `pr-stack` skill.
