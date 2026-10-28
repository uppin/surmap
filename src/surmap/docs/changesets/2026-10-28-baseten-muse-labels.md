# Baseten Muse Spark Open labels

**Date:** 2026-10-28
**Type:** Feature
**Packages:** surmap

Added `BasetenMuseLabelClient` and `UsageLedger`. The client posts a
chat completion only after `ledger.check("baseten")` when a ledger is
attached, and appends one usage record after the response. Reasoning
text stays off `ObjectLabel.raw_text`.
