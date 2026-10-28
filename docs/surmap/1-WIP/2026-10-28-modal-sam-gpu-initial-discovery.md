# Initial discovery — Modal GPU for the ONNX SAM path

## Combined Conclusions

Station SAM 3.1 already runs as `Sam3Detector` over a `Sam3Session`.
`OnnxSam3Session` (`src/surmap/survey/sam3.py`) is the only session:
ONNX Runtime, CUDA when asked, CPU in CI, fake graph
`tests/fixtures/sam3_fake/fake_sam3.onnx`. The contract is input
`image` float32 `[1, 3, H, W]` and outputs `masks` `[1, N, H, W]`,
`scores` `[1, N]`. Post-processing (threshold, box, outline polygon)
lives on `Sam3Detector` and must be reused, not reimplemented.

`station_main` selects that path with `--detector sam3` and
`--sam3-device auto|cpu|cuda`. There is no Modal client, no
`MODAL_SAM_URL`, and no `modal` dependency. `pyproject.toml` does not
list Modal. CI must stay that way: no account, no token, no import of
`modal` at test collection.

`HACKATHON.md` is not on `main`. It exists on PR #28
(`cursor/readme-meta-models-24f9`) with a Credits row: Modal is
"Planned" and "No Modal app in this repo". This change adds the file
with that row reworded and a deploy/stop/spend section. `README.md`
is not edited (review on PR #28). `docs/architecture.md` is edited on
`feat/PX4_sitl` (PR #18); leave it alone.

`src/surmap/usage.py` is not on `main` and not on any open PR. The
session takes optional callbacks so that module can be wired later
without this PR importing it.

Native optional libraries in this repo (`rtabmap.py`, `sam3.py`) are
loaded with `importlib` behind a typed seam. Modal follows that.

Deferred TODOs under `src/surmap/docs/todo/` are all moving-object
work. No `src/surmap/docs/code-issues/`. None block a Modal session.

Modal's current function API (docs, Oct 2026): `gpu`, `timeout`,
`scaledown_window` (idle time before scale-down; default max 60s),
`max_containers`, `min_containers` (keep-warm; omit it). Web entry is
`@modal.fastapi_endpoint(method="POST")`. `modal deploy <file>` and
`modal app stop <app>` are the CLI. Spend is the workspace usage page
in the Modal dashboard.

## Exploration 1

Parent-driven Grep / Glob / Read on 2026-10-28, before the changeset.

### Sequence

- Glob `**/*sam*`, `**/HACKATHON.md`, `**/usage.py` — locate the ONNX
  path and confirm the hackathon note and usage module are absent on
  this checkout.
- Grep `onnx|sam3|Modal` in `*.py` / `*.md` — station entry, tests,
  architecture mentions.
- `gh api` comment `6479197917` and `gh pr view 28` — the task text.
- `gh api` PR #28 comments — sibling tasks and the README review.
- `gh api` contents of `HACKATHON.md` at `cursor/readme-meta-models-24f9`.
- Read `src/surmap/survey/sam3.py`, `station_main.py`, `sam.py`,
  `src/surmap/slam/rtabmap.py`, `tests/test_sam3.py`, `pyproject.toml`,
  `README.md` (station SAM note), `docs/architecture.md` SAM section.
- Web search and fetch of Modal timeout, scale, and web-endpoint docs.

### Inspected files

- `src/surmap/survey/sam3.py` — `Sam3Session` protocol (`provider`,
  `input_size`, `run`), `OnnxSam3Session`, `Sam3Detector._segment`
  (resize, threshold, `_mask_outline`), `sam3_detector`.
- `src/surmap/survey/station_main.py` — `--detector memory|sam3`,
  `--sam3-device auto|cpu|cuda`, model path required for `sam3`.
- `src/surmap/survey/sam.py` — `SamDetector.detect`, `SamDetection`
  (`label`, `score`, `box_xyxy`, `mask_polygon`).
- `src/surmap/slam/rtabmap.py` — lazy `importlib.import_module`,
  typed protocol, unavailable error. The Modal seam copies this.
- `tests/test_sam3.py` — fake ONNX on CPU, polygon assertion, station
  description. Existing tests stay green.
- `pyproject.toml` — dependencies include `onnxruntime` (CPU wheel).
  No Modal. mypy strict on `src` and `tests`.
- `HACKATHON.md` on PR #28 — Credits table, third-party SAM row,
  "Not in this tree" lists Modal as unused.
- `src/surmap/docs/todo/` — moving-object deferrals only.

### Findings

- A Modal session can implement `Sam3Session` and be passed to the
  existing `Sam3Detector`. No second post-processor.
- The checkpoint must not be committed. The remote image reads it
  from a Modal Volume. CI uses a fake HTTP body, not a GPU.
- `modal` cannot be a required import. Build the App only after
  `importlib` succeeds, so collection on CI leaves `app` unset.
- Usage hooks are optional arguments. Missing `usage.py` is not a
  blocker.
- README stays untouched. Runbook goes in the module docstring and
  `HACKATHON.md`.
