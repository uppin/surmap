# Demo page on remote CM5/Station hosts, respecting their features

The demo page can run against the deployed survey servers instead
of its in-process pipelines (`scripts/demo.py --cm5-host/--station-host`,
deployed on the Station host by `scripts/deploy-demo.sh`; the Radxa
CM5 at 10.88.77.14 fills the CM5 role). Both survey services gained
a unary `GetCapabilities`; at startup the demo asks each host what
it was built with and renders only that: a CM5 without a detector
contributes the RTAB-Map panes with no Coral overlay, a host that
does not answer contributes no panes, and the Station's SAM pane is
labelled with its provider/device (`GPU · SAM 3.1 (PyTorch) · cuda:0`).

The wire grew to carry what the page needs from a remote CM5:
per-frame odometry (pose, tracked keypoints, rectification — the
video overlay), new-keyframe points for the cloud and floor plan
(vectorized, capped like the local backend), and the stream's own
`cam0_yaml`/`cam1_yaml` + `max_depth_m`, from which the CM5 builds
a fresh RTAB-Map backend per stream and closes it with the stream.
A shared backend cannot leak a previous stream's map or odometry
into the next (snapshot priming + timestamp guard). Playback itself
moved server-side: a run engine on the Station exchanges frames
with the CM5 regardless of browsers, records history, and
publishes; `/stream` only subscribes and renders, dropping
intermediates for slow clients. Map events carry `rtab_fps`
(posed frames/s over a 10 s window).

Follow-ups fixed on the way: the survey handler no longer
re-scans the whole map per pair (it was the CM5-side bottleneck;
KITTI now runs ~4–6 RTAB fps, RTAB-bound); `StreamAnalysis`
honours the stream's concept prompt (`Sam31TorchDetector.set_prompt`)
instead of the server's build-time label; SAM mask polygons are
built correctly from the vendor's channel-first binary masks,
scaled onto the frame; a run takeover can no longer join an
unstarted engine thread; the demo's dataset cache and history
live in a systemd `StateDirectory` so redeploys cannot wipe them.

Verification: gates green (ruff, format, mypy strict, 780 passed /
3 skipped). Live: Radxa capabilities `cm5/streaming` (detections
off), Station `sam_analysis` on `cuda:0`; the KITTI page stream
shows keypoint overlays on ~all frames, a cloud growing past
150k points with a 205-pose trajectory over ~190 m, SAM events
with tracked `car` objects (187/187 in one capture) whose mask
polygons sit inside their boxes, and a run that kept progressing
server-side (timeline 66 → 91 → 109) after its viewer disconnected.
