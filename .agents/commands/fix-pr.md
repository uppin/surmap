---
description: Fix a PR - address review threads (the full discussion, including human replies and reactions to bot comments) AND failing checks; signal verdicts with GitHub reactions (agree = thumbs-up, fix pushed = rocket) and disagreement with a reply that carries the evidence - never a thumbs-down, rebase a stacked branch first, and while checks are still running poll and fix failures as they appear instead of waiting for the full run
---
## Fix PR — address review comments and failing checks

Work a PR toward mergeable, end to end. Two workstreams feed one fix loop:

- **Review threads** — triage each **discussion** (every reply and human reaction, not just the
  opening comment), **signal the verdict on GitHub itself via reactions**, fix what deserves fixing.
- **Checks** — diagnose every failed check; if checks are still running, **poll and start fixing
  failures as they appear** — never idle until the whole run completes.

The reactions are the status protocol reviewers see, so they are not optional decoration:

| Reaction | Meaning | When |
|---|---|---|
| 👍 `+1` | Agree — a fix is coming | Immediately after triage, **before** starting the fix |
| 🚀 `rocket` | The fix for this comment is pushed | After the push succeeds, on each addressed comment |

A comment can accumulate 👍 then 🚀 (agreed, then fixed). A 👍 is a promise — never 👍 a comment and
then silently drop the fix; if implementation proves the comment wrong after all, reply saying so.

**There is no negative reaction. Disagreement is a reply, always.** A 👎 is a bare verdict with no
reasoning attached: the reviewer cannot tell whether the claim was factually wrong, out of scope,
or simply misread, and it reads as dismissal from an author who owes an explanation. Everything a
thumbs-down would signal belongs in prose the reviewer can check and argue with — so a disagreement
gets a reply carrying the evidence, and no reaction at all. Never post `-1` to any reactions
endpoint.

## Post-wrap — no row, no TODOs

A post-wrap procedure (`pr-lifecycle` skill § *Post-wrap*): it has no `[wf]` row and seeds no
TODO, and it adds nothing to the PR description's `## Workflow` section (Step 0's legacy-row
cleanup is its only edit there). Its state is GitHub's — the
head SHA, its checks, its threads — so a re-run on new threads or failures starts again from
Step 0 and finds what is still open. Done when Step 6's exit condition holds and Step 7 passed:
`<sha> · checks green · <n> threads (<f> fixed, <r> replied)`. Halts, beyond the skill's, are the
summary's **⛔ Needs you**: a flaky or infra check that needs a retrigger (named); the same check
red on a **third** consecutive push; a fix for one failure that keeps causing another; a merged or
closed PR; uncommitted tracked changes unrelated to the fixes. Reacting and replying on threads is
this command's normal work, not a gate.

## Composer offload (`#composer-subagent`, `#coder`)

With `#composer-subagent` (or `#composer`) in the request, this command's work is done by the Muse
agent (`agent -p`) on the newest Composer model, driven by a Sonnet · low subagent — the
`composer-subagent` skill (`.agents/skills/composer-subagent/SKILL.md`), stage F (a fresh session), with the
skill's **row consent**. `#coder` does the same on a Coder workspace (`coder-remote` skill) and implies
`#composer-subagent`. The main agent readies the host (guiding the user through a missing Muse agent
CLI or login), runs the preflight, briefs the driver, reports a halt — the Muse agent's ⛔ — in its
end-of-turn summary, and verifies the result. Every step of this file still runs; only who types changes. A retrigger and a third push for the same failing check come back as a ⛔ halt; a disagreement reply is posted and reported, as below.
Only on request — never chosen on the agent's own initiative. Every modifier this command honours,
`#yolo` included, is defined once in the `behaviour-modifiers` skill
(`.agents/skills/behaviour-modifiers/SKILL.md`).

## Step 0: Resolve the PR

- Default: the PR of the **current branch**. `$ARGUMENTS` may name a PR number or branch instead.
- ```bash
  repo=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
  gh pr view <N> --json number,title,url,state,isDraft,baseRefName,headRefName,reviewDecision
  ```
- If the PR is merged or closed, **halt ⛔** — there is nothing to fix; the summary names
  `/follow-up-branch` as the option for acting on post-merge comments.
- If the working tree has uncommitted tracked changes, **halt ⛔** — PR fixes must not be
  entangled with unrelated in-flight work.
- If the PR body's `## Workflow` still carries rows after Wrap (PR, Checks and threads, Approve,
  Land — planned before the rows ended at Wrap), first carry out what an open TODO under them
  still owes outside GitHub's own state — an open `Stash:` ready publish is made now, per the
  `roadmap-driven-development` skill § *Publish* (once `isDraft` is false; manual mode reports the
  advice) — then delete the rows with their TODOs from the body (`pr-lifecycle` skill, step
  contract step 2 *Rows after Wrap*) and say so in the report. The other TODOs (checks, threads,
  readiness, approval) are this command's or `/yolo`'s ordinary work and need no carrying. That
  is the only edit this command makes to the `## Workflow` section.

## Step 1: Stack currency — BEFORE reading any diff or writing any fix

Determine whether this branch is part of a PR stack (the base-tracking order from the `pr-stack`
skill: `gh stack view`, the changeset's `## Stack Context`, or a non-master `baseRefName`).

- **Stack member** → run `/pr-stack-rebase` in **single mode** on this branch now. This is a
  hard gate exactly like `/green`'s: comments and check failures are evaluated against the code,
  and a stale merge-base makes leaked ancestor commits look like this PR's work. Already-current is
  verify-and-publish — cheap, never a skip — and the rebased state is pushed **before** any
  comment or check fix is started, so every fix lands on a published baseline. Never widen into cascade mode from here.
- **Ordinary branch** → make sure the branch is current enough that comments map onto the code
  (`/merge` if the user wants the base merged in; do not do it unprompted).

If the rebase force-pushed, note it in the report — the push restarts CI (fold that run into the
Step 3 loop), and review comments on rewritten lines become "outdated" on GitHub, but they still
get triaged (Step 2).

## Step 2: Collect workstream A — review **threads**, not lone comments

A review comment is not a lone note. Humans reply to bots, react to replies, and refine the ask.
**Collect the whole discussion on every thread**, then triage the thread as one object. Fetch
enough comments to cover the conversation (paginate if `first:50` truncates).

Gather **all three** comment surfaces:

1. **Review threads** (inline code comments) — GraphQL gives resolution state, the REST
   `databaseId` needed for reactions, timestamps, every reply, and **who** reacted (not only
   `viewerHasReacted`):
   ```bash
   gh api graphql -F owner='{owner}' -F name='{repo}' -F pr=<N> -f query='
     query($owner:String!,$name:String!,$pr:Int!){
       repository(owner:$owner,name:$name){ pullRequest(number:$pr){
         reviewThreads(first:100){ nodes{
           isResolved isOutdated path line
           comments(first:50){ nodes{
             databaseId url createdAt updatedAt author{login} body
             reactionGroups{
               content viewerHasReacted
               users(first:20){ nodes{login} }
             }
           }}
         }}
       }}
     }'
   ```
2. **Review summary bodies** — `gh pr view <N> --json reviews`. These do **not** support
   reactions; a verdict on one is expressed as a reply comment instead. Still read any later
   conversation comments that quote or answer that summary.
3. **PR-level conversation comments** — `gh api repos/$repo/issues/<N>/comments` (each has an
   `id` usable with the issue-comment reactions endpoint). GitHub issue comments are a flat
   timeline: a later comment that quotes, `@`-mentions, or clearly answers an earlier one is part
   of that discussion — treat them as one thread when triaging.

### Triage the thread, not the first comment

Sort each thread's comments by `createdAt`. The **latest substantive human ask** is the claim to
validate, read in the context of everything that preceded it. Concretely:

- A later human reply can retract, refine, contradict, or accept the opening comment. An opening
  "please extract this" followed by "actually, leave it, I misread" is a **not-a-defect**, not an
  agree-and-extract.
- A human reply to a **bot** comment (review bot-review, this command's earlier evidence reply, a
  CI bot that is actually asking something) is live review. Do not ignore it because the parent
  was automated.
- A human **reaction** on any comment in the thread is part of the discussion: 👍 on our evidence
  reply is agreement with the reply; 👎 or 👀 on our 🚀 is "look again"; 👍 on the original ask
  from a second reviewer is a second voice on the same claim. Name who reacted in the triage
  table.
- A thread we already 🚀'd, or that the PR author already replied to, is **not** done if a human
  replied or reacted **after** that last author/bot action. Re-triage the whole discussion.
- `isResolved: true` is skippable only when **no human comment or reaction landed after the
  resolution**. A resolved thread that got a new human reply is live — note the earlier
  resolution in the table and triage anyway. Note skipped (truly quiet) resolved threads in the
  report rather than dropping them silently.
- **Outdated threads still count**: the concern may survive the code that moved. Triage them
  against the current code. `isOutdated` means the anchor moved, not that the discussion is void.
- **Idempotency**: `viewerHasReacted: true` for a given content means this run (or a previous one)
  already posted that reaction — never react twice. A comment already carrying our 🚀 is done
  **only if** no later human reply or reaction exists on that thread; otherwise the rocket is
  historical and the new ask is in the queue.
- Pure-automation noise (CI status bots, danger summaries) is not a review comment — ignore it.
  A **CI failure comment** is workstream B input, not a review comment. **review bot-review
  comments are review comments** — include them and every human reply/reaction on them.

The user naming a thread explicitly forces it into the queue even when quiet.

## Step 3: Collect workstream B — checks, without waiting for the full run

```bash
gh pr checks <N>        # TSV: name<TAB>pass|fail|pending — exits non-zero while pending; expected
```

- **Failed checks** enter the fix queue immediately.
- **Pending checks do not block the loop.** Fix what is already actionable (failed checks, agreed
  comments) and re-read `gh pr checks` between units of work. New failures join the queue **as
  they appear** — a check that fails at minute 3 gets diagnosed while its siblings still run.
  Only when the queue is empty and checks are still pending does polling become the foreground
  activity — use the existing script with a short budget per wait, never one blocking 30-minute
  call:
  ```bash
  POLL_ATTEMPTS=4 POLL_SLEEP=45 scripts/poll-ci-pr-check.sh <N>   # exit 2 = still pending, re-check queue
  ```

**Diagnosing a failed check.** For the CI check, follow the `trace-ci-build` skill
(`.agents/skills/trace-ci-build/SKILL.md`) and read `ci-build` for known failure
patterns before interpreting anything. Classify each failure:

| Class | Action |
|---|---|
| **Change-caused** (this PR broke it) | Fix queue — treat like an agreed review comment |
| **CI standards / CI standards** | Fix queue; use the -standards MCP (`get_results` / `describe_rule`) to see the exact rule |
| **Flaky / infra / known timeout** (e.g. `test:e2e`, rustup ETXTBSY — check `docs/<area>/kb/` and the skill's catalog) | Report with evidence. When it blocks a green run, **halt ⛔** naming the check and the retrigger — never retrigger, cancel, or start a flakiness build unprompted |

Reproduce a change-caused failure locally before fixing (`uv run pytest -q` / `type-check` in the
affected package) — fixing from log text alone is guessing. In a fresh worktree remember
a targeted package build first (`uv run mypy` — missing dist/protogen artifacts
masquerade as code bugs).

## Step 4: Triage **threads** — one verdict per discussion

Read the referenced code and evaluate each **thread** on its merits — the latest substantive human
ask, in the context of the rest of the discussion, including human replies to bots and human
reactions on any comment. **Challenge, don't defer**: a reviewer being the author of the opening
comment does not make it correct, a later 👍 from a second reviewer does not make it mandatory,
and the developer being the PR author does not make the code correct. Verdicts:

| Verdict | Criteria | Action |
|---|---|---|
| **Agree** | The comment identifies a real defect, risk, or clear improvement in scope for this PR | 👍 now; fix in Step 5 |
| **Disagree** | The comment is factually wrong, or the change would make things worse / violates a repo boundary | Post a reply carrying the evidence. **No reaction**, and report it in the summary |
| **Question** | The comment asks for information, not a change | Reply with the answer; no reaction, no fix |
| **Out of scope** | Valid, but belongs to another PR/stack layer or a follow-up | Reply saying where it belongs (name the layer or offer `/tech-backlog`); no 👍 — that would promise a fix here |

Post the 👍 reactions as soon as triage lands (this is the "I've seen it, fix coming" signal):

```bash
gh api -X POST repos/$repo/pulls/comments/<databaseId>/reactions -f content='+1'   # review comment
gh api -X POST repos/$repo/issues/comments/<id>/reactions       -f content='+1'   # PR-level comment
```

**Disagreements are posted directly as soon as the verdict is reached, and then reported.** The
reply argues with a teammate in public under the user's GitHub identity, so every one must appear
in the report, quoted or linked — silence about a disagreement is the failure mode, not the
disagreement. Post the reply, and **only** the reply:

```bash
# the drafted reply goes into a scratch file — drafted text and anything quoted from the
# reviewer's comment never gets interpolated inline into shell source
{ printf "🤖 **%s's agent:**\n\n" "$(gh api user -q .login)"; cat tmp/reply-text.md; } > tmp/reply.md
gh api -X POST "repos/$repo/pulls/<N>/comments/<databaseId>/replies" -F body=@tmp/reply.md   # into the thread
```

Every reply and comment this command posts carries that agent prefix — never a control token such
as `#skipreview`, which is posted bare (**Comments posted on the user's behalf** in
`.agents/skills/pr/SKILL.md`).

A disagreement reply states what was checked and how, so the reviewer can verify or push back:
name the version, file:line or command that settles it, and say plainly what is not being changed.
A claim contradicted by a passing test should say which test and what it asserts.

(For a PR-level comment, reply with `gh pr comment <N> --body-file tmp/reply.md` quoting the
comment, and react on the issue-comment endpoint.)

Present the full triage table (thread → latest human ask → verdict → planned action, plus any
human replies/reactions that changed the reading) before moving to fixes.

## Step 5: The fix loop — fix, push, re-check, repeat

Process the queue (agreed comments + change-caused/standards check failures) as one loop:

1. **Fix** the current batch:
   - Fixes only — no drive-by refactors, no scope creep beyond what the comments/failures ask.
   - A comment or failure about behaviour gets a test that pins the fix
     (see `docs/architecture.md`).
   - `uv run ruff check src tests` (changed files only) and the affected packages' `type-check` / tests must
     pass locally.
   - If a fix turns out to be wrong or infeasible mid-implementation, downgrade the verdict:
     reply on the thread explaining what was found (the earlier 👍 must not be left dangling).
2. **Commit and push** per `/update-pr` discipline: only files relevant to the fixes, on the
   current branch, message referencing what was addressed. Never `--no-verify`, never amend.
   Plain `git push` — the only force-push in this command is the one Step 1's rebase already did.
   Batch sensibly: one push per round of fixes, not one per comment — every push restarts CI.
3. **Mark the addressed comments** — for each comment whose fix is now on the remote:
   ```bash
   gh api -X POST repos/$repo/pulls/comments/<databaseId>/reactions -f content='rocket'
   ```
   - Optionally (and when the fix is non-obvious, do) reply on the thread with the commit SHA:
     `Fixed in <short-sha>` (behind the agent prefix, like every reply).
   - **Never resolve human review threads.** Under the standing owner permission, a PR owner may
     resolve a fixed Review bot thread after the fix is pushed, verified, replied to and marked 🚀.
     Do not resolve an unfixed or newly questioned thread merely to clear the gate.
   - 🚀 goes only on comments whose fix is actually pushed and verified — a partially-addressed
     comment gets a reply describing what remains, not a rocket.
4. **Re-check** — the push restarted CI. Return to Step 3's poll-and-queue rhythm: fix new
   failures as they appear, and exit the loop only when every check has completed **green** and
   every comment has its verdict acted on. A check classified flaky or infra still leaves the head
   red. It is not an exit: **halt ⛔** naming the check and the retrigger it needs (Step 3),
   never report done past it.

**Convergence guard**: if the same check fails on a **third** consecutive push, stop the loop and
**halt ⛔** — repeated red on the same target means the diagnosis is wrong or the failure is
environmental, and more blind pushes only burn CI. Likewise halt if a fix for one failure keeps
causing another.

## Step 6: Exit condition — CI finished on the head SHA

This command is done only when CI has finished **on the current head SHA** and the bots have had their
say on it. Until then the loop keeps going, and this command's turn stays open.

**6a. Wait for the checks to register before you wait for them to finish.** Right after a push the
rollup has not picked up the new run yet, so "zero pending" is true before CI has even started. Pin
the SHA and wait for its check runs to exist:

```bash
repo=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
BRANCH=$(git branch --show-current)
SHA=$(git rev-parse HEAD)
[ "$SHA" = "$(git rev-parse "origin/$BRANCH")" ] || { echo "local HEAD not pushed" >&2; exit 1; }
gh api "repos/$repo/commits/$SHA/check-runs" \
  --jq '.check_runs[] | select(.name | test("CI|review bot";"i")) | {name,status,conclusion}'
```

Poll that until **CI** and **review bot-review** both exist on `$SHA` and have left
`queued`/`in_progress`, with Step 3's short budgets between units of work. When the fix queue is
empty and only waiting remains, run the poll in the background if the harness would time out a
foreground call, **and keep this command's turn open on it**. A running poll is not a reason to end
the turn. Silence never means "probably fine".

**6b. Every push restarts 6a.** A fix pushed in the loop gets a new `$SHA`. Re-pin it and wait
again. A result from the previous SHA says nothing about this one.

**6c. Final sweep once CI is terminal.** review bot-review posts its inline comments when it
completes, which can be after the last fix round's triage. Once both checks are terminal on `$SHA`,
run Step 2 (collect every thread) **once more**. Anything new goes back into the loop. It is
done when a sweep finds nothing new on a terminal, green `$SHA`.

## Step 7: Readiness check — before requesting another review

After Step 6's final sweep, and immediately before dispatching an exact-head review, run:

```bash
uv run pytest -q && uv run mypy
```

Require exit 0 on the current ready PR and the pushed head. This checks every commit's package-doc
routing (including hand edits after a wrap), local doc edits, remaining WIP, required full-suite
receipts, exact-head CI completion and review-thread acknowledgements. Quiet resolved threads pass;
later non-owner activity requires a newer owner reply or 🚀 even on a resolved thread. GitHub exposes
`resolvedBy` but no `resolvedAt`, so the check conservatively treats comments, edits and reactions
after the opening comment as potentially post-resolution.
An unresolved thread also passes when the PR owner's latest reply declares a fix in a commit from
this PR and the owner has added the 🚀 reaction. Use `Fixed in <commit SHA>` so the gate can bind
the attestation to this PR; later non-owner activity requires a newer acknowledgement, and a later
reviewer reply requires the latest reply to be the owner's fix declaration. This is the owner's attestation,
not automatic proof that the defect is fixed. The owner may resolve fixed Review bot threads under
the standing permission after replying and marking 🚀; human threads remain with their reviewer.
Passing this pre-review gate does not relax the workflow's separate merge-time thread rules.
If the gate fails, keep the review request unsent, fix the named failures and rerun;
any later commit or push invalidates the result. Route doc corrections through the wrap procedure
and declare the wrap with `docs(<scope>): wrap ...` or a `Docs-Wrap: /wrap-context-docs` trailer.

The runner commands below create local HEAD-keyed evidence only after a clean, unchanged tree and
the **full** suite exits 0. Use the task's load gate before each suite when its brief requires it.
Run the suites required by the gate after the final commit, then rerun the check:

```bash
uv run pytest -q
uv run pytest -q
```

These run `surmap test` and `surmap test:e2e`; filtered runs and old-head
receipts cannot substitute. A failed rerun invalidates previous evidence. Do not write receipts by
hand. Visual receipts are required only for the registered Product host's actual story globs.
Other hosts report unverified visual coverage without blocking the review request.

## Report

- The PR, and whether Step 1 rebased (old → new SHA) or verified-current.
- The triage table: every **thread**, its latest substantive human ask, human replies/reactions
  that affected the reading, its verdict, and the reaction/reply posted.
- Every check: final state, classification (change-caused / standards / flaky / infra), and for
  fixed ones the failure → fix mapping.
- Per fix: files touched, test added/updated, and the commit SHA.
- Loop rounds used (pushes) and lint / type-check / test state — flag anything not green
  explicitly.
- **Every disagreement reply posted**, with its thread link and the substance of what was argued —
  these went out under the user's identity without an approval step, so the report is where the
  user learns they exist. Never fold one into a one-line "addressed the comments".
- Items left for the user: out-of-scope routing, questions answered.
- In the skill's summary these go under **Done**; the disagreement and out-of-scope replies under
  **Decided without review**.

## Rules

- **Triage whole threads** — later human activity reopens a resolved, outdated, 🚀'd or
  author-replied thread.
- **Reactions are the protocol**: 👍 before fixing, 🚀 once pushed; never double-react, never 👎,
  never 👍 without fixing or walking it back, never 🚀 an unpushed or partial fix, never resolve a
  human thread; only fixed Review bot threads may be owner-resolved under the standing permission.
- **Never wait for the full check run to start fixing**; never one blocking 30-minute poll.
- **Never retrigger, cancel, or flakiness-build a check unprompted.**
- **Done only on a terminal, green head SHA** after the final sweep (Step 6).
- Stack-wide counterpart: `/fix-pr-stack`.
