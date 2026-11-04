# Opening the console plays nothing; Replay cached run is explicit

**Date:** 2026-11-04
**Feature:** Browser demo / run history / journal replay

Opening the test console reran the scene's cached recording at once.
That rerun took the console's one playback slot, so reloading the page
during a Rebuild cancelled the live build, which was then stored as
`interrupted` and never cached. Now:

- **Opening a scene plays nothing.** `startDefault` only offers the
  scene's cached run (`offerCached`). The page says a recording is
  ready and waits.
- **Replay cached run** sits next to Rebuild and stays disabled until a
  cached run is offered. It reruns that run as before
  (`/stream?replay=<id>&speed=1&record=0`), persisting nothing.
- **Rebuild** is unchanged. It is still the only action that runs
  RTAB-Map (and SAM) and records a run, so a page reload no longer
  interrupts it.
