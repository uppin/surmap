# Bevy disaster simulation

A photo-real disaster block in Bevy 0.18 (WebGPU in the browser, or native) with a stereo
rig whose frames RTAB-Map consumes. Everything the simulation shows — the scene, materials,
models, sky, and the camera profile shared with RTAB-Map — is JSON and CC0 / CC BY assets
loaded at runtime from `assets/`; composing a simulation never rebuilds the WASM.

Full documentation: [docs/simulation/bevy-simulation.md](../../docs/simulation/bevy-simulation.md).

## Run

```bash
export PATH="$HOME/.rustup/toolchains/stable-aarch64-apple-darwin/bin:$HOME/.cargo/bin:$PATH"
uv run python scripts/fetch_sim_assets.py        # from the repo root: pinned CC0 assets
cd examples/bevy-sitl-poc
cargo run --release                               # native window
BEVY_ASSET_ROOT=$PWD cargo run --release -- --screenshot shots --at 20
BEVY_ASSET_ROOT=$PWD cargo run --release -- --record cap --frames 90 --start 15.5 --jpeg
BEVY_ASSET_ROOT=$PWD cargo run --release -- --record cap --frames 75 --rate-hz 1 --start 12 --jpeg --colour  # + colour left eye
# browser (WebGPU): serve the page and assets/ from one origin
trunk build index.html --release && ln -sfn ../assets dist/assets && python3 -m http.server 8772 -d dist
```

Requires a WebGPU-capable browser (Chrome/Edge on desktop). The `webgpu` Bevy feature is
load-bearing: Feronia's LOD puts a `VisibilityRange` on every debris instance, and the WebGL2
fallback cannot build that PBR pipeline.

## Controls

Click the view. `Space` take off/land, `W A S D` move, `Q`/`E` yaw, `R`/`F` up/down.
`--flight survey-loop` flies the scripted loop instead.

## Tests

`cargo test --locked` (manifest, camera profile and projection, wire goldens, flight,
recorder, sky bake, mips). CI: `.github/workflows/bevy-wasm-test.yml` and
`bevy-wasm-build.yml`; the RTAB-Map acceptance over a recorded capture is
`tests/test_bevy_sim_rtabmap_e2e.py` in the repo's sidecar CI job.
