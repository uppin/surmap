# Bevy WASM disaster simulation (PoC)

A browser-only proof of concept: the disaster-flight simulation runs
entirely in a web page. Nothing is sent to a backend — no frames, no
telemetry, no fetch. A later phase can add frame export; this PoC
deliberately does not.

## Run

```bash
export PATH="$HOME/.rustup/toolchains/stable-aarch64-apple-darwin/bin:$HOME/.cargo/bin:$PATH"
cd examples/bevy-sitl-poc
trunk serve index.html --port 8772
# open http://127.0.0.1:8772/
```

`trunk build index.html` produces `dist/` for static hosting.

CI: `.github/workflows/bevy-wasm.yml` runs `cargo test --locked`
and `trunk build index.html --release` on every change to this
directory.

Requires a WebGPU-capable browser (Chrome/Edge on desktop). The
`webgpu` Bevy feature is load-bearing: Feronia's LOD puts a
`VisibilityRange` on every debris instance, and the WebGL2 fallback
backend cannot build that PBR pipeline (wgpu validation panic on
`visibility_ranges`, group 0 binding 14).

## What runs in the page

- **Bevy 0.18 (WASM/WebGPU)** renders a simplified disaster block:
  avenue, cross street, flood pond, pancaked slabs, cars, helipad,
  and the seven survivors at the ground-truth poses from
  `docs/simulation/gz/worlds/disaster_block_ground_truth.json`.
- **Rapier physics** (`bevy_rapier3d`) flies the quadcopter: dynamic
  rigid body, gravity, colliders on ground/buildings/cars, thrust
  applied as external force. Avian was evaluated first; its Bevy 0.18
  line is a pre-release that does not compile against the released
  Bevy, so Rapier is the physics engine here.
- **Feronia** (`bevy_feronia`, environment scattering) scatters
  wind-affected debris across the ground plane.
- **Stereo rig**: two Bevy cameras on the drone render 640x480
  left/right feeds into the side panel. They are real render targets,
  not pictures.

## Controls

Click the view. `Space` take off/land, `W A S D` move, `Q`/`E` yaw,
`R`/`F` up/down. The chase camera follows; stereo feeds track the rig.

## Camera calibration

The rig produces the same calibration a backend would consume,
derived from one source of truth (`src/calibration.rs`) so the Bevy
projection and the JSON cannot drift apart:

- 640x480, fx = fy = 381.36 px, cx = 320, cy = 240, baseline 0.07 m
- left eye at rig x = -0.035 m, right eye at +0.035 m (x right, y up,
  z back)
- vertical FOV = 2*atan(cy/fy) ≈ 1.1234 rad, fed into Bevy's
  `PerspectiveProjection`

The panel in the page prints these values from the running app, and
`StereoCalibration::to_json()` emits them as JSON. Native tests:
`cargo test` (4 tests pin the numbers, the extrinsics, the derived
FOV, and the JSON shape).

## Not in this PoC

Frame sending to a backend, RTAB-Map, detection/labelling, and the
8770 mission viewer are all downstream of the capture this page does
not produce yet. The seam for that phase is the stereo render
targets plus the calibration JSON above.
