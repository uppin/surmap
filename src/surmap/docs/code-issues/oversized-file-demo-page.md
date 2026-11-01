# oversized-file: src/surmap/demo/page.py

**Location:** `src/surmap/demo/page.py` — `PAGE`
**Category:** oversized-file
**Detected:** 2026-10-31 by `/pr-wrap` step 4 (file-length gate; `/analyze-code-issues` not run on `surmap` yet)
**Metrics:** 525 lines (limit 500) · one HTML/CSS/JS template string · not covered by a JS test harness
**Restructure:** required — move script blocks out the way `cloud_script.py` was, `/code-restructuring` territory
**Status:** Open (a record exists only while the issue is open — fixing it deletes the file)

## Measurement history

| Run | Lines | Note |
|---|---|---|
| 2026-10-31 | 526 → 525 | `feat/sam-region-points`: the region listener went into `cloud_script.py` (`listenForRegions`), so this PR did not grow the page |
| 2026-10-31 | 523 → 525 | `feat/demo-sam-prompt`: the stream URL carries the SAM prompt box's value (+2); the prompt form itself is rendered by `demo/sam_prompt.py` |

## What the tool found

The demo page is one `PAGE` format string: markup, styles and ~300 lines of page script, just over
the 500-line limit. Its JavaScript is only syntax-checked by hand (`node --check` on the rendered
page); Python tests assert substrings.

## Why it matters here

Every demo pane adds listeners and drawing code to the same string, and `{{`/`}}` escaping makes
mistakes easy and silent until a browser loads the page.

## What would close it

Move the SAM pane drawing and the history/timeline script into their own modules spliced in like
`CLOUD_SCRIPT` (`__CLOUD_SCRIPT__` marker), leaving `page.py` as markup, styles and wiring.

## Verified by hand

2026-10-31 — `wc -l` at the merge base `c126ded` (526) and at the wrap (525); the rendered page's
scripts pass `node --check`.
