# Initial discovery — Baseten Muse Spark Open labels

## Combined conclusions

- `main` has no labelling package, no Baseten client, and no credit ledger.
  `HACKATHON.md` is not on `main` (it is introduced on open PR #28). This
  change adds that file with the Baseten row already at "client in tree;
  live call gated" and a credit-usage subsection. README is not edited.
- Semantic labelling is still an open decision in `docs/architecture.md`
  §3.2 ("newest Meta Llama"). The in-tree client is the decision for
  per-object labels: Baseten chat completions,
  `meta-models/muse-spark-open-1026`. The station server does not call it.
- HTTP in this repo is stdlib `urllib` (`surmap.demo.datasets`). No new
  dependency. Tests inject a transport; nothing in the default suite
  opens a socket.
- The verified response shape is OpenAI `chat.completion`: the label is
  `choices[0].message.content`, reasoning is `reasoning_content` (not the
  label), and usage carries `prompt_tokens`, `completion_tokens`,
  `total_tokens`, and `completion_tokens_details.reasoning_tokens`.
- Other agents will call the ledger as a plain callback. The public
  names are fixed: `UsageRecord`, `UsageSink`, `UsageLedger`,
  `BudgetExceeded`, `check(provider)`, env `SURMAP_USAGE_LOG` and
  `SURMAP_BUDGET_<PROVIDER>_{CALLS,TOKENS}`.

## Exploration 1

Sequence: `gh` comment `6479193887` and PR #28; `git ls-tree origin/main`;
grep for Baseten, HACKATHON, labelling, `json.loads`, `urllib`, PIL;
read `pyproject.toml`, `src/surmap/types.py` (`Vec3`), `slam/base.py`,
`slam/rtabmap.py`, `detection/__init__.py`, `docs/architecture.md` §3.2
and §12, `HACKATHON.md` from `cursor/readme-meta-models-24f9`, fluent
pytest notes, Baseten chat-completions docs.

Findings that set the design:

- JPEG crop, coarse label, and map-frame `Vec3` go in; frozen
  `ObjectLabel` comes out. `label:` is parsed when present, otherwise
  the first non-empty line. `confidence` is `None` when the assistant
  text has no number. A `confidence:` line wins over a number inside
  the label (a "4x4" must not become confidence 4).
- Missing `BASETEN_API_KEY` raises a typed error before the transport.
  Default `reasoning_effort` is `low`. `max_tokens` defaults to 1024.
  The client does not send JSON mode or a flag that claims reasoning
  is off (`none` / `minimal` are rejected).
- `UsageLedger` appends one JSON object per line, keeps process-local
  per-provider totals, and `check` raises `BudgetExceeded` before the
  fake transport is invoked. Token totals are input + output.
  Reasoning tokens are stored and not added again.
- Live coverage is `pytest.mark.skipif` on `SURMAP_LIVE_BASETEN=1` and
  a non-empty key. Collection does not open a socket.
