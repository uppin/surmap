# Initial Discovery: Meta Model API SAM 3.1

**Changeset**: [2026-10-28-meta-model-api-sam.md](./2026-10-28-meta-model-api-sam.md)
**Date**: 2026-10-28
**Passes**: 1

## Combined Conclusions

SAM on main is a port (`SamDetector` / `SamDetection` in
`surmap.survey.sam`) plus an ONNX adapter (`surmap.survey.sam3`).
There is no HTTP client and no `usage.py`. The outline helper
`_mask_outline` is private to `sam3.py`. `HACKATHON.md` is not on
`main` (it is added by PR 28). README is not the place for this
runbook. The hosted adapter is a new module, `meta_sam.py`, that
implements `SamDetector`, reuses a public `mask_outline`, and keeps
the JSON envelope in one function because a live `sam-3.1` body was
not captured. Mask decoding uses the documented `meta-sam-parser`
package. The model id defaults to `sam-3.1` and rejects `wonder`.

## Exploration 1: SAM seam and Meta docs — 2026-10-28

**Agent**: parent Grep/Glob/Read
**Scope**: station SAM port, hackathon doc, Meta Model API docs

### Sequence

1. `gh api` comment 6479196233 — the follow-up task text.
2. Glob `src/surmap/**/*.py` and Grep `sam|SAM|detector` — locate the port.
3. Read `src/surmap/survey/sam.py` and `sam3.py` — `SamDetection`, private outline.
4. Read `tests/test_sam3.py` — existing green suite to leave intact.
5. Glob `HACKATHON.md` — absent. `gh api` contents on `main` — 404.
   `gh pr view 28` — file lives on `cursor/readme-meta-models-24f9`.
6. Web search and fetch of `dev.meta.ai` SAM overview, segmenting,
   reading-segmentation, Responses, and `meta-sam-parser` 0.1.0.
7. Read `pyproject.toml` — no HTTP library; dependencies are uv-managed.
8. Grep `usage.py` / `on_usage` — not on main.

### Grep / glob

| Tool | Pattern / glob | Path scope | Notable hits |
|------|----------------|------------|--------------|
| Glob | `src/surmap/**/*.py` | `/workspace` | `survey/sam.py`, `survey/sam3.py` |
| Grep | `_mask_outline` | `src` | only `sam3.py` |
| Glob | `**/HACKATHON.md` | `/workspace` | none |
| Grep | `on_usage` | repo | none |

### Inspected files

#### `src/surmap/survey/sam.py`

**Why**: the port the new adapter must implement.
**Excerpt**:

```python
class SamDetector(Protocol):
    async def detect(self, frame: RawFrame) -> tuple[SamDetection, ...]: ...
```

`SamDetection` is label, score, `box_xyxy`, `mask_polygon`, optional `track_id`.

#### `src/surmap/survey/sam3.py`

**Why**: the outline helper the task says to reuse.
**Excerpt**: `_mask_outline` walks mask rows and returns a polygon in scaled pixels, used only by `Sam3Detector`.

### Findings

- `Sam3Detector.box_xyxy` is half-open (exclusive max). The Meta parser
  also emits half-open boxes (inclusive wire max plus one).
- The published 5×5 one_bit payload `!!!!!(QO(0lu8?` decodes to a
  non-empty raster, so a fake response can demand a real polygon.
- Text Responses JSON is `output[].content[].type == output_text` and
  `usage.{input_tokens,output_tokens}`. SAM docs put the grammar in
  that text lane. The non-streaming SAM JSON was not seen live.
