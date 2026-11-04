# Initial Discovery: Modal station fixes — prompt, GPU fallback, sam3 numpy

## Combined Conclusions

- The station app's SAM prompt never reaches the container. `modal_station_app.py:38` reads
  `SURMAP_STATION_LABEL` at module import; Modal re-imports the module inside the container, where
  the variable is unset, so `serve()` always runs `station_command("object")`. Deploy-time-only
  settings (`gpu`, `timeout`, `scaledown_window`) are unaffected: Modal reads them when the
  function is defined locally.
- `object` is a poor default concept for SAM 3.1 — on the EuRoC V1_01 frame it returns no
  candidates at all, while `mattress` (3, top 0.594), `floor` (0.848) and `wall` (4) score.
- The station asks for exactly one GPU type (`L4`). On 2026-11-04 the `ginas-bb` workspace could
  not get an L4 for 40+ minutes: no container, no logs, $0, while `gpu="any"` got an A10G in
  6.9 s. Modal accepts a list of GPU types as a fallback order.
- The image installs `sam3` (declares `numpy>=1.26,<2`) and then surmap's pyproject
  (`numpy>=2.4.6`); pip prints a dependency-conflict warning. SAM 3.1 runs correctly on numpy
  2.4.6 (raw scores above, verified on an A10G). pip skips its post-install conflict check under
  `--no-deps`.
- `scripts/verify_station.py` sends no concept prompt, so a station on the default prompt fails
  its analysis check on the EuRoC fixture even when SAM works. The wire already carries prompts:
  `StationStreamConfig.concept_prompts`, applied by `station_server.py:119-122`.

## Exploration 1: live Modal runs and the app file — 2026-11-04

### Sequence

1. `modal serve src/surmap/survey/modal_station_app.py` on `mantas-27062` — refused: no payment
   method for L4 GPU functions.
2. Same on `ginas-bb` — container up in ~100 s, `verify_station.py --expect-device gpu`: health ✅,
   accelerator ✅ (`SAM 3.1 (PyTorch)`, `cuda:0`), analysis ❌ (0 frames with detections).
3. Re-served with `SURMAP_STATION_LABEL=mattress` — no container scheduled for 40+ min; probes:
   bare L4 116 s, station-shaped L4 none in 400 s, split shapes none in 300 s, `gpu="any"` A10G
   6.9 s; CPU smoke test fine throughout.
4. `SURMAP_MODAL_GPU=A10G` — up in 20 s; analysis still 0 detections with the label set.
5. Diagnostic in the station image (scratch app): raw scores per prompt (Conclusions).
6. Verifier with `concept_prompts=["mattress"]` injected: 6/12 frames with detections, all checks
   pass.

### Grep / glob

- `grep -n "_LABEL\|_GPU\|environ" src/surmap/survey/modal_station_app.py` — lines 35-38, 86, 100.
- `grep -rn "SURMAP_MODAL_GPU\|SURMAP_STATION_LABEL"` — also `modal_sam.py:106`,
  `modal_sam_app.py:35` (the separate `surmap-sam` app, out of scope), `docs/modal.md:51,158`.

### Inspected files

#### `src/surmap/survey/modal_station_app.py`

Module-level `_GPU`, `_TIMEOUT_S`, `_SCALEDOWN_S`, `_LABEL` from `os.environ`; image chain:
`debian_slim` → git → `.env(HF_*)` → torch (cu124) → sam3 + extras → `pip_install_from_pyproject`
→ `add_local_python_source("surmap")`; `serve()` Popens `station_command(_LABEL)`.

#### `src/surmap/survey/modal_hosting.py`

Importable constants and `station_command(label)`; tested directly by
`tests/test_modal_survey_apps.py`, which reads the app file with `ast` (CI has no `modal`).

#### `scripts/verify_station.py` / `tests/test_verify_station.py`

`verify()` builds the config message with calibration and analysis mode only; tests load the
script by path and run it against a local fake-SAM3 server.

### Findings

As in Combined Conclusions.
