# oversized-file: proto/surmap/agent/v1/simulation_tools.proto

**Location:** `proto/surmap/agent/v1/simulation_tools.proto`
**Category:** oversized-file
**Detected:** 2026-11-04 by `/pr-wrap` step 4 (file-length gate)
**Metrics:** 499 → 521 lines (limit 500)
**Restructure:** required — left for the `#drone-fleet` sweep node (stack-shared file)
**Status:** Open (a record exists only while the issue is open — fixing it deletes the file)

## Measurement history

| Run | Lines | Note |
|---|---|---|
| 2026-11-04 | 499 → 513 | `pr-1-drone-fleet` (#116): `DroneNestElement` and `AddElementRequest.drone_nest = 8`; left for the #drone-fleet sweep node — later stack PRs edit this file too, so splitting it here would conflict every node above |
| 2026-11-04 | 513 → 521 | simulation export/import: only the `DescribeScenario` rpc and its import line; its messages went to the new `simulation_contents.proto`, the first step of the split |

## What would close it

Move the element messages into their own `simulation_elements.proto` imported by `simulation_tools.proto`, then regenerate with `scripts/gen_agent_rpc.py`.
