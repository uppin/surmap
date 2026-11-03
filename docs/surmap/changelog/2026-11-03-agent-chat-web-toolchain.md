# Web toolchain for the agent chat

**Date:** 2026-11-03
**Feature:** survey agent chat

Added `web/agent-chat/`, the front-end package for the survey agent chat: Vite 8, React 19,
TypeScript 5.9 in strict mode, Tailwind 4, shadcn/ui primitives (Radix based, copied into
`src/components/ui`), ESLint 10 and Vitest 4. The connect-es v2 / protobuf-es v2 client is generated
from `proto/surmap/agent/v1` by `yarn gen`, and the generated TypeScript is committed. A placeholder
page lists the `SurveyTools` rpcs from the generated descriptor.

The package uses yarn 1. The committed `yarn.lock` keeps public `registry.yarnpkg.com` URLs but pins
the versions the private registry serves. `yarn local-install` installs from the private registry on
a machine with no public npm access and restores the lock afterwards; `yarn resolve-local-lock`
(a zero-dependency node script, with `--check` mode and its own tests) normalises the lock after a
dependency change. Packages are pinned to node 20 compatible releases.

A new `agent-chat` workflow, path-filtered on `web/agent-chat/**` and `proto/surmap/agent/**`,
installs from the public registry with the committed lock, rejects `resolved` URLs outside
`registry.yarnpkg.com`, checks generated code for drift, then runs lint, typecheck, test and build.
Python code and the `ci.yml` workflow are unchanged.

Verification: the V3 command (`yarn local-install`, `yarn gen`, no diff in `src/gen` or `yarn.lock`,
lint, typecheck, `yarn test --run`, `yarn build`, `resolve-local-lock.mjs --check`) exited 0 on the
final tree.
