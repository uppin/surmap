# Survey RPC over WebSocket, hosted on Modal

**Date:** 2026-11-03
**Type:** Feature
**Packages:** surmap

`ServerDescription.connect_websocket_path` makes `HypercornHost` serve every composed Connect
service over one WebSocket (`surmap.rpc.socket_rpc.connect_websocket_app`, one acceptor peer per
socket). The server greets each socket with an empty frame and sends one every 20 s as a
keepalive. `auth_token` guards Connect over HTTP (401) and the upgrade. A tokenless socket is
told `unauthorized` and closed with 4401, inside the socket, because Modal's edge rewrites both
the HTTP status and close codes. `peer.py` split into the serving half, `_calls.py` (calling
half) and `_types.py` (870 → 396 / 453 / 83 lines). Streamed replies are forwarded and
forgotten: a 100 MiB bidi stream peaked at 401 MiB before and stays under 32 MiB now.

`surmap.survey.ws_client.SurveyConnection` (asyncio, `compression=None`) carries capabilities,
survey, detections, region points and analysis over one socket. `surmap.demo.remote` runs each
adapter's connection on its own event-loop thread (`_Link`). `scripts/verify_cm5.py` and
`scripts/verify_station.py` take `host:port` or `ws(s)://` / `http(s)://` URLs and `--token`;
`scripts/verify_cm5_simulated.py` is the new `--simulated [--hold-s S]` mode.

The survey proto gained `GpsFix` (`Cm5Request.gps`) and `GpsAnchorOut`
(`Cm5Response.gps_anchor`). `surmap.survey.gps` holds `PoseTimeline` and `PendingFixes`: a fix is
answered once a pose at or after it lands, or when the stream ends. `_stream_survey` drains
odometry, keyframes and pending fixes every 0.1 s while the sender is idle. `cm5_main.describe`
builds the description; streaming without `--calibration-dir` takes each stream's cameras, and
`StreamRegionRouter` answers region queries from the open streams' backends. `cm5_server.py`
split: `cm5_service.py` holds `StreamDetections`, `StreamRegionPoints` and `cm5_service_module`
(662 → 439 / 242 lines).

Modal: `modal_cm5_app.py` and `modal_station_app.py`, with what they run in the typed
`surmap.survey.modal_hosting`. Both join `modal_sam_app` in the mypy `ignore_errors` override,
because CI does not install `modal`. `scripts/build_rtabmap_native.sh` runs as root without
`sudo`.

Verification: V1 fail→pass. 31 acceptance tests were red at the Red commit and are green; the
Modal run found 3 more issues, each fixed test-first. V4 on Modal (CM5 only, workspace
`mantas-27062`, approved by the developer): health, token refusal, survey with real RTAB-Map, GPS
26/40 anchored unpaced and 40/40 paced, regions 26 531 points, and a 205 s stream; spend $0.07.
⚠️ The station app has not run on Modal. Gates: ruff, ruff format, strict mypy and pytest green,
1844 passed and 10 skipped before the wrap's splits. The one intermittent failure seen during
green, `test_survey_cm5_rtabmap_e2e`, also fails on untouched main.
