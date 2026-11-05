# Initial discovery: licence compliance gaps in the public repo

Companion to [2026-11-05-licence-compliance.md](./2026-11-05-licence-compliance.md).

## What was audited

A licence sweep of the public `uppin/surmap` repo, run against `main` @ `fbb2916`, which
already holds `LICENSE` (Apache-2.0), `NOTICE` and `docs/third-party-licences.md`. The
sweep covered every tracked binary, every "adapted / ported from" marker, the asset lock,
and how the deployed Modal app ships the chat page and the simulation.

## Findings this change fixes

1. **ETH3D frames are committed.** `tests/fixtures/eth3d_cables2/` holds 10 downscaled
   stereo pairs. Third-party listings give ETH3D's licence as CC BY-NC-SA (3.0 or 4.0;
   the official page was not reachable). A downscaled copy is an adaptation, so it falls
   under share-alike as well as non-commercial. Two test modules use it:
   - `tests/test_survey_stereo.py`: one real-pair reconstruction test, plus the
     640×397 decode-size test.
   - `tests/test_survey_cm5_stereo_e2e.py`: ten pairs through the CM5 server.
2. **CC BY models are shown without a visible credit.** These are *Car Concept* (CC BY 4.0,
   `models/car_concept/CarConcept.glb`, the scene's cars) and Poly by Google's *Bus*
   (CC BY 3.0, `models/poly-pizza/bus.glb`, the `bus` vehicle class). Their credit lives
   only in `assets.lock.json` and the docs.
   - `ScenarioStore._credits` credits only library (Sketchfab) assets and the OSM floor.
   - The deployed `/sim/` page shows no credit.
3. **Neither build ships the notices of its third-party code.** The Vite build and the
   `trunk build` bundle both include third-party MIT, BSD and ISC code, but neither ships
   those notices. The audit already lists this as an open obligation.

## Codebase facts the plan rests on

- **The existing Bevy capture is out of the matcher's depth range.**
  `tests/fixtures/bevy_sim_capture` (rig 0.07 m, 640×480, ground about 10–20 m away)
  reconstructs about 3,700 points per pair, but the median depth equals the maximum
  (3.34 m, the smallest disparity). The scene is beyond the matcher's range, so the
  capture cannot replace ETH3D as it stands.
- **The PoC records captures itself:**
  `cargo run --release -- --record <dir> --frames N --rate-hz R --start S --jpeg [--camera <profile>]`.
  `cameras/wide-baseline-pinhole.camera.json` is a 0.30 m rig with the same intrinsics.
- **`StereoReconstructor` defaults:** `max_disparity` 64, depth kept within 0.2–8 m.
- **The asset pin already has a field for a credit.** `AssetPin` carries `attribution`,
  and a test refuses a CC BY pin that has none. The `Credit` type has
  `title`/`author`/`licence`/`page_url`, and `ScenarioStore` holds `assets_dir`, the
  simulation's assets folder, where `assets.lock.json` and `vehicle/*.vehicle.json` live.
- **Vite 8 can emit the licence file itself.** It has
  `build.license: boolean | { fileName }`, which writes the bundled dependencies'
  licences with no new dependency.
- **Nothing generates Rust notices yet.** `cargo-about` is not installed, but
  `cargo metadata` gives each crate's licence expression, its `manifest_path`, and the
  resolved dependency graph with dependency kinds.
- **`check_sim_bundle` is the deploy-time gate.** It runs in `modal_agent_app` before the
  image uploads `dist/`, so it is the place to refuse a bundle that has no notices.
