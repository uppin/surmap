# Credit usage and Baseten labels

Civilian disaster-response survey. SurMap maps an area a team already
flew; it does not fly the aircraft and it does not task it. Design of
the pipeline is [architecture.md](architecture.md). This note is the
credit runbook: which hosted model the labelling client calls, how to
turn a live call on, and how spend is recorded.

## Credits

| Source | Job | Id | Status |
|---|---|---|---|
| [Meta Model API](https://dev.meta.ai/docs/models) | Scene note over the mapped area. SAM 3.1 boxes and masks | Hosted Muse Spark `muse-spark-1.3`. SAM `sam-3.1` | Planned |
| [Baseten Model APIs](https://docs.baseten.co/inference/model-apis/overview) | Per-object semantic labels from a JPEG crop | `meta-models/muse-spark-open-1026` at `https://inference.baseten.co/v1` | client in tree; live call gated |
| Modal | GPU for station-side SAM 3.1 behind the in-tree ONNX adapter | No Modal app in this repo | Planned |

Muse Spark Open is not on Meta Model API. Baseten hosts it here.
Hosted Muse Spark (`muse-spark-1.3`) is still the planned model for a
scene note and is not called from this tree. Modal is not called.
The geometric pipeline (stereo, Coral detection, RTAB-Map, the demo)
does not use these credits.

## Baseten Muse Spark Open labels

`surmap.labelling.BasetenMuseLabelClient` posts one chat completion:

`POST https://inference.baseten.co/v1/chat/completions`

| Item | Value |
|---|---|
| Model | `meta-models/muse-spark-open-1026` |
| Key | `BASETEN_API_KEY`, sent only as `Authorization: Bearer`. A missing or blank key raises `BasetenApiKeyMissing` before any socket |
| Input | JPEG crop as an `image_url` data URL, plus the detector's coarse label. The map-frame point is not sent; it is attached to `ObjectLabel.map_point` after the reply |
| Output | `ObjectLabel`: `label`, `description`, `confidence` (`None` when the assistant text has no number), `model_id`, `raw_text` |
| Prompt | Humanitarian search-and-rescue inventory for emergency responders after a natural disaster. Asks only for a short object label, one description sentence, and a confidence |
| Reasoning | `reasoning_effort` defaults to `low` because labels are per object and frequent. Allowed values are `low`, `medium`, and `high`. The client does not send a flag that claims reasoning is off, and it does not use JSON mode. `choices[0].message.reasoning_content` is kept on `reasoning_text` and is not copied into `raw_text` or used as the label |
| Cap | `max_tokens` defaults to `4096`. A value below `2048` is rejected: a trivial prompt can spend about 2200 reasoning tokens before any label text. If `finish_reason` is `length` and the answer text is empty, the client retries once at double the cap, then raises `EmptyLabelError` with `finish_reason` and token counts. An empty label is never returned |

A constructor argument wins. When the argument is omitted, the client
reads the environment, then uses the default:

| Variable | Values | Default |
|---|---|---|
| `SURMAP_BASETEN_REASONING_EFFORT` | `low`, `medium`, or `high` | `low` |
| `SURMAP_BASETEN_MAX_TOKENS` | integer `>= 2048` | `4096` |

Anything else raises `ValueError` when the client is built, before a
request is sent.

When `ledger` is omitted, the client uses a `UsageLedger()` so the call
is appended to `~/.surmap/usage.jsonl` (or `SURMAP_USAGE_LOG`). Pass a
ledger to write somewhere else or to enforce a budget.

`label:` in the assistant text is the label. With no such line, the
first non-empty line is the label. A `confidence:` line wins over a
number that appears inside the label.

The station server does not call the client. Tests use a fake
transport. Nothing in the default suite opens a socket. A live call
runs only when both of these are set:

```bash
export BASETEN_API_KEY='...'   # single quotes; never commit this
export SURMAP_LIVE_BASETEN=1
uv run pytest tests/test_labelling_baseten_muse.py -q
```

The repository is public. Do not commit a key, a `.env` that holds
one, or a usage log copied from a machine that has one.

## Credit usage and limits

Shared ledger for every hosted call. Other agents pass an instance and
use it as a callback; the method names below are the interface.

```python
@dataclass(frozen=True)
class UsageRecord:
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int | None
    t_unix: float

UsageSink = Callable[[UsageRecord], None]
```

`UsageLedger` is a `UsageSink`. Calling it appends one JSON object per
line. The default file is `~/.surmap/usage.jsonl`. Set
`SURMAP_USAGE_LOG` to move it. The process also keeps per-provider
totals in memory (they reset when the process exits; the file does
not). Token totals are `input_tokens + output_tokens`. Reasoning
tokens are stored on the record and are not added again, because they
are already inside `output_tokens` (`completion_tokens` on the Baseten
response; `completion_tokens_details.reasoning_tokens` is the reasoning
subset).

`ledger.check(provider)` raises `BudgetExceeded` before a request is
sent when that provider is already at its budget. Unset means no
limit. Names are upper-cased: `BASETEN`, `META`, `MODAL`.

| Variable | Meaning |
|---|---|
| `SURMAP_BUDGET_BASETEN_CALLS` | Max Baseten calls in this process |
| `SURMAP_BUDGET_BASETEN_TOKENS` | Max Baseten input + output tokens in this process |
| `SURMAP_BUDGET_META_CALLS` / `SURMAP_BUDGET_META_TOKENS` | Same, for Meta |
| `SURMAP_BUDGET_MODAL_CALLS` / `SURMAP_BUDGET_MODAL_TOKENS` | Same, for Modal |

`BasetenMuseLabelClient` takes `ledger: UsageLedger | None`. Omitted,
it builds a `UsageLedger()` aimed at the default log. It calls
`ledger.check("baseten")` before each HTTP request, including the
one retry after a length cutoff, and records a `UsageRecord` after
each response.

```bash
uv run python scripts/usage_report.py
uv run python scripts/usage_report.py --log ~/.surmap/usage.jsonl
```

The report prints one summed row per UTC day, provider, and model.
