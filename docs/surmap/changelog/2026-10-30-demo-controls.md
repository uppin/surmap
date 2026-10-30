# Demo scene picker and playback controls

**Date:** 2026-10-30
**Feature:** browser demo

The launcher downloads nothing at start. Every registered scene is in
the page's picker; a scene not yet cached is prepared in the background
on first pick (`POST /prepare`) and the page shows its progress — bytes
downloaded, checksum, frames extracted — from `GET /datasets`, then
plays. Later picks and launches are cache hits.

Pause/Resume (`POST /control`) stops feeding SLAM and showing frames
while held frames keep resolving; Restart replays from the start. A new
viewer takes the stream over — the running player is cancelled and its
sidecar torn down — instead of being refused with 409 (which the page
had shown as "Stream unavailable — is another viewer connected?").

Verification: gates green (pytest 565 passed, 2 skipped). Pause/resume
answered `paused` / `playing` on a live KITTI stream; a first pick of
KITTI (zip cached) went missing → preparing (verifying) → ready and its
page served.
