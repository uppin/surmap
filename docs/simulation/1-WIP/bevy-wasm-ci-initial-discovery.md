# Discovery: Bevy WASM CI

Date: 2026-11-02. Host: this Mac (Apple Silicon), Rust 1.93.1 stable,
trunk 0.21.14 in `~/.cargo/bin`.

## Observed

- `.github/workflows/ci.yml` is the only workflow. It runs the Python
  gates (ruff, mypy strict, pytest on 3.11/3.12) plus Docker-based
  RTAB-Map/Coral e2e jobs. Nothing in it installs Rust, runs
  `cargo test`, or builds `examples/bevy-sitl-poc` — the PoC's 4
  calibration tests and the WASM bundle are currently verified only by
  hand on this Mac.
- The PoC builds with `trunk build index.html --release` from
  `examples/bevy-sitl-poc/` (trunk compiles for
  `wasm32-unknown-unknown`, runs wasm-bindgen, and applies
  `data-wasm-opt="z"` from `index.html`). Native tests:
  `cargo test` in the same directory (4 tests in
  `src/calibration.rs`).
- `examples/bevy-sitl-poc/.cargo/config.toml` selects the getrandom
  `wasm_js` backend for wasm32; cargo picks it up from the crate
  directory, so CI must run cargo/trunk with that directory as the
  working directory (or via `--manifest-path` for `cargo test`).
- `Cargo.lock` is committed in the PoC directory, so
  `cargo test --locked` is reproducible.
- The bundle needs Bevy's `webgpu` feature (already in
  `Cargo.toml`): Feronia's LOD `VisibilityRange` panics on the WebGL2
  fallback. CI only has to compile it, not run it in a browser.
- Per `.agents/skills/ci-build/SKILL.md`: keep the workflow boring —
  no caches beyond the standard Rust cache, no artefact uploads
  without a named consumer. A separate path-filtered workflow keeps
  the Python CI untouched and runs only when the PoC changes.

## Contract reused, not reinvented

Same commands a developer runs locally (PoC `README.md`): `cargo test`
and `trunk build index.html --release` in `examples/bevy-sitl-poc/`.
No new dependencies, no code changes — the workflow only wires them
into GitHub Actions.
