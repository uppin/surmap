---
description: Logging standards for SurMap
---

# Logging

- Use the standard-library `logging` module via a module-level logger
  (`logging.getLogger(__name__)`); never `print` in library code.
- Namespaces follow the package tree (`surmap.slam`, `surmap.geometry`, …)
  so operators can raise one subsystem's level without the rest.
- Levels: `DEBUG` for per-frame/per-point detail (off by default — it must
  be cheap when disabled), `INFO` for lifecycle events (session start/stop,
  backend loaded), `WARNING` for recoverable degradation, `ERROR` for
  failures that end a session or drop data.
- Log structured context (session id, frame/track ids, GPS fix) in the
  message arguments, not string-built blobs; never log credentials or raw
  model-API keys.
- A failure that a user must act on also raises a named exception with
  install/next-step guidance — the log line is not the error surface.
