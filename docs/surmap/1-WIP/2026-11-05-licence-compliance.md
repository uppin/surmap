# Changeset: The public repo carries only what it may redistribute, and credits what it shows

**Date**: 2026-11-05
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 4. It touches three packages: `surmap.simulation`,
`surmap.survey.modal_hosting` and the two web builds. It also swaps a test fixture.

## Workflow

- [wf 1] ✅ 2026-11-05 `/plan-red` Plan — changeset, initial discovery · this file + companion
- [wf 2] ✅ 2026-11-05 `/plan-red` Red — failing tests · 4 credit tests, 5 notices tests (module missing), 4 preflight tests, 1 alignment test red
  - [x] CC BY pins carry a title and an author; a scenario credits the pinned CC BY models it shows
  - [x] `crate_notices` collects the licence texts of the crates the WASM bundle links
  - [x] The deploy refuses a simulation or chat build without its third-party licence file
  - [x] The reconstructor's `alignment_offset` compensates a right frame offset by a known amount (the coverage ETH3D gave)
- [wf 3] ⏳ `/green` Green — implement until every red test passes ·
  - [x] `StereoReconstructor` shifts the right frame against its documented offset: the ETH3D pairs give 12,613 points with the negated offset, 4,068 with the old sign and 6,264 with none
  - [x] ETH3D fixture replaced by `tests/fixtures/plane_stereo` (CC0 photo texture on a known plane, rendered by `scripts/render_plane_stereo_fixture.py`); both stereo tests read it
  - [x] Lock: `title`/`author` on the two CC BY pins; `ScenarioStore` credits them
  - [x] `scripts/sim_notices.py` writes `dist/THIRD_PARTY_LICENSES.md` after `trunk build`
  - [x] Vite `build.license` writes the chat's `dist/THIRD_PARTY_LICENSES.md`
  - [ ] The `/sim/` page lists the asset credits from `assets.lock.json` and links the licences (written; browser check pending)
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded
  - [ ] `NOTICE`, `docs/third-party-licences.md`: ETH3D removed, CC BY models listed, notices generated
  - [ ] `docs/modal.md` and the `modal_agent_app` docstring: the notices step in the deploy
  - [ ] Changelog entry in `docs/surmap/changelog/`

## Initial Discovery

The codebase exploration this plan rests on:
[initial-discovery.md](./2026-11-05-licence-compliance-initial-discovery.md).

## Summary

The licence audit left three gaps that matter for a public repo with a public deployment:

1. Non-commercial, share-alike ETH3D frames are committed to the repo.
2. Two CC BY models are shown without a visible credit.
3. The two shipped web bundles include third-party code without its notices.

This change closes all three.

## Technical Changes

### State A (Current)

- **Fixture.** `tests/fixtures/eth3d_cables2/` (ETH3D, NC research use) feeds
  `test_survey_stereo.py` and `test_survey_cm5_stereo_e2e.py`.
- **Credits.** `ScenarioStore._credits` credits Sketchfab library assets and the OSM floor.
  The pinned CC BY models are credited only in the lock file and the docs.
- **Notices.** Neither the chat's Vite build nor the Bevy `trunk build` includes
  third-party notices.

### State B (Target)

- **Fixture.** `tests/fixtures/plane_stereo/` holds 10 pairs rendered by
  `scripts/render_plane_stereo_fixture.py`. Each pair is the ELP rig looking at a CC0
  photo-textured plane about 0.45 m away, so every pixel's true depth is known, and the
  right principal point is offset by (+10, +12) px. It is Apache-2.0 with the rest of the
  repo, and both stereo tests read it. The ETH3D directory is deleted.
- **Alignment.** `StereoReconstructor` shifts the right frame by `-alignment_offset`, which
  lines up the two principal points. Before, it shifted by `+alignment_offset`, away from
  alignment.
- **Credits.**
  - A CC BY pin carries `title` and `author` as well as `attribution`.
  - `ScenarioStore` credits every CC BY pin that a scenario uses, either as a model `glb`
    or through a vehicle class's `glb`. The chat's simulation pane already shows credits.
  - The standalone `/sim/` page reads `assets/assets.lock.json` and lists every pin's
    attribution, with a link to the licence file.
- **Notices.**
  - `surmap.simulation.crate_notices` reads `cargo metadata`, walks the normal
    (non-dev, non-build) dependencies for `wasm32-unknown-unknown`, and renders each
    crate's licence files.
  - `scripts/sim_notices.py` writes the result to `dist/THIRD_PARTY_LICENSES.md`.
  - The chat's Vite build emits its own `dist/THIRD_PARTY_LICENSES.md` (`build.license`).
  - The deploy preflight refuses either bundle when its licence file is missing.

### Delta

- `src/surmap/simulation/sim_assets.py`: `AssetPin.title`, `AssetPin.author`.
- `src/surmap/simulation/scenario_store.py`: pinned CC BY credits.
- `src/surmap/simulation/crate_notices.py` (new) and `scripts/sim_notices.py` (new).
- `src/surmap/survey/modal_hosting.py`:
  - `check_sim_bundle` also requires the licence file;
  - `check_chat_bundle` is new;
  - `modal_agent_app` calls both.
- `web/agent-chat/vite.config.ts`: `build.license`.
- `examples/bevy-sitl-poc/index.html`: a credits line.
- `examples/bevy-sitl-poc/assets/assets.lock.json`: `title`/`author` on the two CC BY pins.
- `tests/fixtures/eth3d_cables2/` is deleted; `tests/fixtures/plane_stereo/` and
  `scripts/render_plane_stereo_fixture.py` are added.
- `src/surmap/survey/stereo.py`: the sign of the alignment shift.

## Verification

**Method:** V1-fail→pass for the credits, the notices and the preflight. V3 for the two builds.

**Command:**
- `uv run pytest -q tests/test_sim_assets.py tests/test_sim_scenario_store.py tests/test_sim_crate_notices.py tests/test_modal_sim_bundle.py tests/test_survey_stereo.py tests/test_survey_cm5_stereo_e2e.py`
- `(cd web/agent-chat && yarn build) && ls web/agent-chat/dist/THIRD_PARTY_LICENSES.md`
- `(cd examples/bevy-sitl-poc && trunk build index.html --release) && uv run python scripts/sim_notices.py && ls examples/bevy-sitl-poc/dist/THIRD_PARTY_LICENSES.md`

**Before:**
- The new tests fail: `title` is missing, `crate_notices` does not exist, and the preflight
  accepts a bundle without notices.
- Neither build writes the licence file.

**After:**
- The tests are green.
- Both licence files exist and name the bundled crates and packages.
- `git ls-files tests/fixtures | grep -i eth3d` is empty.

## Decisions & Trade-offs

- **Rendered pairs over real ETH3D pairs.** Bevy captures were tried first. The existing
  capture, and new ones on the 0.30 m and ELP rigs, all sit beyond the matcher's 0.2–8 m
  range at the PoC's 7 m altitude, so their points pile up at the smallest disparity. A
  CC0 texture on a known plane gives exact ground truth instead: more than 99% of the
  points are within 5 cm of the plane. The tests lose real sensor noise. Only the ETH3D e2e exercised the reconstructor's `alignment_offset`, so a
  new synthetic test in `test_survey_stereo.py` covers it: the right frame is offset by a
  known amount and the offset is compensated.
- **Generated notices, not committed ones.** About 590 crates' licence texts would bloat
  the repo and drift from `Cargo.lock`. They are generated after each build instead, and
  the deploy refuses a bundle that lacks them.
- **No new dependency.** Vite's built-in `build.license` is used, and the Rust side uses
  `cargo metadata` with a stdlib walker instead of `cargo-about`.
