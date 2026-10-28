# Baseten Muse Spark Open label client

**Date:** 2026-10-28
**Type:** Feature
**Packages:** surmap

Added the labelling port and the Baseten Muse Spark Open adapter.
`LabelClient.label_object` takes a JPEG crop, a coarse detector
label, and a map-frame position, and returns a frozen `ObjectLabel`
(`label`, `description`, `confidence`, `model_id`, `raw_text`).
`confidence` is `None` when the assistant text has no number.
`BasetenMuseLabelClient` is the HTTP adapter. `InMemoryLabelClient`
returns a recorded label and never opens a socket. No new dependency:
the HTTP call uses the stdlib, and tests inject a transport.

Verification executed 2026-10-28. `tests/test_labelling_baseten_muse.py`
is 12 passed and 1 skipped (`test_live_baseten_labels_a_jpeg_crop`,
which runs only when `SURMAP_LIVE_BASETEN=1` and `BASETEN_API_KEY`
are both set). `uv run ruff check src tests` passed. `uv run ruff
format --check src tests` reported 153 files already formatted.
`uv run mypy` reported no issues in 133 source files. `uv run pytest -q`
reported 480 passed, 6 skipped.
