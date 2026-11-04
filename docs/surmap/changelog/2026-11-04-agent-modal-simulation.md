# The deployed agent serves the simulation

**Date:** 2026-11-04
**Feature:** Modal / `surmap-agent`; Bevy simulation

- **The simulation on Modal.** The Modal agent command (`surmap.survey.modal_hosting`)
  passes `--sim-assets /opt/surmap/sim/assets` and `--sim-dist /opt/surmap/sim/dist`, and
  the agent image (`src/surmap/agent/modal_agent_app.py`) carries the PoC's assets, with the
  fetched pinned CC0 files, and its `trunk build` there. The deployed chat now has the
  simulation tools, the `/sim/` preview, and the `/sim/fleet` link the agent flies drones
  through (same port, `wss://` on HTTPS).
- **The latest WASM, or no deploy.** `check_sim_bundle` runs where the app is deployed
  (`modal.is_local()`), not in the container. It refuses a missing `dist/`, a `.wasm`
  older than any file under the PoC's `src/`, `index.html`, `Cargo.toml` or `Cargo.lock`,
  and pinned assets that were not fetched, naming the command that fixes each. The
  `dist/assets` link from the PoC README is not uploaded a second time.
- **Not yet:** the stereo bridge (`--bevy-bridge-port`) on Modal. It needs a same-port route
  and RTAB-Map built into the agent image, so it is a follow-up PR. Until then, the deployed
  preview shows no RTAB-Map keypoints and `drone_map_status` has no maps.
- **Tests.** `tests/test_modal_sim_bundle.py` (5: a current bundle, no build, a stale build
  from a source change and from a lock-file change, an unfetched pin), and three in
  `tests/test_modal_survey_apps.py` (command flags, image steps, the deploy-only check).

Docs: [docs/modal.md](../../modal.md) §5, [docs/agent.md](../../agent.md) (*Running the agent*).

**Verified:** the new tests failed at collection on the old code and pass on the new code;
`check_sim_bundle` refuses a checkout that has no build. The live deploy to `ginas-bb` with the
simulation is not done yet.
