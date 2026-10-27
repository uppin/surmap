# Station SAM analysis policy

**Date:** 2026-10-27
**Feature:** Survey data APIs

Added the station's SAM seam: a `SamDetector` port (SAM 3.1 arrives
behind it), domain frame/detection contracts, an in-memory detector
for tests and simulation, and the admission gate that enforces the
requester's choice — analyze every frame and accept the lag, or
analyze only when the detector is free and count the drops.
