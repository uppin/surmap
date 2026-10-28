# Modal GPU for the SAM 3.1 ONNX path

The station posts an image tensor to `MODAL_SAM_URL`. The remote app
`surmap-sam` (`src/surmap/survey/modal_sam_app.py`) runs that ONNX file
on a GPU and returns `masks`, `scores`, and its own elapsed inference
time. `Sam3Detector` builds the polygon. CI does not install Modal and
does not hold a token.

## Deploy, stop, spend

Run these in WSL from the repo root. `modal token new` writes
`~/.modal.toml` on that machine. Do not commit it. Choose workspace
`ginas-bb` when the CLI asks.

```bash
uv run --with modal modal token new
uv run --with modal modal volume create surmap-sam3
uv run --with modal modal volume put surmap-sam3 ./sam3.1.onnx /sam3.1.onnx
uv run --with modal modal deploy src/surmap/survey/modal_sam_app.py
```

The default GPU is a T4. Set `SURMAP_MODAL_GPU` (for example `L4`) only
for the deploy command to change it. `SURMAP_MODAL_TIMEOUT` defaults to
300 seconds. `SURMAP_MODAL_SCALEDOWN_WINDOW` defaults to 60 seconds.
The function sets `max_containers=1` and does not set `min_containers`,
so the container scales to zero after that idle window.

Copy the web URL the deploy command prints, then start the station:

```bash
export MODAL_SAM_URL='https://<the-url-modal-printed>'
python -m surmap.survey.station_main --detector sam3-modal
```

`--detector sam3 --sam3-device modal` selects the same session.
`MODAL_SAM_MODEL` overrides the usage label (default
`surmap-sam/<gpu>`).

Stop the app when the survey is finished:

```bash
uv run --with modal modal app stop surmap-sam
```

Spend for workspace `ginas-bb` is the Usage page in the Modal
dashboard, <https://modal.com/settings/usage>, and the `surmap-sam`
app from `uv run --with modal modal app list`.

## How to obtain `sam3.1.onnx`

### Source

The weights are the gated Hugging Face repo
[`facebook/sam3.1`](https://huggingface.co/facebook/sam3.1). That repo
stores a PyTorch checkpoint, `sam3.1_multiplex.pt` (about 3.5 GB), plus
tokenizer files. It does not store an ONNX file. The model card points
at the SAM 3 code repo, [facebookresearch/sam3](https://github.com/facebookresearch/sam3).

### Licence and gating

The file `LICENSE` on that repo is the SAM License, last updated
19 November 2025:
<https://huggingface.co/facebook/sam3.1/blob/main/LICENSE>.

The repo is gated. Open the model page while logged in to Hugging
Face, accept the terms, and only then download. The license grants a
non-exclusive royalty-free right to use and modify the materials.
Redistribution of the weights or a derivative stays under the same
license and must include a copy of it. Trade-control terms exclude
military, weapons, and ITAR uses. This survey is civilian disaster
response. Do not commit the checkpoint or the ONNX file.

### Download

```bash
hf auth login
hf download facebook/sam3.1 sam3.1_multiplex.pt --local-dir ./sam3.1-weights
```

`hf` is the Hugging Face CLI (`huggingface_hub`). A 403 means the
gated terms are not accepted yet for that account.

`sam3.1_multiplex.pt` is not the file the Modal function loads.
`OnnxSam3Session` opens an ONNX graph at `/models/sam3.1.onnx`.

### Export

This repository does not export Meta's checkpoint. Meta's checkpoint
repo is weights only, and the SAM 3 GitHub issues that ask for an
official ONNX export do not ship one
([facebookresearch/sam3#159](https://github.com/facebookresearch/sam3/issues/159),
[facebookresearch/sam3#224](https://github.com/facebookresearch/sam3/issues/224)).

The only ONNX builder in this tree is the CI stand-in:

```bash
uv run --with onnx python scripts/make_fake_sam3_model.py
```

That writes `tests/fixtures/sam3_fake/fake_sam3.onnx`. The script's
`INPUT_SIZE` is 256. The graph segments bright regions. It is not
SAM 3.1 and must not be uploaded as the station checkpoint.

The file put on the volume has to match the contract in
`surmap.survey.sam3`: input `image` float32 `[1, 3, H, W]` with values
in 0..1, outputs `masks` float32 `[1, N, H, W]` and `scores` float32
`[1, N]`. Meta's own `Sam3Processor` defaults to a square resolution
of 1008 and normalizes with mean 0.5 and standard deviation 0.5.
SurMap's detector sends 0..1 RGB, so that normalization has to sit
inside the exported graph if the weights expect it.

### `MODAL_SAM_INPUT`

The variable is `WIDTHxHEIGHT` of the ONNX input, in pixels. The
default is `256x256`, which matches `INPUT_SIZE` in
`scripts/make_fake_sam3_model.py` and nothing else.

A graph whose spatial size is Meta's processor default needs:

```bash
export MODAL_SAM_INPUT=1008x1008
```

Set it to the width and height actually baked into the graph you
upload. The station resizes each frame to that size before the POST.

## Usage ledger

`ModalSamSession` does not import `surmap.usage`. A
`UsageLedger` from that module (PR #31) can be passed as the hooks:

- `before_call=ledger` calls `ledger.check("modal")` before the
  request. `before_call=ledger.check` is the same call. A raised
  `BudgetExceeded` blocks the POST.
- `on_usage=ledger` appends one record: provider `modal`, model
  `surmap-sam/<gpu>` (or `MODAL_SAM_MODEL`), 0 input tokens, 0 output
  tokens, `reasoning_tokens` null, and `t_unix` from `time.time()`.
- `on_gpu_seconds=ledger` is accepted and does not append a second
  line. `UsageRecord` has no GPU-seconds field. Pass a
  `Callable[[float], None]` to receive the remote `inference_seconds`.

A plain callback still works for each hook: `before_call(provider)`,
`on_usage(provider, model, 0, 0, None)`, and
`on_gpu_seconds(inference_seconds)`.
