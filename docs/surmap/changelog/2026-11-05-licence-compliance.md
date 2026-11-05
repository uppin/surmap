# Licences: the ETH3D frames leave the repo, the CC BY models are credited, both pages ship their notices

**Date:** 2026-11-05
**Fix:** Repository licensing (the gaps the audit in [third-party-licences.md](../../third-party-licences.md) left open)

- **Fixture.** `tests/fixtures/eth3d_cables2` held ETH3D's CC BY-NC-SA research frames, in a
  public Apache-2.0 repo. They are replaced by `tests/fixtures/plane_stereo`: ten ELP-rig pairs
  of Poly Haven's CC0 `rocks_ground_02`, projected onto a known plane and rendered
  deterministically by `scripts/render_plane_stereo_fixture.py`.
  - Bevy captures were tried first. At the PoC's 7 m altitude they sit beyond the matcher's
    0.2–8 m range, on both the 0.30 m rig and the ELP rig.
  - The tests now check geometry: more than 95% of points must lie within 5 cm of the true
    plane, where the old test only checked loose depth ranges.
  - The ETH3D frames remain in the git history.
- **Alignment.** `StereoReconstructor` shifted the right frame *by* `alignment_offset`, which
  moved it away from alignment. It now shifts by `-alignment_offset`.
  - No production caller passes an offset.
  - On the old ETH3D pairs, the documented offset gave 4,068 points, no offset gave 6,264,
    and the corrected sign gives 12,613.
  - On the plane fixture, more than 99% of points land on the plane with the offset, against
    about 25% without it.
- **Credits.** CC BY pins carry `title` and `author`. `ScenarioStore` credits each one a
  scenario shows: *Car Concept* (CC BY 4.0), as a model, and the Poly by Google *Bus*
  (CC BY 3.0), through the `bus` vehicle class. The chat's simulation pane shows those
  credits, and the standalone `/sim/` page lists the lock's credit lines.
- **Notices.**
  - `surmap.simulation.crate_notices` and `scripts/sim_notices.py` write the WASM bundle's
    `THIRD_PARTY_LICENSES.md` from `cargo metadata`. It covers 351 crates, quoting each
    distinct text once (about 750 KB).
  - Vite's `build.license` writes the chat's file (66 packages).
  - `check_sim_bundle` and the new `check_chat_bundle` refuse a deploy without them.
- **Tests:**
  - `tests/test_sim_crate_notices.py` (5 tests);
  - 4 preflight tests in `tests/test_modal_sim_bundle.py`;
  - 5 credit tests in `tests/test_sim_assets.py` and `tests/test_sim_scenario_store.py`;
  - the alignment test and the plane reconstruction test in `tests/test_survey_stereo.py`.

Docs: [third-party-licences.md](../../third-party-licences.md), [modal.md](../../modal.md),
[bevy-simulation.md](../../simulation/bevy-simulation.md).
