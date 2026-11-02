# Changeset: GitHub Actions workflow for the Bevy WASM PoC

**Date**: 2026-11-02
**Status**: 🚧 In Progress
**Type**: Infra
**Behaviour**: preserves
**Complexity**: 1 — one new workflow file; no code or dependency changes

## Workflow

- [wf 1] ✅ 2026-11-02 `/plan-ft-dev` Plan — changeset with V3 verification, initial discovery · this file + `bevy-wasm-ci-initial-discovery.md`; `.github/workflows/ci.yml` covers Python only, PoC verified by hand
- [wf 2] ✅ 2026-11-02 `/green` Implement — GitHub workflow compiles the WASM bundle and runs the PoC tests · `.github/workflows/bevy-wasm.yml` added; exact commands green locally (cargo test 4/4, trunk build, bundle check)
  - [x] `.github/workflows/bevy-wasm.yml`: path-filtered to `examples/bevy-sitl-poc/**`, Rust stable + wasm32 target, `cargo test --locked`, `trunk build index.html --release`, bundle-present assertion
  - [x] Exact CI commands replicated locally and green
  - [x] Workflow YAML validated
- [wf 3] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [x] Verification executed — result recorded
  - [x] `examples/bevy-sitl-poc/README.md` — CI coverage noted
  - [ ] Four gates green: ruff check, ruff format, mypy, pytest (untouched Python; run to prove no regression)

## Initial Discovery

See `bevy-wasm-ci-initial-discovery.md`. In short: CI has no Rust
job today; the PoC's `cargo test` (4 calibration tests) and
`trunk build index.html --release` run only by hand on this Mac.
A separate path-filtered workflow (per the ci-build skill's
"keep the workflow boring") wires exactly those two commands into
GitHub Actions without touching the Python CI.

## Verification

| Check | Before | After (planned) |
|---|---|---|
| Workflow covering `examples/bevy-sitl-poc` | none (`grep` over `.github/workflows/`) | `.github/workflows/bevy-wasm.yml` triggers on PoC paths |
| PoC tests in CI | never run | `cargo test --locked` step (4 tests) |
| WASM compilation in CI | never run | `trunk build index.html --release` step + `dist/*_bg.wasm` present and non-empty |
| Local replication | manual, ad hoc | the workflow's exact commands run green on this Mac before pushing |

Verification executed 2026-11-02 (locally; the workflow itself first
runs when a PR touches the PoC paths): red confirmed first — no file
under `.github/workflows/` mentioned the PoC, cargo, or trunk. After
adding `bevy-wasm.yml`: YAML parses with the planned triggers, job,
and steps; `cargo test --locked` in `examples/bevy-sitl-poc` passes
4/4; `trunk build index.html --release` succeeds; the bundle check
finds a 46 MB `dist/*_bg.wasm`. Python gates (no Python changed):
ruff check clean, format clean (266 files), mypy strict clean
(237 files), pytest 996 passed / 6 skipped / 1 failed —
`test_euroc_pairs_stream_real_rtabmap_poses_and_points` times out
against the `amd64` RTAB-Map sidecar image running emulated on this
`arm64` host; pre-existing and environmental (CI's x86
`rtabmap-stream-e2e` job runs it natively), left as a finding for
the wrap row's gate item.
