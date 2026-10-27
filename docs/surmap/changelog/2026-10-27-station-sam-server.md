# Station SAM server

**Date:** 2026-10-27
**Feature:** Survey data APIs

Exposed the base station as a ConnectRPC bidirectional server with
the CM5's frame input: SAM detection vectors out, keyed by the
frame_id the requester assigned. The requester picks per stream
whether every frame is analyzed (lag accepted) or frames drop while
the detector is busy (counted, reconciled by missing frame_ids).
