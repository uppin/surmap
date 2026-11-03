# agent-chat

Web front end for the SurMap survey agent: Vite, React 19, TypeScript (strict),
Tailwind 4, shadcn/ui (Radix primitives in `src/components/ui`) and a
connect-es / protobuf-es client generated from `proto/surmap/agent/v1`.
The package manager is yarn 1 (`"packageManager": "yarn@1.22.22"`); there is
no `package-lock.json`.

## Commands

Run from `web/agent-chat/`.

| Command | What it does |
|---|---|
| `yarn local-install` | Install from the private registry (see below). Use this on the dev machine. |
| `yarn install --frozen-lockfile` | Install from the public registry. CI only. |
| `yarn dev` | Vite dev server. |
| `yarn gen` | Regenerate `src/gen/**/*_pb.ts` from `../../proto/surmap/agent/v1` with `buf`. The output is committed; CI fails on drift. |
| `yarn lint` | ESLint. |
| `yarn typecheck` | `tsc` over the app and node configs. |
| `yarn test` | Vitest (`yarn test --run` for one pass). Includes the lock resolver tests. |
| `yarn build` | Type-check and `vite build` into `dist/`. |

## Running against a local agent server

```bash
# from the repository root
uv run python -m surmap.agent --sam-fake --model ollama:llama3.2   # http://127.0.0.1:8780
# from web/agent-chat/
yarn local-install
yarn dev                        # http://localhost:5173
```

Open `http://localhost:5173/`. `?server=<url>` points the page at another
agent server (default `http://127.0.0.1:8780`; add the page's origin to
`SURMAP_AGENT_CORS_ORIGINS` when it is not `http://localhost:5173`), and
`?conversation=<id>` opens a given conversation (default: one per tab,
kept across reloads). `yarn build && yarn preview` serves the production
build on the same port. What the page shows: [docs/agent.md](../../docs/agent.md#chat-ui).

`yarn e2e` runs the Playwright suite against a stub Connect server
(`e2e/stub-chat-server.ts`), not the real agent; it skips when Chromium is
not installed unless `E2E_REQUIRE_BROWSER=1`.

## Private registry and `yarn.lock`

The dev machine cannot reach public npm; it reaches a private registry
(`LOCAL_REGISTRY_URL`, default `https://npm.dev.wixpress.com`) whose package
versions are CVE-protected. CI runs on public runners that cannot reach it.
So `yarn.lock` is committed in a form both can use:

- every `resolved` URL points at `https://registry.yarnpkg.com/...`, so CI
  installs it unchanged;
- every `version`, `integrity` and shasum is the one the private registry
  serves, so the dev machine installs exactly the protected versions.

`yarn local-install` (`scripts/local-install.sh`) swaps in a temporary lock
whose `resolved` hosts point at `$LOCAL_REGISTRY_URL`, runs
`yarn install --frozen-lockfile --registry "$LOCAL_REGISTRY_URL"`, and
restores the committed `yarn.lock` on exit. It fails if the restored file
differs from the committed one. If a run is interrupted and leaves
`yarn.lock.local-install-backup`, copy it back over `yarn.lock` before retrying.

Never run a plain `yarn install` or `yarn add` against the public registry on
the dev machine: it cannot resolve there, and it would rewrite the lock.

## Adding or changing a dependency

1. Add it, pointing yarn at the private registry
   (or edit `package.json` by hand):
   `yarn add <pkg> --registry "$LOCAL_REGISTRY_URL"`
2. Normalise the lock: `yarn resolve-local-lock`.
   `scripts/resolve-local-lock.mjs` (node, no dependencies) checks every
   locked `name@version` against the private registry, keeps a version it
   serves, otherwise moves to the highest version at or below it (else
   `latest`), rewrites `version` / `integrity` / `resolved` (public URL), and
   widens or pins the `package.json` range when a version moved outside it.
   It prints `[CHANGED] name: a -> b` for each change.
3. Install from the normalised lock: `yarn local-install`.
4. Commit `package.json` and `yarn.lock` together.

`node scripts/resolve-local-lock.mjs --check` exits 1 when a `resolved` host is
not `registry.yarnpkg.com` or a locked version is not served by the private
registry. It asks the private registry, so it runs on the dev machine, not in CI.

`scripts/resolve-local-lock.mjs` is the entry point; its semver, lock-file, registry
and local-cache code lives in `scripts/lib/`.

Pinned versions stay node 20 compatible (the dev machine runs 20.19); a newer
major whose `engines` need node 22 is not taken until the toolchain moves.
