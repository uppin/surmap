# Modal: SAM 3.1 GPU, Muse Spark Open, and the survey servers

Three uses of Modal: the SAM 3.1 GPU app and the Muse Spark Open shared
endpoint (sections 1–4), and the survey servers — a simulated drone's CM5 and
the station — as Modal web servers (section 5). The first two are separate
Modal products. Neither is called from CI. No token is
committed. `README.md` does not repeat these steps.

SAM 3.1 runs as our own GPU app (`surmap-sam`): one L4 container, scale
to zero. Muse Spark Open is a Shared Endpoint: per-token, OpenAI-compatible
Chat Completions, text plus image plus audio. The model id on
[Modal's library page](https://modal.com/library/meta/muse-spark-open) is
`meta-models/Muse-Spark-Open-816B-A42B`.

Run every command below from the repo root in WSL, with `uv run`.
Do not call bare `python`.

## 1. Accept the SAM 3.1 licence and create a Hugging Face token

1. Open <https://huggingface.co/facebook/sam3.1> while logged in and
   accept the gated SAM License (19 November 2025). The repo stores
   `sam3.1_multiplex.pt` (about 3.5 GB), not an ONNX file. The model
   card points at [facebookresearch/sam3](https://github.com/facebookresearch/sam3).
   There is no Transformers integration.
2. Create a read token at <https://huggingface.co/settings/tokens>.
   Type it into the shell. It is not written to the repo.

## 2. Authenticate Modal and store the Hugging Face token

Workspace `ginas-bb`. The Modal token stays in `~/.modal.toml`.

```bash
uv run --with modal modal token new
read -rs HF_TOKEN
uv run --with modal modal secret create huggingface HF_TOKEN="$HF_TOKEN"
unset HF_TOKEN
```

`modal secret create huggingface HF_TOKEN=...` is the same command if
you paste the token yourself. Do not commit it and do not put it in a
file in this tree. The GPU function reads `HF_TOKEN` from that secret.

## 3. Deploy SAM 3.1

The app file defines `app`, `image`, and `segment` at module scope.
Modal 1.x rejects a function nested inside another function.

The default GPU is an **L4** (24 GB). A T4 has 16 GB. The checkpoint
is 3.5 GB on disk and the image backbone's activations do not fit
comfortably beside it; Meta's own throughput figures are on an H100.
An A10G is also 24 GB and older. Set `SURMAP_MODAL_GPU=A10G` on the
deploy command to use one. `timeout` is 300 seconds,
`scaledown_window` is 60 seconds, `max_containers` is 1, and
`min_containers` is not set, so the container scales to zero.

On first request the function downloads `facebook/sam3.1` into Volume
`surmap-sam3` (mounted at `/models`) with
`download_ckpt_from_hf(version="sam3.1")`, then
`build_sam3_image_model(checkpoint_path=..., load_from_HF=False)`.
The image installs PyTorch (CUDA 12.4) and
`git+https://github.com/facebookresearch/sam3.git`. The local ONNX
station path (`--detector sam3 --sam3-model`) is unchanged and is not
what this app runs. `scripts/make_fake_sam3_model.py` is only the CI
stand-in.

```bash
uv run --with modal modal deploy src/surmap/survey/modal_sam_app.py
```

Copy the printed web URL.

```bash
export MODAL_SAM_URL='https://<the-url-modal-printed>'
uv run python scripts/check_modal_sam.py
```

The check posts `tests/fixtures/modal_sam/person.jpg` with the prompt
`person` and prints detections and `inference_seconds` (GPU time
inside the remote function).

Start the station the same way:

```bash
uv run python -m surmap.survey.station_main --detector sam3-modal --sam3-label person
```

`--sam3-device modal` on `--detector sam3` selects the same detector.
`MODAL_SAM_PROMPT` overrides the label.

Stop the app when the survey is finished so it cannot boot another GPU:

```bash
uv run --with modal modal app stop surmap-sam
```

Spend for the GPU app (workspace `ginas-bb`) is
<https://modal.com/settings/usage> and
`uv run --with modal modal app list`.

## 4. Muse Spark Open shared endpoint

Create a proxy token, then the shared endpoint. The CLI prints an id
and a secret. Join them as `Authorization: Bearer <id>.<secret>`.

```bash
uv run --with modal modal workspace proxy-tokens create
uv run --with modal modal endpoint create --shared --model meta-models/Muse-Spark-Open-816B-A42B
```

Copy the endpoint URL from the CLI or the dashboard. It is called at
`<endpoint-url>/v1/chat/completions`.

```bash
export MODAL_MUSE_URL='https://<the-endpoint-url>'
export MODAL_MUSE_MODEL='meta-models/Muse-Spark-Open-816B-A42B'
export MODAL_PROXY_TOKEN_ID='<proxy token id>'
export MODAL_PROXY_TOKEN_SECRET='<proxy token secret>'
uv run python scripts/check_modal_muse.py
```

The check sends one chat completion and prints the assistant text.
A live pytest of the same call is gated:

```bash
SURMAP_LIVE_MODAL=1 uv run pytest -q tests/test_modal_muse.py -k live
```

Shared-endpoint spend is per token
([supported models](https://modal.com/docs/guide/supported-models)):
Muse Spark Open is 1.25 USD per million input tokens (0.15 cached)
and 4.25 USD per million output tokens. See the usage page. Credits
on a Modal plan do not cover shared endpoints.

`ModalMuseClient.label(jpeg, hint)` posts the crop as an image and the
hint as text. `chat(messages)` posts any message list. `max_tokens`
defaults to 4096. An empty reply or `finish_reason=length` is retried
once with at least 8192 tokens. `before_call("modal")` runs before
each POST and can raise to block it. `on_usage("modal", model,
prompt_tokens, completion_tokens, reasoning_tokens)` records the
response counts. A `UsageLedger` can be passed as either hook
(`check` before the call, the ledger itself as `on_usage`) without
this package importing `surmap.usage`.

## 5. The survey servers on Modal: a simulated drone and the station

Two app files run the existing survey mains as `@modal.web_server` functions,
one container each (`max_containers=1`: a survey's region queries must reach
the server holding its frames). Clients reach them over the app's stable
HTTPS URL with Connect over one WebSocket (`wss://<url>/connect`,
[connectrpc.md](connectrpc.md#connect-over-one-websocket)), which Modal carries
past its 150 s cap per HTTP request. What each app runs is
`surmap.survey.modal_hosting` (`cm5_command`, `station_command`), tested in CI;
the app files are read with the AST, because CI does not install `modal`.

| App | File | Runs | Resources |
|---|---|---|---|
| `surmap-cm5-sim` | `src/surmap/survey/modal_cm5_app.py` | `cm5_main --slam-backend streaming --rtabmap-native … --region-points --detector none` on port 8080, no calibration dir: the simulator sends cameras and GPS over RPC | 4 CPU, 8 GiB; image builds RTAB-Map 0.23.1 natively (`scripts/build_rtabmap_native.sh`, about 15 min the first time), then `uv sync --no-dev` from `uv.lock` |
| `surmap-station` | `src/surmap/survey/modal_station_app.py` | `station_main --detector sam31-torch` on port 8081, prompt `$SURMAP_STATION_LABEL` (default `object`) | L4 GPU (`SURMAP_MODAL_GPU`), 4 CPU, 16 GiB; checkpoint in Volume `surmap-sam3` with the `huggingface` secret, as `surmap-sam` |

`SURMAP_MODAL_TIMEOUT` (default 86400 s) bounds a container, and so the longest
survey stream; `SURMAP_MODAL_SCALEDOWN_WINDOW` (default 300 s) how long an
idle one stays up.

Create the token secret once per workspace; keep the token out of the repo:

```bash
read -rs SURMAP_SURVEY_TOKEN
uvx modal secret create surmap-survey SURMAP_SURVEY_TOKEN="$SURMAP_SURVEY_TOKEN"
```

Run one ephemerally (it stops with the command) from the repo root, then
verify it with the URL Modal prints:

```bash
SURMAP_MODAL_TIMEOUT=3600 uv run --with modal modal serve src/surmap/survey/modal_cm5_app.py
uv run python scripts/verify_cm5.py wss://<url> --simulated --hold-s 200   # token from $SURMAP_SURVEY_TOKEN
uv run --with modal modal serve src/surmap/survey/modal_station_app.py
uv run python scripts/verify_station.py wss://<url> --expect-device gpu
```

`modal deploy` instead keeps an app up; stop it with
`uvx modal app stop -y <app-id>` (`uvx modal app list` names them). The
`modal-cloud` skill (`.agents/skills/modal-cloud/SKILL.md`) covers workspace
choice, cost guardrails and cleanup.

What Modal's edge does to these servers, and how the code meets it:

- WebSockets only over HTTP/1.1, messages up to 2 MiB, no `permessage-deflate`
  — `SurveyConnection` dials with `compression=None`; bodies go in 256 KiB chunks.
- An HTTP 401 on the upgrade reaches the client as a 500, and close codes
  arrive as 1000 — the servers refuse a missing token inside the socket (the
  text frame `unauthorized`), which `SurveyConnection.open` raises as
  `PermissionError`.
- Endpoint URLs are public — the bearer token guards every Connect call; only
  `/health/is_alive` answers without it.

Verified on 2026-11-03 for the CM5 app only (`modal serve`, workspace
`mantas-27062`): token refusal and acceptance, real RTAB-Map scene points, GPS
anchors and region points over `wss://`, and one survey stream held for 205 s.
The station app has not run on Modal yet.

