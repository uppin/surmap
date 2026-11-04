# The survey agent runs SAM on an on-demand GPU station

**Date:** 2026-11-04
**Feature:** Survey agent / SAM station; Chat UI header

- **Interface.** `StationControl` (`surmap.agent.tools.station`): `status`, `start`, `stop`,
  `check_idle`, `detector`. `StubStationControl` (in process, fake SAM) and
  `ModalStationControl` (`station_modal`, the deployed `surmap-station` app through the `modal`
  SDK's `Function` API behind a `ModalFunction` protocol) both satisfy it; one contract suite
  runs against both.
- **Lifecycle.** The workspace's SAM (`StationSamDetector`) starts the station on its first frame;
  the agent stops it `--station-idle-s` (300) after the last frame (`IdleTicker`), on
  `stop_station`, or when the process stops. On Modal the state comes from function stats only —
  a status read never boots or holds a GPU; start is a health GET until 200; stop closes the
  agent's link and scales idle containers down within 2 s.
- **Tools.** `get_station_status` (SYNC · 10 s · FAIL), `start_station` and `stop_station`
  (SYNC · 30 s · DETACH) — `StationTools`, mounted only with `--station`.
- **Process.** `--station modal|stub`, `--station-app`, `--station-env`, `--station-idle-s`,
  `--station-prompt`; `--sam-fake` is no longer the only SAM. Optional extra `modal`.
- **Chat UI.** `SAM · <state>` with **Start SAM** / **Stop SAM** in the header, polled every 5 s,
  hidden without a station.
- **Verified** live on Modal (`ginas-bb`, 2026-11-04): first-frame start with detections, stop,
  start, idle-out; the header's off → starting → ready → stopping → off.
- **Tests.** `tests/test_agent_station.py` (21: 10 contract tests × both implementations, plus the idle ticker), `test_agent_station_modal.py`
  (11), `test_agent_station_tools.py` (7), six config tests in `test_agent_server_app.py`;
  `StationIndicator.test.tsx` (8), four `App.test.tsx` tests, two Playwright tests.

Docs: [docs/agent.md](../../agent.md) (*SAM station*, *Running the agent*, *Chat UI*),
[docs/modal.md](../../modal.md) §5.
