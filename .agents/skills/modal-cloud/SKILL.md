---
name: modal-cloud
description: >-
  Run SurMap work on Modal (modal.com) serverless containers and GPUs:
  log in and pick the right workspace or profile, smoke-test the account,
  run or deploy an app without making Modal a SurMap dependency, keep cost
  bounded, and stop what you started. Use when asked to run something "on
  Modal", test a container or GPU there, switch Modal workspace/profile,
  or check what a Modal run cost. Generic SDK and API questions go to
  Modal's own `modal` skill.
---

# Modal for SurMap

Modal runs Python functions in cloud containers. A Modal run is
outward-facing and billed to a workspace. Treat it like a push: the
user's request covers the run they asked for, not more.

This skill is the SurMap operating procedure. For the SDK itself
(`modal.Image`, `@app.function`, GPUs, volumes, secrets, sandboxes),
load Modal's official `modal` skill (step 1).

Stop at the first failed step. Report the command and its output.

## 0. CLI without a dependency

`modal` is not in `pyproject.toml`. Do not add it there for a one-off
run. A PR that makes Modal part of SurMap adds it to a dependency group
and states why in the PR body.

Run the CLI as a uv tool:

```bash
uvx modal --version
```

`uvx modal run app.py` imports `app.py` in the tool environment, so the
app can import `modal` but not `surmap`. To ship SurMap code into the
container, add it to the image (`Image.add_local_python_source("surmap")`
from a uv env that has both). Check the official skill for the current
API before writing it.

Run the CLI without a TTY (the Bash tool already does), so logs are
plain text instead of spinner redraws.

**Pass:** a version prints.

## 1. Official Modal skill

```bash
uvx modal skills show | head -20     # preview, needs no install
uvx modal skills install --global --claude -y
```

`--global --claude` puts it under `~/.claude/skills/modal/` with its
downloaded docs. Do not install it into the repo; the docs are large
and change with every SDK release. If `metadata.version` in that skill
differs from `uvx modal --version`, run
`uvx modal skills update --global --claude`.

Installing writes to the user's home directory. Ask once before doing it.

## 2. Credentials and workspace

```bash
uvx modal profile list
```

A profile holds one token for one workspace, stored in `~/.modal.toml`.
Never print `token_secret`, and never commit or paste that file.

No profile, or the user wants another workspace: run the browser login
in the background so the agent can hand over the URL.

```bash
uvx modal token new --no-verify --profile <name>   # run_in_background
```

Read its first output lines and give the user the
`https://modal.com/token-flow/...` URL. The user has to:

1. sign in as **their own** user;
2. pick the workspace the token is for. A team or peer workspace shows
   up only after its owner has invited the user;
3. approve. The command then exits on its own.

The completion line names the workspace:
`Token is connected to the <workspace> workspace.` Compare it with the
workspace the user asked for. If they differ, stop and ask. Never guess
that a personal workspace is fine for team work, or the other way round.

Switch between workspaces with `uvx modal profile activate <name>`, or
pass `--profile <name>` to a single command.

**Pass:** `uvx modal profile current` names the workspace the user
intends to bill.

## 3. Smoke test

```bash
uvx modal run .agents/skills/modal-cloud/scripts/hello_modal.py
```

It builds a `debian_slim` Python 3.12 image and runs one function with
0.25 CPU and 256 MB for a few seconds. The app stops itself when the
entrypoint returns.

**Pass:** it prints `greeting: hello, surmap, from Modal`, a
`ta-...` task id and a `kernel` ending in `gvisor`, then
`✓ App completed`. A first run takes about 10 s; an image rebuild
takes longer.

Async WebSocket round trip (run it when the work talks to Modal over a
socket):

```bash
uvx --with websockets modal run .agents/skills/modal-cloud/scripts/ws_modal.py
```

It serves an `async def` FastAPI echo through `@modal.asgi_app` with
`@modal.concurrent`, in one container (0.25 CPU, 256 MB, 120 s), and
opens 3 connections at once from a local asyncio client. The endpoint
is **unauthenticated** while the app runs; Modal prints
`(unauthenticated)`. Real endpoints need `requires_proxy_auth=True` or
a token check. Messages are limited to 2 MiB, the client must pass
`compression=None` (no `permessage-deflate`), and a connection cannot
outlive the function `timeout`.

**Pass:** `PASS: async connections overlapped`, with the wall time well
under the sum of the per-connection times and `containers 1`. The first
run builds the image (about 15 s); the warm-up connection absorbs the
container cold start.

## 4. Real work: cost guardrails

Before running anything bigger than the smoke test, state to the user:
the workspace, the GPU type and count, `timeout`, and the expected
container count (`.map` fan-out). Get a yes for GPUs, `--detach`,
`modal deploy`, schedules, or anything left running after the command
returns.

In code, always set:

- `timeout=` on every `@app.function`, sized to the job. The default is
  300 s per call, and a longer one raised for a big job also lets a
  stuck container bill for that long;
- explicit `cpu=` / `memory=` / `gpu=`. Pick the smallest GPU that
  fits;
- `max_containers=` on functions you `.map` over.

Async works on both sides. Inside the container, `async def` functions
run on Modal's event loop, and `@modal.concurrent(max_inputs=...)` lets
one container serve several inputs at once, which suits I/O-bound
work. From async client code, call `.aio()` variants
(`await fn.remote.aio(x)`, `async for r in fn.map.aio(xs)`,
`await fn.spawn.aio(x)`) rather than the blocking calls.

Prefer `modal run` (ephemeral, stops with the local process) to
`modal deploy` (persists). Name apps `surmap-<purpose>` so step 5 can
find them.

Rates and spend:

```bash
uvx modal billing rates
uvx modal billing summary            # this month
```

## 5. Clean up

```bash
uvx modal app list --json            # state: ephemeral / deployed / stopped
uvx modal app logs <app-id>          # last 100 entries; -f to follow
uvx modal app stop <app-id>          # permanent
```

Stop every `surmap-*` app this session started that is not `stopped`,
unless the user asked for it to keep running. `modal app stop` is
permanent. Stop only apps you started, and ask about any other app.

**Pass:** no app this session started is left `ephemeral` or
`deployed` without the user's say-so.

## Scope

Modal is compute, not part of the survey pipeline. Code run there keeps
the scope guardrail in [AGENTS.md](../../../AGENTS.md): passive survey
only, no flight control or mission orchestration. RTAB-Map output stays
read-only; object layers are written beside it.
