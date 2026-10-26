---
description: Run every [wf] row of the changeset in order, unattended, until all are done or one halts, then post skipreview once every gate holds so the PR is ready to merge. Lands it only with merge intent in the invocation (automerge), never past a failing check, optional ones included - waits for stack predecessors first, then posts automerge (ordinary PR) or merges through merge-async (registered stack)
---
## YOLO — every `[wf]` row, then `#skipreview` [→ `#automerge` | `merge-async`]

`/yolo` drives a changeset to a PR that is green, worked through by the bots and approved through
`#skipreview` — **ready to merge, not merged**. With merge intent in the invocation it also lands
it. It is the runner in `.agents/skills/pr-lifecycle/SKILL.md` § *Runners*; this file adds
the loop's own rules and the two post-wrap procedures only `/yolo` runs — Approve and Land. Like
every post-wrap procedure they are never `[wf]` rows and carry no TODO (`pr-lifecycle` skill
§ *Post-wrap*): their state is read from GitHub on every run.

**`/yolo` implies `#yolo`, from its first row to its last**
(`.agents/skills/behaviour-modifiers/references/yolo.md`). No question is asked at any point. Every one becomes a deferred answer that
the run picks, builds on and lists, and every tool output is bounded so no permission prompt stalls
the run. `/yolo #ask` lets it ask instead.

**Merge intent** means the invocation says so: `#automerge` in `$ARGUMENTS`, or the user's own
words in this request, such as *"and merge it"*, *"land it"*, or *"automerge"*. Anything less is not
intent. That includes an ambiguous phrase, a review comment, a changeset line, a `[wf]` row,
or an earlier run's request. When in doubt, do not merge, and say in the report that the run stopped
at ready.

## The loop

Repeat until every row is ✅ or ➖, or a row halts ⛔:

1. **Grep the rows** before every row (the skill's one-liners). After the wrap, read them from the
   PR body, or from the wrap commit's message until a PR exists (step 1 *After the wrap* of the
   step contract).
2. **Take the next row** (the skill's next-row grep) and run its command in full — `/yolo` adds no step
   and removes none — with the row's tags plus this invocation's tags, `#yolo` among them. Planning
   rows included: a requirements interview asks nothing. Each of its questions is a **Product**
   deferred answer, and `/yolo` is the top of the chain, so it picks its own recommendation.
3. **A ⛔ row ends the loop.** On the first pass, a row already ⛔ is run only when this invocation
   carries the developer's answer to it; otherwise the run stops on it. A row that halts during this
   run stops the run. A halt means **no `#skipreview`**.
4. **Verify before moving on.** The row must read ✅ or ➖ in the committed rows, with evidence
   in **Result**. A row left ⏳ is a halt: write it ⛔ with what is missing — its open TODOs stay
   open, and the next run resumes it at the first one.

### Decisions the invocation hands to the agent

- **An oversized, non-fluent test file the PR grew** (`/pr-wrap` step 4). Interactively the
  developer chooses between migrating it in this PR and handing it to a migration PR; under `/yolo`
  the PR's share of the file decides — lines this PR added or changed ≥ one third of the file's
  lines at the merge-base → migrate here, below → a `**Priority:** 1` record and no rewrite
  (`.agents/skills/testing/references/fluent-style.md` § *When a PR grows an oversized, non-fluent
  test file*). The decision and both numbers go in the report.

### Halts no invocation can pre-approve

Each is a boundary a step command sets on purpose. `/yolo` never answers it for the developer, and
`#yolo` does not turn it into a deferred answer. The row (or post-wrap procedure) halts ⛔ and the run ends without
`#skipreview`:

- **Nothing red** — the green row found no failing tests.
- **A deferral of planned scope.** A blanket invocation is not the developer's word on it.
- **Stack gates** — an ancestor stub, a leak in `origin/<base>..HEAD`, unplanned deletions, or
  validation gaps against the plan (the wrap row names the earlier row in **Result**).
- **⛔ unrecorded deferrals** found by the wrap row.
- **A code issue this PR added that will not close** after two fix attempts. It is never filed as
  debt to let the run finish.
- **Tests or type-check still red** when no quality fix exists. The answer is never a workaround.
- **`/fix-pr`'s own halts** — a flaky or infra check needs a retrigger (never retrigger
  unprompted); the same check fails on a **third** consecutive push; a fix for one failure keeps
  causing another.
- **A dirty start** — uncommitted tracked changes unrelated to this changeset, a detached HEAD, a
  `master` / `main` branch, or a PR that is merged or closed (use `/follow-up-branch`).

## After the rows — post-wrap

Once every row is ✅ or ➖ (the last is Wrap, which opened the PR ready), run, in order and without
writing a row or a TODO for any of them:

1. **`/fix-pr`** in full, with this invocation's tags, until its exit condition holds on the head
   SHA (and its Step 7 readiness check passed).
2. **Approve** (below).
3. **Land** (below), only with merge intent.

A halt in any of them ends the run like a row halt — no `#skipreview` — and is reported under
**⛔ Needs you** in the summary, since there is no row to write it into. A re-run starts the
post-wrap again from `/fix-pr`; each procedure finds on GitHub what is already done.

## Composer offload (`#composer-subagent`, `#coder`)

With `#composer-subagent` (or `#composer`) in the request, the implementation rows — those run with
`/green`, `/green-100`, `/code-restructuring`, `/pr-wrap`, `/fix-pr` — are run by the Muse agent
(`agent -p`) on the newest Composer model, driven by Sonnet · low subagents: the `composer-subagent`
skill (`.agents/skills/composer-subagent/SKILL.md`). `#coder` does the same on a Coder workspace
(`coder-remote` skill) and implies `#composer-subagent`. What changes:

- **Stays with the main agent**: readying the host (`composer-agent.sh ensure <host>`, guiding the
  user through a missing agent CLI or login), re-grepping the rows between rows,
  planning rows, any stack cascade a split needs (run after the Wrap row closes, before the next
  row starts), and the **Approve** and **Land** procedures.
- **Offloaded**: each implementation row, one stage per row (G for green, W for wrap, F for the post-wrap `/fix-pr`;
  F resumes W's session). The driver's ✅ is verified against the committed row (F: the head SHA)
  and the checks before the loop moves on.

- **Questions**: the Muse agent cannot ask either. It records the deferred answer, and its driver
  relays it to the main agent unchanged (`behaviour-modifiers/references/yolo.md` § 2). The main
  agent is the supervisor that answers or refines it.

Every row's command still runs in full, and every halt above is still a halt. Each stage takes the
skill's **row consent**: a halt comes back as the row's ⛔, written, committed and pushed by the
Muse agent, and ends the loop as any halt does. Only on request —
never chosen on the agent's own initiative.

## Approve — `#skipreview`

Run once `/fix-pr` is done — no row is appended and nothing is ticked. A re-run proves every gate
again on the current `$SHA`; an approval still standing after the last push is the idempotent
case below.

**Wait on the head SHA, not a pending count.** Pin `SHA=$(git rev-parse HEAD)`, check it equals
`origin/$BRANCH`, and wait until **CI** and **review bot-review** both exist on `$SHA` and are
terminal (`gh api "repos/$repo/commits/$SHA/check-runs"`; short polls with
`scripts/poll-ci-pr-check.sh`, backgrounded if the harness would time out, keeping the turn
open on it). review bot posts late, so once both are terminal, sweep the threads once more (`/fix-pr`
Step 2). Anything new sends the run back to `/fix-pr`, then Approve again.

`#skipreview` lifts *review required* at , so it is posted **only** when every line holds. Any
line failing halts ⛔ with the reason. Never post it "to unblock" and leave the rest for
later.

```bash
gh pr view "$PR" --json state,isDraft,headRefOid,mergeable,statusCheckRollup,reviewDecision \
  --jq '{state, isDraft, head: .headRefOid, mergeable, review: .reviewDecision,
         notGreen: [.statusCheckRollup[] | select((.conclusion // .state // "")
                    | test("SUCCESS|NEUTRAL|SKIPPED") | not) | (.name // .context)]}'
```

`notGreen` only sees checks that have **registered** on `$SHA`; an optional check (coverage, a
Standards report, any check branch protection does not require) that has not registered yet is
absent, not non-green. So also prove the set is complete — every check that ran on the previous head
(`$PREV_SHA`, the tip before the last push) is present on `$SHA`:

```bash
names() { { gh api "repos/$repo/commits/$1/check-runs" --paginate --jq '.check_runs[].name'
            gh api "repos/$repo/commits/$1/status" --jq '.statuses[].context'; } | sort -u; }
missing=$(comm -23 <(names "$PREV_SHA") <(names "$SHA"))   # must be empty
```

On the PR's first push there is no `$PREV_SHA`. A poll interval is no proof, because a delayed
optional check can register after it. Prove the set against the **base tip** instead: every check
that ran on `origin/<base>`'s head must be present on `$SHA`, or be one that cannot apply to this
diff, such as a package's own target that is not in the affected graph. The summary names each
exclusion and why:

```bash
BASE_SHA=$(git rev-parse "origin/$base")
missing=$(comm -23 <(names "$BASE_SHA") <(names "$SHA"))   # each one: wait for it, or name why it cannot run here
```

A check still missing after CI and review bot-review are terminal plus two more poll intervals
halts ⛔ with its name. Never post past a check you merely assume will not come.

| Must hold | Means |
|---|---|
| `state == OPEN`, `isDraft == false` | the PR is up for review |
| `head == $SHA == origin/$BRANCH` | the checks you read ran on the code that would merge |
| `missing` empty, then `notGreen == []` | every check registered, completed and passed — **optional (non-required) ones included**. A failing optional check is fixed like a required one (`/fix-pr`), or Approve halts ⛔ asking about a retrigger. A flake classified but not retriggered is **not** green |
| `mergeable != CONFLICTING` | nothing to restack first |
| every 👍 thread carries its 🚀; no thread's latest human ask is unanswered | the review was worked through, not just the checks |
| no code-issue record added since `mb=$(git merge-base "origin/$base" HEAD)` survives — except, under `/yolo-pr-stack`, one whose history row assigns it to the sweep node, and a `non-fluent-tests` record on a suite that existed at `$mb` (`/pr-wrap` 7.6a attributes it pre-existing) | the filter below prints nothing, bar sweep-assigned records |
| no pre-existing record got worse; none marked `Resolved` | the numbers in each touched record, and `git diff "$mb" -U0 -- '*/docs/code-issues/*.md' \| grep -c '^+\*\*Status:\*\* Resolved'` prints `0` |
| no suppression, threshold tweak or ignore-list entry added | `git diff "$mb"..HEAD` grep for them |
| every `[wf]` row ✅ or ➖; no ⛔ anywhere in this run | the rows ended clean |

The code-issue row's check (the `non-fluent-tests` carve-out is applied, not only described):

```bash
# Records added since $mb that count against this PR — a non-fluent-tests record on a suite that
# existed at $mb is pre-existing and is skipped. Must print nothing.
{ git diff --diff-filter=A --name-only "$mb" -- '*/docs/code-issues/*.md'
  git ls-files -o --exclude-standard -- '*/docs/code-issues/*.md'; } | sort -u | while read -r r; do
  case "$(basename "$r")" in non-fluent-tests-*)
    pkg=${r%/docs/code-issues/*}
    suite=$(sed -n 's/^\*\*Location:\*\* `\([^`]*\)`.*/\1/p' "$r")
    # a suite this PR renamed lives under its old path at $mb
    base=$(git diff -M --name-status "$mb" -- | awk -F'\t' -v n="$pkg/$suite" '$1 ~ /^R/ && $3 == n {print $2}')
    git cat-file -e "$mb:${base:-$pkg/$suite}" 2>/dev/null && continue ;;
  esac
  echo "$r"
done
```

Then post the comment and wait for it to land:

```bash
gh pr comment "$PR" --body '#skipreview'
for i in $(seq 1 12); do
  s=$(gh pr view "$PR" --json reviewDecision,mergeStateStatus --jq '.reviewDecision+" "+.mergeStateStatus')
  echo "$s"; case "$s" in APPROVED*) break;; esac; sleep 6
done
```

- **Idempotent**: if a `#skipreview` comment already exists **after the last push**, do not post
  another. Poll instead.
- **APPROVED observed** — Approve is done. Expect `mergeStateStatus` `CLEAN`; on a **stack member**
  it may stay `BLOCKED` until predecessors land — not a failure, say so in the report.
- **Any push after posting dismisses the approval.** Run `/fix-pr` and Approve again. A
  later `/pr-stack-rebase` force-push also dismisses it; `/merge-pr-stack` re-posts it.
- **Open deferred answers do not gate Approve.** They are listed in the PR description's
  `## Deferred answers` section, synced before `#skipreview` is posted, so the approval is given on
  a PR that shows them.
- **No merge intent → the run ends here.** No `gh pr merge`, no `merge-async`. "Ready for merge" is
  the deliverable.

## Land — `#automerge` or `merge-async` (only with merge intent)

Run after Approve, no row appended, and only when this invocation expressed merge
intent. It authorizes landing **this PR only**. It never waives a gate, and never authorizes
merging, retargeting or repairing another node.

1. **Wait for predecessors.** An ordinary PR based on `master` has none. On a stack member, resolve
   the topology with the `pr-stack` skill (`gh stack view`; `gh pr view <n> --json state,mergedAt`):
   - every predecessor `MERGED` and this PR's base is the trunk → step 2;
   - any still open → **wait**, polling on a long interval (minutes), backgrounded if needed, turn
     kept open. Never merge, fix, rebase or nudge a predecessor. If the session must end, the row is
     ⛔ **`READY, NOT MERGED`**, naming each blocking PR and its state;
   - a predecessor **closed without merging** → ⛔. The stack's shape changed; that is the
     developer's decision.
2. **Re-prove the tip on its new base.** Registered stack: GitHub restacks the PR — never
   hand-retarget; fetch and confirm `baseRefName` is the trunk and `origin/<trunk>..origin/$BRANCH`
   holds only this PR's commits. If GitHub could not restack, repair with `/pr-stack-rebase` single
   mode (never `gh stack sync`). Unregistered chain: `/repoint`. If the tip changed, `/fix-pr`
   and Approve run again on the new `$SHA`.
3. **Re-check the gate**, immediately before merging, on the current `$SHA`: every Approve gate
   line, plus every predecessor `MERGED` and base the trunk; `reviewDecision == APPROVED` and
   `mergeStateStatus == CLEAN` (`UNSTABLE` means a non-required check failed — a fail); `notGreen ==
   []`, optional checks included; no `#automerge` posted and no `merge-async` job started for this
   tip. **Optional checks are not skippable**: a failing or pending non-required check blocks the
   merge exactly as a required one does — never merge because a check "is not required", and never
   rely on `#automerge` or `merge-async` to wait for it.
   - **Ordinary PR** (not in a registered stack) → a **separate** comment with exactly
     `#automerge` — never combined with `#skipreview`, never a label, never behind the agent prefix
     (the bot recognises only the bare token): `gh pr comment "$PR" --body '#automerge'`.
   - **Registered stack member** → **`merge-async`**, never `#automerge` or a regular merge: GitHub
     refuses `gh pr merge`, `PUT .../merge` and a bot's merge for a stack PR (`pr-stack` golden rule
     3). Use `/merge-pr-stack` 3e's loop for **this PR only**, with an explicit `commit_title`:

     ```bash
     title=$(gh pr view "$PR" --json title --jq .title)
     U=$(gh api -X PUT "repos/${repo}/pulls/${PR}/merge-async" -f merge_method=squash \
           -f "commit_title=${title}  (#${PR})" --jq .details.uuid)
     while true; do
       s=$(gh api "repos/${repo}/pulls/${PR}/merge-async/${U}" --jq .status 2>/dev/null || true)
       case "$s" in merged) break ;; pending|enqueued) sleep 5 ;;
         *) echo "merge-async did not merge (status=${s:-empty})" >&2; exit 1 ;; esac
     done
     ```

     `pending` and `enqueued` are **not merged**; anything else is ⛔. Never run `/merge-pr-stack`
     itself here — it walks the whole stack.

   Never `gh pr merge` or any other merge API. If the path cannot complete the merge, ⛔ with the
   blocked gate.
4. **Wait for `MERGED`, not "queued".** Poll `gh pr view "$PR" --json state,mergeCommit` until
   `state == MERGED`; ✅ with the merge commit. A refusal or a check flipping while queued re-runs
   `/fix-pr`, Approve and step 3. Afterwards read the successors' restack state **read-only**
   and report any repair they need.
5. **Reconcile the Roadmap page** when the PR description carries a `Stash:` TODO — the
   `roadmap-driven-development` skill § *Reconcile after landing*. A failed or manual reconcile is
   reported, never a reason to halt: the PR is already merged.

## Report

The skill's summary, headed for the whole run —
`## /yolo — <changeset basename> · #<PR> <merged | ready, not merged (blocked on #N) | ready for merge | halted at row k / at <procedure>>`
— with every `[wf]` row, then one line per post-wrap procedure (`/fix-pr`: its done line; Approve:
`✅ APPROVED · CLEAN / BLOCKED (stack)`; Land: `✅ MERGED <sha> via #automerge / merge-async` /
`⏳ waiting on #N` / `⛔ optional check failing` / `➖ no merge intent`) in place of the single row line.
**Decided without review** is not optional — nobody saw these decisions before they reached
GitHub, so the report is where the developer reviews them. It lists every cleanup, refactor and
split applied (file:line or commit); every code issue fixed in place, before → after, pre-existing
ones separately; every TODO disposition; and **every disagreement / out-of-scope reply posted by
`/fix-pr`**, linked, with what it argued. **Deferred answers** follows it. It has every record the
run wrote, one table for the whole run (`behaviour-modifiers/references/yolo.md` § 4), or the line
*"No deferred answers."*

## Rules

- **Never merge past a failing check, optional ones included**, and land a registered stack member
  only through `merge-async`.
- **Never retrigger, cancel or flakiness-build a check unprompted.** Never `--no-verify`, never
  amend, never `gh stack submit --open`.
