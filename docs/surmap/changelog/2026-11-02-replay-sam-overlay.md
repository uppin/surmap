# Replays show the recorded SAM overlay, and long journals start at once

**Date:** 2026-11-02
**Feature:** Browser demo / run history / journal replay

Browser checks of the recorded KITTI 0009 run (447 frames, real SAM 3.1
masks) found four problems with replaying cached results. All four are
fixed.

- **SAM overlay without SAM.** A console started without SAM rendered
  no SAM pane, so a replay's recorded masks were dropped. `sam_pane` now
  always renders a view: without SAM it is passive and hidden (no
  prompt box), and the first `sam` event reveals it.
- **SAM overlay when rewinding.** A history snapshot carried only
  Coral detections. `RunHistoryStore.snapshot_at` now adds `sam`, the
  newest journalled SAM result at or before that frame, with its image.
  The page draws it while scrubbing.
- **45 s before the first replayed frame.** The player decoded the
  whole journal first; KITTI's holds 243 MB of map clouds.
  `RunHistoryStore.journal_events` streams it 64 rows at a time.
- **1–4 fps at "max".** A slow recording journals one map update per
  frame, and the replay redrew and streamed every one of them. Replays
  now draw the map at most every `MAP_INTERVAL_S` (0.33 s, the live
  cadence), and the newest held-back update is drawn before the end.
- **Viewers stealing runs back.** A stream the server ended (on
  takeover) made the browser's EventSource reconnect, which started a
  new run that took the other viewer's back, and so on. Every stream
  now ends with `event: ended` (`finished` or `taken over`), and the
  page closes its EventSource on it.

Verification: gates green (ruff, format, mypy strict; pytest 1067
passed / 12 skipped); both rendered page scripts pass `node --check`.
On a console without SAM, in the in-app browser, the KITTI run replays
at max speed with its first frame after 2.4 s (was about 45 s), at
7–8.5 fps (was 1–2), with the SAM pane revealed and drawing every SAM
frame through 447. A curl replay of the whole run takes 54.5 s (was
115 s) and streams 138 map views instead of 447. Scrubbing to frame 200
draws that moment's 4 recorded car masks.
