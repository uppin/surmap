# oversized-file: src/surmap/demo/remote.py

**Location:** `src/surmap/demo/remote.py` — whole file
**Category:** oversized-file
**Detected:** 2026-11-03 by `/pr-wrap` step 4 (file-length gate; `/analyze-code-issues` not run on `surmap` yet)
**Metrics:** 555 lines (2026-11-03; was 607 at this PR's merge base) (limit 500) · coverage not measured
**Restructure:** required — split into focused modules, `/code-restructuring` territory
**Status:** Open (a record exists only while the issue is open — fixing it deletes the file)

## Measurement history

| Run | Lines | Note |
|---|---|---|
| 2026-11-03 | 607 → 555 | survey RPC over WebSocket PR (#97): the h2c and `http.client` transports were replaced by `_Link` over `SurveyConnection`. The file was already over the limit at the base and this PR shrank it, so the gate only alerts; the split is not this PR's |

## What the tool found

A 555-line module holding four adapters behind the demo's seams (`RemoteCm5Backend`,
`RemoteDetectionSource`, `RemoteSamDetector`, `fetch_capabilities`) plus the `_Link`
event-loop bridge they share. Coverage was not measured; "not measured" is not "clean".

## Why it matters here

Each adapter changes for its own server: survey output for the CM5, analysis for the station.
In one file, a change to one adapter is reviewed next to the other three.

## What would close it

A mechanical split at the seams already in the file: `demo/remote_link.py` (`_Link`,
`fetch_capabilities`), `demo/remote_cm5.py` (`RemoteCm5Backend`, `RemoteDetectionSource`) and
`demo/remote_station.py` (`RemoteSamDetector`, `_iou`), with `demo/remote.py` re-exporting the
public names so `demo/server.py` and the tests keep their imports. Same green before and after.

## Verified by hand

2026-11-03 — `wc -l` at the merge base (607) and at the wrap (555); the seams above were read
from the file's class and function list. No analyzer ran, so complexity and coverage are unknown.
