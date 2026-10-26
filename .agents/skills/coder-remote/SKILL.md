---
name: coder-remote
description: >-
  Run implementation work on a Coder workspace instead of this machine — `#coder` means remote execution. List and start workspaces, provision a new one (tools, GitHub SSH, repo clone; `references/workspace-setup.md` guides a developer with none through creating it), create worktrees there with `uv sync --group dev` + builds, and own every restart. What runs in a remote worktree is the `composer-subagent` skill's Muse `agent -p` on Composer, driven by Claude Code subagents — `#coder` implies `#composer-subagent`; on the workspace the agent runs in tmux so a dropped connection never stops it. Only implementation is offloaded — `/green` → `/pr-wrap` → `/fix-pr` (the implementation rows `/yolo` runs; in `/yolo-pr-stack`, its `[G]`, `[W]` and `[F]` stages); planning always stays local. Use ONLY when the user asks for it — words like "on coder", "remotely", "on my coder machine", or the `#coder` tag. Never choose it on your own.
---

> **Genericized import.** This workflow was originally written for a specific product and infrastructure. Service, artifact, dashboard and host names below are `example` placeholders — substitute SurMap's equivalents (see `README.md` and `docs/architecture.md`) before acting, and confirm any external system exists before calling it.


# Coder Remote — a Coder workspace as the host for Composer subagents

There is room for several worktrees on a Coder workspace, and this laptop's disk and CPU stay free.
Claude Code stays local and orchestrates. **`#coder` is the host; the executor is the
`composer-subagent` skill** (`.agents/skills/composer-subagent/SKILL.md`), which `#coder` implies —
read it too: it owns the driver brief, the stage prompts, the turn commands and the row consent.
This skill owns the workspace.

```
main agent (local)                                   driver subagent (local)          Coder workspace
──────────────────                                   ───────────────────────          ───────────────
$CR ensure <ws>   start · tools · yarn · gh ──────►                                   ~/Code/this repo             main checkout
$CR worktree <ws> <branch> <name> · warm-up ──────►                                   ~/Code/this repo/.worktrees/<name>
$CA ensure <ws>   Muse agent · login · model ───►
brief (composer-subagent driver-brief.md) ────────►  $CA run --host <ws> ──────────►  tmux cmp-<name>: agent -p (Composer)
                                                                                        └─ pipe-pane ─► ~/.composer-runs/<name>/stream.jsonl
                                                     wait · progress · summary ◄──
◄──── 🔴 transport-lost (name, session) ──────────── stop; never start anything
$CR ensure <ws> → SendMessage "resume" ───────────►  wait → RUN_EXIT=16 → run --resume <sid>
```

## What runs where

| Local — the session's own model (the orchestrator) | Coder — Muse `agent -p` on Composer |
|---|---|
| Everything that decides *what* to build: the interview, the decomposition question, every changeset/PRD, the red commits (failing tests), the 6e guardrail verification, the sweep node's plan, the TODO gate | `/green` (or `/code-restructuring`) |
| Warm-up, worktrees, restarts, logins, every judgement about whether a stage is done (the drivers) | `/pr-wrap` |
| Reporting every ⛔ halt — anything that needs the developer comes back as a halted row, or a ⛔ in the report for the row-less `/fix-pr` | `/fix-pr` and its rounds |

**When it applies.** Only when the user asks for it, in words or with `#coder`. It never replaces
local work on the agent's own initiative, and a `#coder` request never lapses into running the stage
locally because the remote is hard — stop and say why instead.

**Why tmux, only here.** A remote turn must survive a dropped `coder ssh`, a closed laptop and a local
context reset, so the agent runs in a detached tmux session `cmp-<name>` on the workspace and tmux
writes the pane's output to the stream. Only a **workspace stop** kills a turn, because tmux dies with
the machine; the next `wait` reports **`RUN_EXIT=16`** and the session is continued with `--resume`.
The Muse chat itself lives on the workspace disk and survives the stop. Watch a turn live with
`coder ssh <ws> -- tmux attach -r -t cmp-<name>` (read-only).

## The script

Workspace steps go through `.agents/skills/coder-remote/scripts/coder-remote.sh` (call it `$CR`);
turns go through `composer-subagent`'s `composer-agent.sh` (`$CA`) with the workspace name as its
host. Use absolute paths, since a subagent's shell does not keep a `cd`. Never hand-roll
`coder ssh …` lines. The shared transport (`scripts/coder-transport.sh`) handles what bit during the
build-out:

- The remote script travels base64-encoded in argv, because `coder ssh` never closes a piped stdin
  (so `bash -s` hangs).
- `coder ssh` turns LF into CRLF, and reports every remote failure as its own exit 1. The transport
  strips the CRs and recovers the real exit status.
- `coder ssh` starts a stopped workspace by itself. The transport passes `--disable-autostart`, so
  only `$CR ensure` starts one.
- A login shell rewrites the exit status through `~/.bash_logout`. The transport `exec`s a plain bash
  under the login environment instead.
- Short calls retry through a network blip while the workspace is up, so a `13` means the workspace
  really is down.

| Command | Who | What |
|---|---|---|
| `list` | main | workspaces with template and status |
| `setup <ws>` | main | provision a new workspace's internals: tools (incl. tmux, jq, flock), GitHub SSH, repo clone, uv run pytest -q, git identity, `gh` login check — idempotent |
| `ensure <ws>` | main | start if stopped/failed; check the repo and tools; repair the uv run pytest -q; check the `gh` login; print `REPO`, `READY=yes` |
| `worktree <ws> <branch> <name> [--from <base>]` | main | check out (or fast-forward) a pushed `<branch>` in `~/Code/this repo/.worktrees/<name>`; with `--from`, cut a **new** branch from `origin/<base>` with no upstream (a bare `git push` can then never land on `<base>`); print `WORKTREE`, `HEAD` |
| `exec <ws> <dir> <cmd…>` | main | a shell command in a remote dir (the warm-up) |
| `remove-worktree <ws> <dir>` | main | remove it once no process runs in it (14 — an agent turn, the user's shell, anything), nothing tracked is dirty, and nothing is unpushed |

Exit codes the caller must act on: **11** `gh` not logged in · **12** workspace or provisioning
failure · **13** workspace not reachable (it stopped) · **15** branch checked out in another remote
worktree · **14** a process still runs in the worktree (`remove-worktree`) · **17** workspace not provisioned — run `setup` · **18** GitHub rejects the workspace's SSH
key — the user must add it. `$CA ensure <ws>` adds **10** (Muse not logged in on the workspace).

Paths default to the remote home: the main checkout is `~/Code/this repo` (`setup` clones it there
from the local checkout's `origin`), worktrees go under `~/Code/this repo/.worktrees/` (gitignored), and
streams under `~/.composer-runs/<name>/`. `CODER_REMOTE_REPO` and `CODER_REMOTE_WORKTREES` override
the first two for a workspace laid out differently.

## Main agent — warm up, brief, restart

### 1. Pick and warm the workspace

Every developer has their own workspaces, or none yet, so never assume a workspace name.

1. `$CR list`. Use the workspace the user named. Otherwise use their `ec2-monorepo` workspace
   (that template carries the monorepo toolchain), whatever its status. With more than one
   candidate, ask — starting a workspace costs money.
   **None, or only other templates** → follow
   [references/workspace-setup.md](references/workspace-setup.md): local prerequisites, how the user
   creates an `ec2-monorepo` workspace and which parameters to pick, then `setup`. A brand-new
   workspace always goes through `$CR setup <ws>` before anything else.
2. `$CR ensure <ws>`. It starts the workspace when it is stopped, which takes about two minutes.
   - **Exit 17, not provisioned** (no repo checkout, missing tools) → `$CR setup <ws>`, which clones
     the repo and installs what is missing; then `ensure` again. `setup` can also stop with
     **18**: GitHub rejects the workspace's SSH key. Relay the step from
     [references/workspace-setup.md](references/workspace-setup.md) § 4.
   - **Exit 11, `gh` not logged in** → stop and tell the user: *"`gh` on `<ws>` is not logged in.
     Please run `coder ssh <ws>`, then `gh auth login`, and tell me when it's done."* Use
     `AskUserQuestion` when it's available. Re-run `ensure` after the answer. Never log in for them,
     and never copy credentials onto the workspace.
   - **Exit 12** → report the error. Do not try another workspace without asking.
3. `$CA ensure <ws>`. It installs the Muse agent on the workspace when it is missing, checks its
   login and prints `COMPOSER_MODEL`.
   - **Exit 10, Muse not logged in** → the same as 11, with `agent login`
     (`NO_OPEN_BROWSER=1 agent login` prints a URL to open locally).
4. A long run outlives the workspace's autostop (8 h TTL). Push the deadline out with
   `coder schedule extend <ws> 8h`, and again whenever a long pipeline is still running.

### 2. A worktree per unit of work

```bash
$CR worktree <ws> <branch> <name>        # e.g. name = yolo-<slug>-n<k>
$CR exec <ws> <WORKTREE> './scripts/setup-worktree.sh && uv sync --group dev && uv run mypy'   # each package in scope; never a full-repo build
```

`scripts/setup-worktree.sh` clones every workspace `node_modules` from the main checkout
(`~/Code/this repo`), so `uv sync --group dev` applies only the differences. If the main checkout was never
installed, nothing is cloned and `uv sync --group dev` does the full install. A path it cannot copy is
reported and left for `uv sync --group dev`; the script still exits 0. The workspace disk is ext4, which
has no reflink, but the repo's Yarn `nmMode: hardlinks-global` makes every `node_modules` file a
hardlink into `~/.yarn/berry/store`, and the script hardlinks from a source installed that way (on
coderplex, also ext4: 70 s clone + 142 s install and 2.1 GB, against 458 s and 12.7 GB for a
classic install). A branch
from before the script existed has no `scripts/setup-worktree.sh`; warm it up with
`uv sync --group dev && uv run mypy`.

Run the warm-up with `run_in_background: true`, since an install plus builds can exceed the
10-minute Bash cap: `uv sync --group dev` alone took about 4 minutes in a fresh worktree. Without it the
Muse agent cannot commit, because the husky hooks run `uv run pytest -q`. A warm-up failure is the main
agent's to diagnose, never the driver's. **Exit 15** (branch pinned) means someone is already working
on that branch remotely: stop that unit and do not force it. The branch must be **pushed** before
`worktree`, because the workspace sees only `origin`.

### 3. Brief the driver

As `composer-subagent` § *Brief the driver*, with `<host>` = `<ws>` and `<WORKTREE>` = the path
`worktree` printed.

### 4. Own every restart

A driver that gets exit **13** stops and reports `🔴 transport-lost` with its `<name>` and
`SESSION_ID`. The workspace has stopped: autostop, a spot reclaim, a failed build. Then:

1. `$CR ensure <ws>` restarts it, then `$CA ensure <ws>`. Handle 10/11 as above.
2. `$CR worktree <ws> <branch> <name>` — the worktree survives a stop, and this re-verifies it.
   Re-run the warm-up only if `node_modules` or the build output is gone.
3. `SendMessage` the **same** driver: *"Workspace `<ws>` is back. Run `wait` for `<name>`, then
   resume per the brief."* Its `wait` returns `RUN_EXIT=16`, and the brief tells it how to resume.
   Never spawn a new driver for an interruption. Load the tool with
   `ToolSearch("select:SendMessage")` if it is not loaded.

Several drivers report the same outage: restart once, then message each of them. A dropped
connection while the workspace stays up is **not** a restart. The agent keeps running in tmux, and
the driver's next `wait` simply picks it up.

After a context reset, re-derive each unit from `$CA summary <ws> <name>` and `tmux ls` on the
workspace. Only the `cmp-<name>` sessions of this run's names are yours; every other session in that
list is the user's or another agent's — read it, never touch it. Never re-run a turn whose session is
still running.

### 5. Finish

When a unit is done, run `$CR remove-worktree <ws> <dir>`. It refuses when anything tracked is dirty
or unpushed, so push first, or keep the worktree and say where it is. Never delete the branch. The
stream under `~/.composer-runs/<name>/` stays as the record. When other work is queued, leave the
workspace running. Otherwise tell the user it is still running, and stop it with
`coder stop <ws> --yes` only when they ask. A stop ends **every** session on the workspace — the
user's own SSH shells and tmux sessions, and other agents' turns, not only this run's. So before
stopping, list what else is running (`$CR exec <ws> ~ 'tmux ls 2>/dev/null; who'`), name anything
that is not this run's `cmp-<name>` sessions to the user, and stop only on their answer.

## Rules

- **Opt-in only**: the user's words or `#coder`.
- **`#coder` implies `#composer-subagent`**: Composer for every remote turn, `COMPOSER_MODEL` from
  `$CA ensure <ws>`, never a hard-coded version.
- **The main agent owns the workspace**: start, restart, extend, provisioning, logins, worktrees.
  A driver never runs anything in `coder-remote.sh`, `coder start` or `coder stop`, and never works
  around a `13`.
- **Logins are the user's**: on exit 10 or 11, stop and ask them to SSH in and log in.
- **Kill only what you started.** A turn ends through `composer-agent.sh cancel <ws> <name>`, which
  kills only its own tmux session `cmp-<name>`. Never `tmux kill-server`, never another tmux session
  or terminal on the workspace or on this machine — the user's, another agent's or another run's —
  and never `pkill`/`killall` by pattern. The two workspace-wide actions that end other sessions too
  need the user: `coder stop` (only when they ask, after naming what else runs there), and removing
  a worktree anything still runs in (`remove-worktree` refuses with 14 and lists the processes —
  never work around it, never kill them). The one listed process a run may end itself is the
  `restructure serve` its own restructure commands started in that worktree (with its language
  servers): `restructure daemon stop` from inside the worktree stops it cleanly; otherwise it exits
  after 15 idle minutes.
- Never `--no-verify`, never amend, never force-push.

## Related

`composer-subagent` skill (the executor, the driver brief, the stage prompts) · `/yolo-pr-stack`
§ *Composer mode* · `/yolo` § *Composer offload* · `pr-stack` skill (worktree and branch rules)
