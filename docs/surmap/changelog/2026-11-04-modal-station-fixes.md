# Modal station: the SAM prompt reaches the container, the GPU falls back, sam3 keeps surmap's numpy

**Date:** 2026-11-04
**Fix:** Survey servers on Modal / `surmap-station`

- **Prompt.** `modal_station_app.py` read `SURMAP_STATION_LABEL` at import, and Modal imports
  the file again inside the container without the deploy shell's env, so the station always
  prompted `object` (no candidates on the EuRoC frames). `modal_hosting.StationSettings` reads
  GPU list, timeout, scaledown window and label where the app is deployed; `container_env()`
  travels to the container in a `Secret.from_dict`.
- **GPU.** `gpu=["L4", "A10G"]` by default; `SURMAP_MODAL_GPU` takes a comma list. A workspace
  with no free L4 had left the app waiting 40+ minutes with no container, log or cost.
- **numpy.** sam3 declares `numpy<2`; it runs on surmap's `numpy>=2.4.6`. The image installs
  sam3's other declared deps (`SAM3_RUNTIME_PACKAGES`) before the pyproject and `sam3` itself
  `--no-deps` after it; the build log has no conflict.
- **Verifier.** `scripts/verify_station.py --prompt <concept>` (default `mattress`) sends
  `StationStreamConfig.concept_prompts`; `--prompt ""` leaves the station's label in charge.
- **Verified** on Modal (`ginas-bb`, 2026-11-04): with the label set at deploy time and no
  client prompt, SAM 3.1 detections on 6 of 12 EuRoC frames on `cuda:0`.
- **Tests.** Seven in `tests/test_modal_survey_apps.py` and `tests/test_verify_station.py`.

Docs: [docs/modal.md](../../modal.md) §5.
