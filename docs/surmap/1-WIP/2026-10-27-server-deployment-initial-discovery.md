# Initial Discovery — server deployment (n6)

## Combined Conclusions

- Whole-work pass reused (see Exploration 1 in the n1–n5 companions):
  the ConnectRPC kit hosts a `ServerDescription` over real sockets with
  `HypercornHost(description, context, host, port)` (`start()` →
  `BoundPorts`, `stop()`), and `health_routes` provides
  `/health/is_alive`.
- n4/n5 (green, on this stack) expose `cm5_service_module()` and
  `station_service_module()` factories with in-memory default adapters
  (`InMemorySlamBackend`, `InMemoryObjectPointSource`,
  `InMemorySamDetector`). There is no executable entrypoint, no `main`,
  no systemd unit, and no deployment script anywhere in the repo.
  Hardware adapters (RTAB-Map binding, Coral tracker, SAM 3.1) do not
  exist yet, so a deployed service today serves with the in-memory
  adapters — that limitation must be stated wherever deployment is
  described.
- Deferred-work scan: `src/surmap/docs/{todo,code-issues,deferred-answers}/`
  still do not exist; no record names this layer. Nothing in
  `## Prerequisites`.
- Machine addressing is by CLI argument per the developer: each deploy
  script takes the local source path and the SSH target as arguments.
  No hostname, user, or install path is committed.

## Exploration 1 — deployment pass (2026-10-27)

Read the greened `cm5_server.py` / `station_server.py` module factories
on `pr-5-station-sam-server`, `HypercornHost` (`start`/`stop`,
management port split), `health_routes`, and the hypercorn host test;
listed `scripts/` (only proto generators); grepped the repo for
`systemd|ssh|deploy|.service` outside `.agents/` (no hits).
