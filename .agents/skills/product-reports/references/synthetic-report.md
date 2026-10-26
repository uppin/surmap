# A synthetic Product report, for dry runs

Invented for testing the three skills: no user wrote it, the Slack `ts` is made up, and so are the
extension SHA and the delivery `request` id. Its `run`, `step` and `step_number` are those of a real
failed weave on 2026-10-13, so the investigation finds real lines until app-logs ages them out on
about 2026-11-12 (30-day retention). After that, swap in the ids of a recent failure:

```sql
SELECT timestamp, request_id, JSONExtractString(data, 'runId') AS run,
       JSONExtractInt(data, 'step') AS step, JSONExtractString(data, 'errorKind') AS error_kind
FROM app_logs
WHERE $__timeFilter(timestamp) AND artifact_id = 'surmap.base_station.session_ingest'
  AND message LIKE 'step %' AND JSONHas(data, 'ok') AND NOT JSONExtractBool(data, 'ok')
ORDER BY timestamp DESC LIMIT 10
```

Run it with `/product-reports dry-run .agents/skills/product-reports/references/synthetic-report.md`.

## The message, as the channel would show it

Slack `ts` `1791901200.000100` (synthetic) · posted by the Product reports app. The shape is
`formatReport`'s (`product/product-server/src/reports/format.ts`) for an automatic report.

~~~~text
*Product failure (automatic report)*
extension · 0.1 (0000000000000000000000000000000000000000)
when · 2026-10-13T14:09:43.872Z
operation · build
failure · refusedForGood
detail · Product couldn’t get the table right after several tries. Try again, or ask for a simpler table.
run · d8b816c6-8b09-4707-9a85-b522aae8e146
step · 1791900571.108521608511463
step_number · 9
request · 1791901199.000000000000001
~~~~

No `account` line: the build that served this run (`1.117.0`) predates `account_key`. A dry run
should notice three things rather than treat them as failures:

- the all-zero SHA names no commit, so the client version is unresolvable;
- `request` matches no `report …` delivery line, as a synthetic delivery id should;
- `refusedForGood` is a server code, so the server's `ERROR` row for step 9 is where the cause is.
