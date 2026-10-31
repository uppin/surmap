"""Demo page HTML (see server.py for the SSE contract)."""

from __future__ import annotations

from surmap.demo.cloud_script import CLOUD_SCRIPT

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>SurMap Test Console — {title}</title>
<style>
  body {{ margin: 0; background: #17191c; color: #e8eaed;
    font-family: "Segoe UI", system-ui, sans-serif; }}
  header {{ padding: 20px 28px 8px; }}
  h1 {{ font-size: 22px; margin: 0 0 4px; font-weight: 650; }}
  .sub {{ color: #9aa3ad; font-size: 13px; margin: 0; max-width: 900px; line-height: 1.5; }}
  main {{ display: flex; gap: 20px; padding: 16px 28px 28px;
    flex-wrap: wrap; align-items: flex-start; }}
  .stage {{ flex: 1 1 620px; max-width: 880px; min-width: 320px; }}
  canvas#view {{ width: 100%; background: #000; border: 1px solid #34383e; display: block; }}
  .sam-pane {{ margin-top: 18px; }}
  .sam-pane h2 {{ font-size: 14px; margin: 0 0 6px; font-weight: 650; }}
  canvas#sam-view {{ width: 100%; background: #000; border: 1px solid #34383e; display: block; }}
  aside {{ flex: 1 1 380px; min-width: 320px; max-width: 760px; }}
  h2 {{ font-size: 14px; margin: 18px 0 6px; font-weight: 650; }}
  h2:first-child {{ margin-top: 2px; }}
  .stat {{ font-size: 13px; color: #c3c9d1; line-height: 1.7; }}
  .stat b {{ color: #fff; font-weight: 650; }}
  canvas#map {{ background: #101215; border: 1px solid #34383e;
    width: 100%; display: block; }}
  .legend {{ font-size: 12px; color: #9aa3ad; line-height: 1.5; }}
  .dot {{ display: inline-block; width: 9px; height: 9px;
    border-radius: 50%; vertical-align: -1px; }}
  .controls {{ display: flex; gap: 8px; align-items: center; margin-top: 12px;
    flex-wrap: wrap; font-size: 13px; }}
  .controls select, .controls button, .btn {{ background: #24272c; color: #e8eaed;
    border: 1px solid #3b4047; border-radius: 6px; padding: 5px 10px; font: inherit; }}
  .controls button:disabled, .btn:disabled {{ opacity: 0.45; }}
  .btn {{ cursor: pointer; font-size: 13px; }}
  .btn.active {{ border-color: #2fd4c4; color: #2fd4c4; }}
  .progress {{ display: flex; gap: 10px; align-items: center; margin-top: 10px;
    font-size: 13px; color: #c3c9d1; }}
  .progress[hidden] {{ display: none; }}
  .bar {{ width: 320px; max-width: 60vw; height: 8px; background: #24272c;
    border-radius: 4px; overflow: hidden; }}
  .bar > div {{ height: 100%; width: 0; background: #2fd4c4; transition: width 0.3s; }}
  .history {{ margin-top: 14px; border: 1px solid #34383e; border-radius: 8px;
    padding: 10px 12px; background: #1d2024; }}
  .history-row {{ display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }}
  .history-row input[type="range"] {{ flex: 1 1 220px; accent-color: #2fd4c4; }}
  .history-label {{ font-size: 12px; color: #9aa3ad; margin-top: 6px; }}
  .history-label b {{ color: #e8eaed; }}
  .cloud-pane {{ border: 1px solid #34383e; border-radius: 8px; background: #1d2024;
    padding: 10px 12px 12px; margin-top: 4px; }}
  .cloud-pane:fullscreen {{ background: #101215; padding: 16px; overflow: auto; }}
  .cloud-head {{ display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }}
  .cloud-head h2 {{ margin: 0; flex: 1; }}
  .cloud-wrap {{ resize: both; overflow: hidden; width: 100%; height: 340px;
    min-width: 260px; min-height: 200px; max-width: 100%; border: 1px solid #34383e;
    background: #0b0d0f; position: relative; margin-top: 8px; }}
  .cloud-pane:fullscreen .cloud-wrap {{ height: calc(100vh - 170px); resize: none; }}
  canvas#cloud {{ width: 100%; height: 100%; display: block; touch-action: none; cursor: grab; }}
  canvas#cloud:active {{ cursor: grabbing; }}
  .ptz {{ display: flex; gap: 6px; align-items: center; flex-wrap: wrap; margin-top: 8px;
    font-size: 12px; color: #9aa3ad; }}
  .ptz .btn {{ padding: 4px 8px; }}
  .resize-hint {{ font-size: 11px; color: #7c8590; margin-top: 4px; }}
</style>
</head>
<body>
<header>
  <h1>SurMap Test Console — {title}</h1>
  <p class="sub">Generic testing page for the survey pipeline. Pick any registered
  scene and run it: the video, tracked points, detections and point cloud build live,
  every run is persisted to a SQLite database, and the timeline below can be rewound
  and wound forward — each moment shows the frame, overlay points and point cloud
  as they were at that point in the run. {description}</p>
  <div class="controls">
    <label for="scene">Scene</label>
    <select id="scene"></select>
    <button id="pause" disabled>Pause</button>
    <button id="restart">Restart</button>
  </div>
  <div class="controls">
    <label for="run-select">Persisted run</label>
    <select id="run-select"><option value="">Current / latest run</option></select>
    <button class="btn" id="run-load" type="button">Load run</button>
    <span class="stat" id="run-info">Run: not started · persisted frames: 0</span>
  </div>
  <div class="progress" id="progress" hidden>
    <div class="bar"><div id="bar-fill"></div></div>
    <span id="progress-text"></span>
  </div>
</header>
<main>
  <div class="stage">
    <canvas id="view" width="{width}" height="{height}"></canvas>
    <p class="legend">
      <span class="dot" style="background:{near}"></span> near ({near_label}) &nbsp;
      <span class="dot" style="background:{mid}"></span> {mid_label} &nbsp;
      <span class="dot" style="background:{far}"></span> far ({far_label})
      &nbsp;— features tracked in this frame, coloured and sized by depth.
      Yellow boxes: tracked objects from the separate detections stream.{sam_legend}
    </p>
    <p class="legend">{credit}</p>
    {sam_pane}
    <div class="history">
      <div class="history-row">
        <button class="btn" id="history-back10" type="button" title="Back 10 frames">⏪ 10</button>
        <button class="btn" id="history-back" type="button"
          title="Back one frame">◀</button>
        <input type="range" id="history-slider" min="0" max="0" step="1" value="0">
        <button class="btn" id="history-forward" type="button"
          title="Forward one frame">▶</button>
        <button class="btn" id="history-forward10" type="button"
          title="Forward 10 frames">10 ⏩</button>
        <button class="btn active" id="history-live" type="button">● Live</button>
      </div>
      <div class="history-label" id="history-label">History: no frames yet —
        play a scene, then scrub.</div>
    </div>
    <h2>Playback</h2>
    <div class="stat" id="playback">Connecting…</div>
    <h2>RTAB-Map</h2>
    <div class="stat" id="rtab">Waiting for playback…</div>
  </div>
  <aside>
    <div class="cloud-pane" id="cloud-pane">
      <div class="cloud-head">
        <h2>Point cloud (3D)</h2>
        <button class="btn" id="cloud-reset" type="button">Reset view</button>
        <button class="btn" id="cloud-fullscreen" type="button">Fullscreen</button>
      </div>
      <div class="cloud-wrap" id="cloud-wrap">
        <canvas id="cloud" width="640" height="340"></canvas>
      </div>
      <div class="ptz" id="ptz">
        <span>Pan</span>
        <button class="btn" type="button" data-ptz="pan-left" title="Pan left">◀</button>
        <button class="btn" type="button" data-ptz="pan-right" title="Pan right">▶</button>
        <span>Tilt</span>
        <button class="btn" type="button" data-ptz="tilt-up" title="Tilt up">▲</button>
        <button class="btn" type="button" data-ptz="tilt-down" title="Tilt down">▼</button>
        <span>Zoom</span>
        <button class="btn" type="button" data-ptz="zoom-in" title="Zoom in">+</button>
        <button class="btn" type="button" data-ptz="zoom-out" title="Zoom out">−</button>
        <span id="ptz-readout">drag to orbit · Shift+drag to pan · wheel to zoom</span>
      </div>
      <p class="resize-hint">Drag the pane's bottom-right corner to resize
        it, or use Fullscreen.</p>
    </div>
    <h2>Floor plan</h2>
    <canvas id="map" width="340" height="340"></canvas>
    <p class="legend">Top-down floor plan: every map point in its camera intensity,
    amber = camera trajectory, yellow wedge = the camera at the shown moment.</p>
  </aside>
</main>
<script>
const $ = (id) => document.getElementById(id);
const view = $('view').getContext('2d');
const playback = $('playback');
const rtab = $('rtab');
const slider = $('history-slider');
const historyLabel = $('history-label');
const liveButton = $('history-live');
const runInfo = $('run-info');
const runSelect = $('run-select');
let frames = 0, started = performance.now(), scrubSeq = 0, maxSeq = -1;
let latestDetections = null, source = null, currentRunId = null;
const samCanvas = document.getElementById('sam-view');
const samView = samCanvas ? samCanvas.getContext('2d') : null;
const samStatus = document.getElementById('sam-status');
let mode = 'live', scrubFetch = 0;
const SCENE = '{dataset_id}';
let lastMap = null, lastCamera = null;
function setMode(next) {{
  mode = next;
  liveButton.classList.toggle('active', mode === 'live');
  liveButton.textContent = mode === 'live' ? '● Live' : 'Go live';
}}
function updateHistoryLabel(extra) {{
  const shown = maxSeq < 0 ? 'no frames yet' :
    `frame ${{scrubSeq + 1}} / ${{maxSeq + 1}} · `
    + `${{mode === 'live' ? 'LIVE' : 'SCRUBBED (persisted)'}}`;
  historyLabel.innerHTML = `History: <b>${{shown}}</b>${{extra ? ' · ' + extra : ''}}`;
}}
function drawBoxes(objects) {{
  const list = objects || (latestDetections && latestDetections.objects) || [];
  view.strokeStyle = '#ffd23c'; view.lineWidth = 1.6;
  view.fillStyle = '#ffd23c'; view.font = '11px system-ui';
  for (const object of list) {{
    const [x1, y1, x2, y2] = object.box;
    view.strokeRect(x1, y1, x2 - x1, y2 - y1);
    view.fillText(`${{object.label}} #${{object.track_id}}`, x1 + 2, Math.max(10, y1 - 3));
  }}
}}
function drawSamObjects(ctx, objects) {{
  if (!ctx || !objects) return;
  ctx.strokeStyle = '#22d3ee'; ctx.lineWidth = 1.6;
  ctx.fillStyle = 'rgba(34, 211, 238, 0.16)';
  ctx.font = '11px system-ui';
  for (const object of objects) {{
    const polygon = object.mask_polygon || [];
    if (polygon.length > 1) {{
      ctx.beginPath();
      polygon.forEach(([x, y], i) => i ? ctx.lineTo(x, y) : ctx.moveTo(x, y));
      ctx.closePath(); ctx.fill(); ctx.stroke();
    }} else {{
      const [x1, y1, x2, y2] = object.box;
      ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);
    }}
    const [lx, ly] = polygon.length ? polygon[0] : object.box;
    ctx.fillStyle = '#22d3ee';
    ctx.fillText(`SAM ${{object.label}} #${{object.track_id}}`, lx + 2, Math.max(10, ly - 3));
    ctx.fillStyle = 'rgba(34, 211, 238, 0.16)';
  }}
}}
function drawSamPane(data) {{
  if (!samView) return;
  if (samStatus) {{
    samStatus.textContent = `SAM frame ${{data.frame_id}} · ${{data.objects.length}} object(s) · `
      + `updated ${{new Date().toLocaleTimeString()}} (SAM runs at its own rate; `
      + `the main preview above is not delayed by it)`;
  }}
  if (!data.image_b64) return;
  const image = new Image();
  image.onload = () => {{
    samView.drawImage(image, 0, 0, samCanvas.width, samCanvas.height);
    drawSamObjects(samView, data.objects);
    URL.revokeObjectURL(image.src);
  }};
  image.src = 'data:image/jpeg;base64,' + data.image_b64;
}}
function drawImageFrame(imageB64, overlay, objects, camera, labelData) {{
  const image = new Image();
  image.onload = () => {{
    view.drawImage(image, 0, 0, view.canvas.width, view.canvas.height);
    for (const point of (overlay || [])) {{
      view.fillStyle = point.c;
      view.beginPath();
      view.arc(point.x, point.y, point.d < {near_m} * 1.5 ? 2.2 : 1.4, 0, Math.PI * 2);
      view.fill();
    }}
    drawBoxes(objects);
    URL.revokeObjectURL(image.src);
  }};
  image.src = 'data:image/jpeg;base64,' + imageB64;
  lastCamera = camera || null;
  if (labelData) {{
    playback.innerHTML = `Frame <b>${{labelData.index + 1}} / ${{labelData.total}}</b><br>`
      + `Overlay points this frame <b>${{(overlay || []).length}}</b>`;
  }}
  if (lastMap) drawMap(lastMap, lastCamera);
}}
const FLOOR_PX = 340, FLOOR_PAD = 10;
function showMap(data) {{
  const image = new Image();
  image.onload = () => {{
    lastMap = {{image, extent: data.extent, trajectory: data.trajectory_xy}};
    drawMap(lastMap, lastCamera);
  }};
  image.src = 'data:image/png;base64,' + data.floor_png;
}}
function drawMap(map, camera) {{
  const ctx = $('map').getContext('2d');
  const [minX, maxX, minZ, maxZ] = map.extent;
  const scale = (FLOOR_PX - 2 * FLOOR_PAD) / Math.max(maxX - minX, maxZ - minZ, 0.01);
  const px = (p) => [
    FLOOR_PAD + (p[0] - minX) * scale, FLOOR_PX - FLOOR_PAD - (p[1] - minZ) * scale,
  ];
  ctx.clearRect(0, 0, FLOOR_PX, FLOOR_PX);
  if (map.image) ctx.drawImage(map.image, 0, 0);
  if (map.points) {{
    ctx.fillStyle = '#c8ccd2';
    for (const p of map.points) {{
      const [x, y] = px([p[0], p[2]]);
      ctx.fillRect(x, y, 1.6, 1.6);
    }}
  }}
  ctx.strokeStyle = '#ffb03a'; ctx.lineWidth = 2; ctx.beginPath();
  (map.trajectory || []).forEach((point, i) => {{
    const [x, y] = px(point); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
  }});
  ctx.stroke();
  if (camera) drawCamera(ctx, px([camera.x, camera.z]), camera);
}}
function drawCamera(ctx, [x, y], camera) {{
  const heading = Math.atan2(-camera.dz, camera.dx);
  const half = (camera.fov_deg / 2) * Math.PI / 180;
  const reach = 34;
  ctx.beginPath();
  ctx.moveTo(x, y);
  ctx.arc(x, y, reach, heading - half, heading + half);
  ctx.closePath();
  ctx.fillStyle = 'rgba(255, 210, 60, 0.22)';
  ctx.fill();
  ctx.strokeStyle = '#ffd23c'; ctx.lineWidth = 1.4;
  ctx.stroke();
  ctx.beginPath();
  ctx.arc(x, y, 4, 0, Math.PI * 2);
  ctx.fillStyle = '#ffd23c';
  ctx.fill();
}}
__CLOUD_SCRIPT__
// --- History scrub: persisted snapshots from SQLite via /runs ---
async function showSnapshot(seq) {{
  if (!currentRunId || maxSeq < 0) return;
  seq = Math.max(0, Math.min(maxSeq, seq));
  scrubSeq = seq; slider.value = String(seq);
  setMode(seq >= maxSeq && source ? 'live' : 'scrub');
  if (mode === 'live') {{ updateHistoryLabel(); return; }}
  const ticket = ++scrubFetch;
  try {{
    const snap = await (await fetch(`/runs/${{currentRunId}}/snapshot?seq=${{seq}}`)).json();
    if (ticket !== scrubFetch) return;
    drawImageFrame(snap.image_b64, snap.overlay, snap.objects, snap.camera,
      {{index: snap.seq, total: maxSeq + 1}});
    if (snap.cloud) {{
      setCloud(snap.cloud.points, snap.cloud.colors);
      lastMap = {{image: null, extent: snap.cloud.extent, trajectory: snap.cloud.trajectory_xy,
        points: snap.cloud.points}};
      drawMap(lastMap, snap.camera);
      rtab.innerHTML = `Keyframes <b>${{snap.cloud.keyframes}}</b> · cloud `
        + `<b>${{snap.cloud.cloud_points}}</b> pts · Odometry <b>${{snap.cloud.odom_state}}</b> `
        + `(at frame ${{snap.cloud.frame_id}})`;
    }} else {{
      setCloud([], []);
      rtab.textContent = 'No map snapshot at this point in the run yet.';
    }}
    updateHistoryLabel(
      `frame_id ${{snap.frame_id}} · ${{(snap.overlay || []).length}} overlay pts`);
  }} catch (error) {{
    updateHistoryLabel('snapshot unavailable');
  }}
}}
function stepHistory(delta) {{ showSnapshot(scrubSeq + delta); }}
slider.addEventListener('input', () => showSnapshot(Number(slider.value)));
$('history-back').addEventListener('click', () => stepHistory(-1));
$('history-forward').addEventListener('click', () => stepHistory(1));
$('history-back10').addEventListener('click', () => stepHistory(-10));
$('history-forward10').addEventListener('click', () => stepHistory(10));
liveButton.addEventListener('click', () => {{
  setMode('live'); scrubSeq = maxSeq; slider.value = String(Math.max(0, maxSeq));
  updateHistoryLabel('back at the live edge');
}});
document.addEventListener('keydown', (event) => {{
  if (event.target.tagName === 'SELECT' || event.target.tagName === 'INPUT') return;
  if (event.key === 'ArrowLeft') stepHistory(event.shiftKey ? -10 : -1);
  if (event.key === 'ArrowRight') stepHistory(event.shiftKey ? 10 : 1);
}});
async function refreshRuns(keep) {{
  try {{
    const listing = await (await fetch('/runs')).json();
    const chosen = keep || runSelect.value || currentRunId || '';
    runSelect.innerHTML = '<option value="">Current / latest run</option>';
    for (const run of listing.runs) {{
      const option = document.createElement('option');
      option.value = run.run_id;
      option.textContent = `${{run.dataset_id}} · ${{run.frame_count}} frames · `
        + `${{run.status}} · ${{run.run_id.slice(0, 8)}}`;
      option.selected = run.run_id === chosen;
      runSelect.appendChild(option);
    }}
  }} catch (error) {{ /* history list is best-effort */ }}
}}
$('run-load').addEventListener('click', async () => {{
  const runId = runSelect.value;
  if (!runId) return;
  const detail = await (await fetch(`/runs/${{runId}}`)).json();
  currentRunId = runId;
  maxSeq = detail.timeline.length - 1;
  slider.max = String(Math.max(0, maxSeq));
  runInfo.innerHTML = `Run: <b>${{runId.slice(0, 12)}}…</b> · `
    + `persisted frames: <b>${{detail.frame_count}}</b>`;
  cloudCentered = false;
  showSnapshot(0);
  updateHistoryLabel('loaded persisted run');
}});
// --- Live stream (SSE) ---
function attachListeners() {{
  source.addEventListener('run', (event) => {{
    const data = JSON.parse(event.data);
    currentRunId = data.run_id; frames = 0; maxSeq = -1; started = performance.now();
    cloudCentered = false;
    runInfo.innerHTML = `Run: <b>${{currentRunId.slice(0, 12)}}…</b> · persisting to SQLite…`;
    refreshRuns(currentRunId);
  }});
  source.addEventListener('detections', (event) => {{
    latestDetections = JSON.parse(event.data);
  }});
  source.addEventListener('sam', (event) => drawSamPane(JSON.parse(event.data)));
  listenForRegions(source);
  source.addEventListener('frame', (event) => {{
    const data = JSON.parse(event.data);
    frames += 1;
    maxSeq = Math.max(maxSeq, data.index);
    slider.max = String(maxSeq);
    runInfo.innerHTML = `Run: <b>${{(currentRunId || '').slice(0, 12)}}…</b> · `
      + `persisted frames: <b>${{maxSeq + 1}}</b>`;
    if (mode !== 'live') {{ updateHistoryLabel(); return; }}
    scrubSeq = data.index; slider.value = String(scrubSeq);
    const fps = (frames / ((performance.now() - started) / 1000)).toFixed(1);
    drawImageFrame(data.image_b64, data.detections, null, data.camera,
      {{index: data.index, total: data.total}});
    playback.innerHTML = `Frame <b>${{data.index + 1}} / ${{data.total}}</b><br>`
      + `Stream rate <b>${{fps}} fps</b><br>Overlay points this frame <b>${{data.point_count}}</b>`;
    updateHistoryLabel();
  }});
  source.addEventListener('map', (event) => {{
    const data = JSON.parse(event.data);
    if (mode === 'live') {{
      rtab.innerHTML = `Keyframes <b>${{data.keyframes}}</b> · cloud `
        + `<b>${{data.cloud_points}}</b> pts<br>Odometry <b>${{data.odom_state}}</b> `
        + `· lag <b>${{data.lag_frames}}</b> · dropped <b>${{data.dropped_frames}}</b>`;
      setCloud(data.points, data.point_colors);
      showMap(data);
    }}
  }});
  source.addEventListener('status', (event) => {{
    rtab.textContent = JSON.parse(event.data).message;
  }});
  source.addEventListener('final', (event) => {{
    const data = JSON.parse(event.data);
    if (mode === 'live') {{
      rtab.innerHTML = `Optimized poses <b>${{data.poses}}</b><br>`
        + `Trajectory travelled <b>${{data.travelled_m}} m</b><br>`
        + `Assembled cloud <b>${{data.cloud_points}} points</b>`;
      setCloud(data.points, data.point_colors);
      showMap(data);
    }}
    pauseButton.disabled = true;
    refreshRuns(currentRunId);
    source.close(); source = null;
    updateHistoryLabel('run finished and persisted — scrub or load it any time');
  }});
  source.onerror = () => {{
    if (frames === 0 && mode === 'live') {{
      playback.textContent = 'Stream unavailable — the server sent no frames; see its log.';
    }}
  }};
}}
function openStream() {{
  source = new EventSource('/stream?dataset=' + encodeURIComponent(SCENE));
  attachListeners();
  pauseButton.disabled = false;
}}
const sceneSelect = $('scene');
const pauseButton = $('pause');
const progress = $('progress');
const progressText = $('progress-text');
const barFill = $('bar-fill');
function describe(step) {{
  if (!step) return 'Starting…';
  const mb = (n) => (n / 1e6).toFixed(0);
  if (step.phase === 'downloading')
    return `Downloading ${{mb(step.done)}} / ${{mb(step.total)}} MB`;
  if (step.phase === 'verifying') return 'Verifying checksum…';
  if (step.phase === 'unpacking')
    return `Unpacking the recording ${{mb(step.done)}} / ${{mb(step.total)}} MB`;
  if (step.phase === 'extracting') return `Extracting frames ${{step.done}} / ${{step.total}}`;
  return 'Ready';
}}
async function sceneState() {{
  const listing = await (await fetch('/datasets')).json();
  return listing.datasets.find((scene) => scene.id === SCENE);
}}
async function prepareThenPlay() {{
  let scene = await sceneState();
  if (scene.state !== 'ready') {{
    progress.hidden = false;
    playback.textContent = 'This scene is downloaded once, then cached.';
    await fetch('/prepare?dataset=' + encodeURIComponent(SCENE), {{method: 'POST'}});
    while (scene.state !== 'ready') {{
      if (scene.state === 'error') {{
        progressText.textContent = `Preparing failed: ${{scene.error}}`;
        return;
      }}
      const step = scene.progress;
      barFill.style.width = step && step.total ? `${{100 * step.done / step.total}}%` : '0';
      progressText.textContent = describe(step);
      await new Promise((resolve) => setTimeout(resolve, 500));
      scene = await sceneState();
    }}
    progress.hidden = true;
  }}
  playback.textContent = 'Connecting…';
  openStream();
}}
async function fillScenes() {{
  const listing = await (await fetch('/datasets')).json();
  for (const scene of listing.datasets) {{
    const option = document.createElement('option');
    option.value = scene.id;
    option.textContent = scene.state === 'ready'
      ? scene.title : `${{scene.title}} (downloads on first play)`;
    option.selected = scene.id === SCENE;
    sceneSelect.appendChild(option);
  }}
}}
sceneSelect.addEventListener('change', () => {{
  location.href = '/?dataset=' + encodeURIComponent(sceneSelect.value);
}});
pauseButton.addEventListener('click', async () => {{
  const action = pauseButton.textContent === 'Pause' ? 'pause' : 'resume';
  const response = await fetch('/control', {{
    method: 'POST', headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{action}}),
  }});
  if (!response.ok) return;
  const state = (await response.json()).state;
  pauseButton.textContent = state === 'paused' ? 'Resume' : 'Pause';
}});
$('restart').addEventListener('click', () => location.reload());
fillScenes().then(prepareThenPlay);
refreshRuns();
resizeCloud();
updateHistoryLabel();
</script>
</body>
</html>
"""

# Spliced in before the server formats PAGE, so its braces stay doubled.
PAGE = PAGE.replace("__CLOUD_SCRIPT__", CLOUD_SCRIPT)
