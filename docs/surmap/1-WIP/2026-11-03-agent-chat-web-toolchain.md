# Changeset: Web toolchain for the agent chat — Vite, React, TypeScript, Tailwind, shadcn/ui, connect-es

**Date**: 2026-11-03
**Status**: 🚧 In Progress
**Type**: Infra
**Behaviour**: preserves
**Complexity**: 3 — new toolchain and CI workflow, generated TS client from proto, private-registry lock resolver and local install; no Python change

## Workflow

- [wf 1] ✅ 2026-11-03 `/plan-ft-dev` Plan — changeset with a V3 `## Verification` and its before-output · this file + discovery (commit 1, a6a921c); V3 before-output recorded — commit 2
  - [x] Record initial discovery
  - [x] Cross-check `src/surmap/docs/todo/` and `src/surmap/docs/code-issues/`
  - [x] Create/update PRD documentation — None — Infra, no user-visible behaviour delta
  - [x] Create changeset
  - [x] Before-output re-recorded on the branch tip (commit 2)
- [wf 2] ✅ 2026-11-03 `/green` Implement — the recorded command produces the planned after-output · V3 After output recorded in `## Verification` (clean `node_modules`, empty yarn cache, every step exit 0); vitest 14/14 (App 2, resolver 12); Python gates green (ruff format, ruff check, mypy, pytest 1481 passed / 32 skipped, no Python change)
  - [x] `web/agent-chat/` scaffold (yarn 1.22.22, `"packageManager": "yarn@1.22.22"`, `yarn.lock`, no `package-lock.json`): Vite 8, React 19, TypeScript 5.9 strict, Tailwind 4, ESLint 10, Vitest 4 — versions pinned to what the private registry serves (table below; protobuf-es at 2.13.0, see Decisions)
  - [x] `scripts/resolve-local-lock.mjs` (node ESM, zero deps): resolves every `yarn.lock` entry against `$LOCAL_REGISTRY_URL`, rewrites `version`/`integrity`/`resolved` (public `registry.yarnpkg.com` URL), widens/pins `package.json` ranges, `--check` mode
  - [x] `scripts/local-install.sh`: temp lock with private-host `resolved`, `yarn install --frozen-lockfile --registry "$LOCAL_REGISTRY_URL"`, restore on EXIT, fail if the restored lock differs
  - [x] `scripts/resolve-local-lock.test.mjs` (vitest, fake registry on a local HTTP server): exact kept, missing version downgraded to highest ≤ locked, resolved host rewritten to public, scoped names, `--check` fails on a private-host URL
  - [x] `package.json` scripts `local-install`, `resolve-local-lock`, `gen`, `lint`, `typecheck`, `test`, `build`
  - [x] shadcn/ui initialised (`components.json`, `src/components/ui/{button,card,textarea,scroll-area,badge,separator}.tsx`, `src/lib/utils.ts`; sources copied from the registry JSON, not `shadcn add` — see Decisions)
  - [x] `buf.gen.yaml` + `yarn gen` → `src/gen/surmap/agent/v1/*_pb.ts` via `@bufbuild/protoc-gen-es` v2 from `proto/surmap/agent/v1`
  - [x] Placeholder page renders the shadcn `Card` with the list of `SurveyTools` rpcs from the generated descriptor (`src/App.test.tsx`)
  - [x] `.github/workflows/agent-chat.yml` (public runners): `yarn install --frozen-lockfile` from the public registry, a guard that every `resolved` URL is on `registry.yarnpkg.com`, `yarn gen` + `git diff --exit-code src/gen`, `lint`, `typecheck`, `test`, `build` (`--check` runs on the dev machine only — see Decisions)
  - [x] root `.gitignore`: `web/agent-chat/node_modules`, `web/agent-chat/dist`, `web/agent-chat/yarn.lock.local-install-backup`
  - [x] The V3 command produces the After output below
- [wf 3] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded
  - [ ] `web/agent-chat/README.md` — dev, gen, test and build commands; the add-a-dependency loop (`yarn add <pkg> --registry $LOCAL_REGISTRY_URL` → `yarn resolve-local-lock` → `yarn local-install`)
  - [ ] `README.md` — one line pointing at `web/agent-chat/`
  - [ ] `docs/surmap/changelog/2026-11-03-agent-chat-web-toolchain.md` — write changelog entry

## Initial Discovery

Full codebase exploration that grounded this plan:
[2026-11-03-agent-chat-web-toolchain-initial-discovery.md](./2026-11-03-agent-chat-web-toolchain-initial-discovery.md).

## Stack Context

**Stack**: survey agent · slug **`#survey-agent`** — this PR is **6 of 9** · [#82](https://github.com/uppin/surmap/pull/82)
**Branch**: `pr-6-survey-agent` · **Base**: `pr-5-survey-agent`
**Successor**: `pr-7-survey-agent`
**Kind**: Infra · behaviour-preserves
**Workflow**: preset `infra` · planned by `/plan-pr-stack` · pass-2 = the V3 command and its recorded before-state

Why the boundary falls here: the repo has no JavaScript toolchain; landing one (and its CI) apart
from the chat UI keeps the UI PR about behaviour and lets the toolchain go green in wave 1.

### Owned API surface

- `web/agent-chat/` (package, `yarn.lock`, configs, `components.json`, shadcn primitives, `buf.gen.yaml`, placeholder `App.tsx`)
- `web/agent-chat/scripts/{resolve-local-lock.mjs,local-install.sh,resolve-local-lock.test.mjs}`
- `.github/workflows/agent-chat.yml`

### Green wave

**Wave:** 1 of 4
**Node:** n6
**Concurrent with:** n1, n2, n3, n4, n5
**Blocks:** n9 (builds the chat UI in this package)

Real dependency edges, as opposed to the branch line:

    n1 → n7, n8        n1 ⇢ n4, n9 (compile only)
    n2 → n7    n3 → n7    n4 → n8    n5 → n8    n7 → n8    n6 → n9    n8 → n9

### Greenable independently?

**yes** — codegen reads `proto/surmap/agent/v1/*.proto`, which n1's red commit adds; the toolchain
does not need n1's Python implementation.

### Trunk-merge safety

**When this PR merges alone:** Python CI (`ci.yml`) unchanged; a new, path-filtered workflow runs
only on `web/agent-chat/**` and `proto/surmap/agent/**`. **Local dev data:** no. **Production
data:** none.

## Inherited Dependencies — do not implement here

| Symbol / module | Owned by | State during this PR's green | What this PR does |
|---|---|---|---|
| `proto/surmap/agent/v1/*.proto` | n1 | present from n1's red commit | generates TS from it; never edits it |

**Greenable independently?** yes.

## Inherited Restructure — expect rewrite

n2 moves the demo run engine; this node touches no Python. No fallout expected.

## Affected Packages

- **web/agent-chat** (new, yarn 1); `.github/workflows/agent-chat.yml` (new); root `.gitignore` (`web/agent-chat/node_modules`, `dist`, `yarn.lock.local-install-backup`)

## Related Feature Documentation

None — Infra, no user-visible behaviour delta. No PRD.

## Summary

A Vite + React + TypeScript app with Tailwind and real shadcn/ui (`components.json`, Radix-based
primitives copied into `src/components/ui`), connect-es v2 / protobuf-es v2 code generated from the
agent protos, and a CI workflow that checks generation, lint, types, tests and the build. The
package uses yarn 1; on the dev machine (no public npm) `yarn local-install` installs from the
private registry, and a zero-dependency lock resolver keeps the committed `yarn.lock` on public
`registry.yarnpkg.com` URLs pinned to the versions the private registry serves.

## Background

The demo UI is HTML/JS inside Python strings (`demo/page.py`), with no JavaScript package anywhere. The developer
asked for a shadcn chat UI; that needs a real frontend package.

## Scope

- Toolchain, private-registry local install and lock resolver, shadcn init, codegen, placeholder page, CI
- **Out of scope:** chat behaviour (n9)

## Technical Changes

### State A (Current)

No `package.json` or lockfile in the repo; workflows `ci.yml`, `bevy-wasm-build.yml`,
`bevy-wasm-test.yml`. Local toolchain: node v20.19.5, yarn 1.22.22 (`/opt/homebrew/bin/yarn`);
no pnpm, no bun. The dev machine reaches the private registry `https://npm.dev.wixpress.com`
(user `~/.npmrc` / `~/.yarnrc` point `registry` at it); `registry.npmjs.org` and
`registry.yarnpkg.com` are unreachable from it. Root `.gitignore` has `dist/` only.

### State B (Target)

```text
web/agent-chat/
  package.json            "packageManager": "yarn@1.22.22"; scripts local-install,
                          resolve-local-lock, gen, lint, typecheck, test, build
  yarn.lock               resolved = https://registry.yarnpkg.com/...; versions = private registry's
  tsconfig.json  tsconfig.app.json  tsconfig.node.json  vite.config.ts  eslint.config.js
  components.json  buf.gen.yaml  index.html  README.md
  scripts/resolve-local-lock.mjs        lock resolver, --check mode
  scripts/local-install.sh              private-registry install, restores yarn.lock on EXIT
  scripts/resolve-local-lock.test.mjs   vitest, fake registry on a local HTTP server
  src/{main.tsx,App.tsx,index.css,lib/utils.ts}
  src/components/ui/{button,card,textarea,scroll-area,badge,separator}.tsx
  src/gen/surmap/agent/v1/{execution,survey_tools,jobs,chat}_pb.ts
  src/App.test.tsx
.github/workflows/agent-chat.yml
.gitignore   + web/agent-chat/node_modules, web/agent-chat/dist,
               web/agent-chat/yarn.lock.local-install-backup
```

**`scripts/resolve-local-lock.mjs`** (node ESM, zero dependencies, inlined semver;
`LOCAL_REGISTRY_URL`, default `https://npm.dev.wixpress.com`; concurrency 10, 120 s timeouts):
parses the yarn v1 `yarn.lock`; for each entry `name@version` the version is **kept** when a local
package cache (yarn v6 `~/Library/Caches/Yarn/v6`, npm `_cacache` index) holds that tarball from the
private host, or when `GET $REGISTRY/<name>/<version>` answers; otherwise the package document's
versions decide — exact, else highest ≤ locked, else `latest`. It **rewrites `yarn.lock` in
place**: `version`, `integrity` (the private registry's `dist.integrity`) and `resolved` set to the
public URL `https://registry.yarnpkg.com/<name>/-/<basename>-<version>.tgz#<shasum>` (scoped:
`@scope/name/-/name-<version>.tgz`); widens or pins the matching `package.json` range when a
changed version falls outside it; prints `[CHANGED] name: a -> b` and a summary. `--check` exits 1
if any `resolved` host is not `registry.yarnpkg.com` or any locked version is not served by the
private registry.

**`scripts/local-install.sh`**: backs up `yarn.lock` to `yarn.lock.local-install-backup`, writes a
temporary lock whose `resolved` hosts point at `$LOCAL_REGISTRY_URL`, runs
`yarn install --frozen-lockfile --registry "$LOCAL_REGISTRY_URL" "$@"`, restores `yarn.lock` on
EXIT (trap), and fails if the restored lock differs from the committed one.

**Pinned versions** (exact, each served by the private registry on 2026-11-03; node 20.19.5
compatible — `engines` checked):

| Package | Version | Note |
|---|---|---|
| `react`, `react-dom` | 19.3.1 | latest |
| `@types/react`, `@types/react-dom` | 19.3.0 | latest |
| `typescript` | 5.9.3 | latest 5.x — `typescript-eslint` 8.72 peers `typescript <6.1.0`; 7.x (latest) excluded |
| `vite` | 8.3.4 | latest; node `^20.19.0` |
| `@vitejs/plugin-react` | 6.1.2 | latest; peers `vite ^8` |
| `tailwindcss`, `@tailwindcss/vite` | 4.3.3 | latest |
| `tw-animate-css` | 1.4.0 | latest |
| `eslint` | 10.13.0 | latest; node `^20.19.0` |
| `@eslint/js` | 10.0.1 | latest |
| `typescript-eslint` | 8.72.0 | latest |
| `eslint-plugin-react-hooks` | 7.1.1 | latest |
| `eslint-plugin-react-refresh` | 0.5.7 | latest |
| `globals` | 17.13.0 | latest |
| `vitest` | 4.1.12 | `V4` tag — 5.x needs node ≥ 22.12 |
| `jsdom` | 29.1.1 | 30.x needs node ≥ 22.22 |
| `@testing-library/react` | 16.3.3 | latest |
| `@testing-library/dom` | 10.4.2 | latest |
| `@testing-library/jest-dom` | 6.9.1 | 6.10+ needs node ≥ 22 |
| `@types/node` | 20.19.43 | matches node 20 |
| `@bufbuild/protobuf`, `@bufbuild/protoc-gen-es` | 2.13.0 | newest v2 whose `engines` allow node 20 — 2.14+ declare node ≥ 22 |
| `@bufbuild/buf` | 1.74.0 | latest |
| `@connectrpc/connect`, `@connectrpc/connect-web` | 2.2.0 | latest v2 |
| `@radix-ui/react-slot` | 1.5.0 | latest |
| `@radix-ui/react-scroll-area` | 1.4.0 | latest |
| `@radix-ui/react-separator` | 1.2.0 | latest |
| `class-variance-authority` | 0.7.1 | latest |
| `clsx` | 2.1.1 | latest |
| `tailwind-merge` | 3.7.0 | latest |
| `lucide-react` | 1.60.0 | latest |
| `shadcn` (CLI, dev) | 4.22.1 | latest |

Transitive versions are whatever `yarn.lock` resolves, normalised by `yarn resolve-local-lock`.

### Delta (What's Changing)

#### web/agent-chat

- all files above (new): the Vite/React/TS/Tailwind/shadcn package, its `yarn.lock`, codegen
  config and generated TS, placeholder page and test
- `scripts/resolve-local-lock.mjs`, `scripts/local-install.sh` and the scripts' vitest test (new)

#### .github/workflows

- `agent-chat.yml` (new): path-filtered on `web/agent-chat/**` and `proto/surmap/agent/**`; public
  runner, `actions/setup-node` node 20.19, `corepack enable` (honours `packageManager`),
  `yarn install --frozen-lockfile` against the public registry, then gen + drift check, lint,
  typecheck, test, build, and a guard that every `resolved` URL is on `registry.yarnpkg.com`. `resolve-local-lock.mjs --check` is not in CI (it asks the private registry)

#### repo root

- `.gitignore`: `web/agent-chat/node_modules`, `web/agent-chat/dist`,
  `web/agent-chat/yarn.lock.local-install-backup`

## Verification

**Method:** V3 — a deterministic command whose before- and after-output are recorded here
**Command:** `cd web/agent-chat && yarn local-install && yarn gen && git diff --exit-code src/gen yarn.lock && yarn lint && yarn typecheck && yarn test --run && yarn build && node scripts/resolve-local-lock.mjs --check`
**Before** (2026-11-03, run from the repo root on `pr-6-survey-agent` at a6a921c; node v20.19.5,
yarn 1.22.22):

```text
$ cd web/agent-chat && yarn local-install && yarn gen && git diff --exit-code src/gen yarn.lock && yarn lint && yarn typecheck && yarn test --run && yarn build && node scripts/resolve-local-lock.mjs --check
zsh:cd:1: no such file or directory: web/agent-chat
exit=1
```

**After** (2026-11-03, `pr-6-survey-agent` after the rebase onto `pr-5-survey-agent` 00edf65; node v20.19.5, yarn 1.22.22; `web/agent-chat/node_modules` and `dist` removed and `YARN_CACHE_FOLDER` pointed at an empty folder, so `yarn local-install` fetched all 574 tarballs from `https://npm.dev.wixpress.com`; every step exits 0):

```text
$ cd web/agent-chat && yarn local-install && yarn gen && git diff --exit-code src/gen yarn.lock && yarn lint && yarn typecheck && yarn test --run && yarn build && node scripts/resolve-local-lock.mjs --check
yarn run v1.22.22
$ sh scripts/local-install.sh
local-install: installing from https://npm.dev.wixpress.com with a frozen lockfile
[1/5] Validating package.json...
[2/5] Resolving packages...
[3/5] Fetching packages...
info There appears to be trouble with your network connection. Retrying...
info There appears to be trouble with your network connection. Retrying...
[4/5] Linking dependencies...
warning Workspaces can only be enabled in private projects.
warning Workspaces can only be enabled in private projects.
warning Workspaces can only be enabled in private projects.
warning Workspaces can only be enabled in private projects.
warning Workspaces can only be enabled in private projects.
warning Workspaces can only be enabled in private projects.
warning Workspaces can only be enabled in private projects.
warning Workspaces can only be enabled in private projects.
warning Workspaces can only be enabled in private projects.
warning Workspaces can only be enabled in private projects.
[5/5] Building fresh packages...
local-install: yarn.lock restored to its committed, public-URL form.
Done in 261.41s.
yarn run v1.22.22
$ buf generate ../../proto --path ../../proto/surmap/agent/v1 --template buf.gen.yaml
Done in 1.39s.
yarn run v1.22.22
$ eslint .

/Users/mantasi/Code/yolo-survey-agent-n6/web/agent-chat/src/components/ui/badge.tsx
  47:17  warning  Fast refresh only works when a file only exports components. Use a new file to share constants or functions between components  react-refresh/only-export-components

/Users/mantasi/Code/yolo-survey-agent-n6/web/agent-chat/src/components/ui/button.tsx
  63:18  warning  Fast refresh only works when a file only exports components. Use a new file to share constants or functions between components  react-refresh/only-export-components

✖ 2 problems (0 errors, 2 warnings)

Done in 1.35s.
yarn run v1.22.22
$ tsc -p tsconfig.app.json --noEmit && tsc -p tsconfig.node.json --noEmit
Done in 1.71s.
yarn run v1.22.22
$ vitest --run

 RUN  v4.1.12 /Users/mantasi/Code/yolo-survey-agent-n6/web/agent-chat


 Test Files  2 passed (2)
      Tests  14 passed (14)
   Start at  13:37:20
   Duration  1.43s (transform 54ms, setup 210ms, import 81ms, tests 1.31s, environment 373ms)

Done in 3.89s.
yarn run v1.22.22
$ tsc -p tsconfig.app.json --noEmit && vite build
vite v8.3.4 building client environment for production...
transforming...
✓ 81 modules transformed.
rendering chunks...
computing gzip size...
dist/index.html                   0.40 kB │ gzip:  0.27 kB
dist/assets/index-B5xhTUr-.css   21.31 kB │ gzip:  4.58 kB
dist/assets/index-CmW02kE-.js   322.20 kB │ gzip: 98.97 kB

✓ built in 497ms
Done in 2.05s.
resolve-local-lock: yarn.lock OK, 574 package(s) on https://registry.yarnpkg.com and served by https://npm.dev.wixpress.com
exit=0
```

`yarn local-install` leaves `yarn.lock` byte-identical (the step restores it); `yarn gen` leaves `src/gen` and `yarn.lock` with no diff; `resolve-local-lock.mjs --check` passes on all 574 packages. The `agent-chat` workflow runs on the PR; its green run is the PR-green gate, not part of this row.

## Decisions & Trade-offs

- **yarn 1 with a private-registry local install; committed `yarn.lock` on public URLs** — the
  developer's requirement (2026-11-03): *"this computer has no access to public NPM. So please
  import the working 'local install' solution from ~/Code/tddy-coder to resolve versions from
  private registry, but keep yarn.lock with public. yarn.lock should be updated to match the
  versions with local as local versions are protected against CVE."* Why: the private registry's
  versions are the CVE-protected ones, so the lock pins exactly those; the dev machine cannot reach
  public npm, so local installs must go through `$LOCAL_REGISTRY_URL`; CI runs on public GitHub
  runners that cannot reach the private registry, so the committed `resolved` URLs stay on
  `registry.yarnpkg.com`. yarn 1.22.22 is what the dev machine has; bun and pnpm are not installed.
  The resolver is a node ESM port of the bun-based pattern (behaviour, not names), zero
  dependencies so it runs before any install.
- **node 20 compatible pins** — the dev machine runs node v20.19.5; `vitest` 5, `jsdom` 30 and
  `jest-dom` 6.10 require node ≥ 22, so the highest node-20 releases are pinned instead.
  `typescript` stays on 5.9.3 because `typescript-eslint` peers `<6.1.0`.
- **Real shadcn/ui** (`components.json` + Radix primitives copied in), not hand-rolled look-alikes.
- **connect-es over the Connect protocol** (`@connectrpc/connect-web`), which supports unary and
  server-streaming over `fetch` — no NDJSON/REST transcoding layer.
- **Generated TS is checked in** and CI fails on drift, matching how the Python `_pb2` files are kept.
- **protobuf-es pinned at 2.13.0, not 2.16.0** — `@bufbuild/protoc-gen-es` 2.14 and later declare `engines.node >=22`; yarn refuses the install on node 20.19.5 (`The engine "node" is incompatible`). 2.13.0 is the newest line that allows node 20, and `@bufbuild/protobuf` moves with it so generated imports and runtime match.
- **shadcn components copied from the registry JSON, not `shadcn add`** — `shadcn@4.22.1 add` tried `yarn add cn radix-ui`: the `cn` npm package needs node ≥ 22 and the monolithic `radix-ui` is not in the pinned table, so the CLI aborted with no files written. The six component files come from `https://ui.shadcn.com/r/styles/new-york-v4/<name>.json` with three import rewrites: `cn` → `@/lib/utils`, `radix-ui` → the pinned `@radix-ui/react-*` packages, and `Slot.Root` → `Slot` (the standalone package exports the component itself).
- **CI skips `--check` and runs an offline guard instead** — `--check` asks the private registry whether each locked version exists and matches, which public GitHub runners cannot reach. CI proves the committed lock installs from public npm (`yarn install --frozen-lockfile`) and fails on any `resolved` URL outside `registry.yarnpkg.com`. The V3 command runs `--check` on the dev machine.
- **The resolver is all-or-nothing** — a registry error for any package fails the run before `yarn.lock` is written (the tddy-coder reference kept such entries). A locked version the private registry does not serve resolves to the highest version at or below it, else `dist-tags.latest`, unless a local cache from the same host holds it, in which case it is kept. `--check` also compares integrity and shasum with the private registry and flags `package.json` ranges that have no lock key.
- **Two `react-refresh/only-export-components` warnings stay** — shadcn's `buttonVariants` and `badgeVariants` are exported beside their components upstream. `yarn lint` exits 0 with two warnings; no disable comment was added.
