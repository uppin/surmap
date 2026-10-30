"""Demo page HTML (see server.py for the SSE contract)."""

from __future__ import annotations

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>SurMap demo — {title}</title>
<style>
  body {{ margin: 0; background: #17191c; color: #e8eaed;
    font-family: "Segoe UI", system-ui, sans-serif; }}
  header {{ padding: 20px 28px 8px; }}
  h1 {{ font-size: 22px; margin: 0 0 4px; font-weight: 650; }}
  .sub {{ color: #9aa3ad; font-size: 13px; margin: 0; }}
  main {{ display: flex; gap: 20px; padding: 16px 28px 28px;
    flex-wrap: wrap; align-items: flex-start; }}
  .stage {{ flex: 1 1 640px; max-width: 880px; }}
  canvas#view {{ width: 100%; background: #000; border: 1px solid #34383e; display: block; }}
  aside {{ flex: 0 1 360px; min-width: 300px; }}
  h2 {{ font-size: 14px; margin: 18px 0 6px; font-weight: 650; }}
  h2:first-child {{ margin-top: 2px; }}
  .stat {{ font-size: 13px; color: #c3c9d1; line-height: 1.7; }}
  .stat b {{ color: #fff; font-weight: 650; }}
  canvas#map {{ background: #101215; border: 1px solid #34383e;
    width: 100%; display: block; }}
  .legend {{ font-size: 12px; color: #9aa3ad; }}
  .dot {{ display: inline-block; width: 9px; height: 9px;
    border-radius: 50%; vertical-align: -1px; }}
  .controls {{ display: flex; gap: 8px; align-items: center; margin-top: 12px;
    flex-wrap: wrap; font-size: 13px; }}
  .controls select, .controls button {{ background: #24272c; color: #e8eaed;
    border: 1px solid #3b4047; border-radius: 6px; padding: 5px 10px; font: inherit; }}
  .controls button:disabled {{ opacity: 0.45; }}
  .progress {{ display: flex; gap: 10px; align-items: center; margin-top: 10px;
    font-size: 13px; color: #c3c9d1; }}
  .progress[hidden] {{ display: none; }}
  .bar {{ width: 320px; max-width: 60vw; height: 8px; background: #24272c;
    border-radius: 4px; overflow: hidden; }}
  .bar > div {{ height: 100%; width: 0; background: #2fd4c4; transition: width 0.3s; }}
</style>
</head>
<body>
<header>
  <h1>SurMap demo — {title}</h1>
  <p class="sub">{description} The RTAB-Map map is built live from the frames as they play, and
  its points are overlaid on the video by depth.</p>
  <div class="controls">
    <label for="scene">Scene</label>
    <select id="scene"></select>
    <button id="pause" disabled>Pause</button>
    <button id="restart">Restart</button>
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
      &nbsp;— features RTAB-Map tracked in this frame, coloured and sized by depth
      (stereo-matcher points when RTAB-Map is off).
      Yellow boxes: tracked objects from the separate detections stream.
    </p>
    <p class="legend">{credit}</p>
  </div>
  <aside>
    <h2>Playback</h2>
    <div class="stat" id="playback">Connecting…</div>
    <h2>RTAB-Map</h2>
    <div class="stat" id="rtab">Waiting for playback to finish…</div>
    <canvas id="map" width="340" height="340"></canvas>
    <p class="legend">Top-down floor plan: RTAB-Map cloud (sampled) in each point's camera
    intensity, amber = camera trajectory, yellow wedge = the camera now and its field of
    view.</p>
  </aside>
</main>
<script>
const view = document.getElementById('view').getContext('2d');
const playback = document.getElementById('playback');
const rtab = document.getElementById('rtab');
let frames = 0, started = performance.now(), lastPoints = 0;
let latestDetections = null;
const SCENE = '{dataset_id}';
// Latest floor plan and the shown frame's camera: the map is redrawn
// with every frame so the camera marker moves with the video.
let lastMap = null, lastCamera = null;
let source = null;
function drawBoxes() {{
  if (!latestDetections) return;
  view.strokeStyle = '#ffd23c'; view.lineWidth = 1.6;
  view.fillStyle = '#ffd23c'; view.font = '11px system-ui';
  for (const object of latestDetections.objects) {{
    const [x1, y1, x2, y2] = object.box;
    view.strokeRect(x1, y1, x2 - x1, y2 - y1);
    view.fillText(`${{object.label}} #${{object.track_id}}`, x1 + 2, Math.max(10, y1 - 3));
  }}
}}
function attachListeners() {{
source.addEventListener('detections', (event) => {{
  latestDetections = JSON.parse(event.data);
}});
source.addEventListener('frame', (event) => {{
  const data = JSON.parse(event.data);
  const image = new Image();
  image.onload = () => {{
    view.drawImage(image, 0, 0, view.canvas.width, view.canvas.height);
    for (const point of data.detections) {{
      view.fillStyle = point.c;  // depth colour, from the server's ramp
      view.beginPath();
      view.arc(point.x, point.y, point.d < {near_m} * 1.5 ? 2.2 : 1.4, 0, Math.PI * 2);
      view.fill();
    }}
    drawBoxes();
    URL.revokeObjectURL(image.src);
  }};
  image.src = 'data:image/jpeg;base64,' + data.image_b64;
  frames += 1; lastPoints = data.point_count;
  lastCamera = data.camera;
  if (lastMap) drawMap(lastMap.data, lastMap.extent, lastCamera);
  const fps = (frames / ((performance.now() - started) / 1000)).toFixed(1);
  playback.innerHTML = `Frame <b>${{data.index + 1}} / ${{data.total}}</b><br>`
    + `Stream rate <b>${{fps}} fps</b><br>`
    + `Overlay points this frame <b>${{data.point_count}}</b>`;
}});
let liveExtent = null;
source.addEventListener('map', (event) => {{
  const data = JSON.parse(event.data);
  rtab.innerHTML = `Keyframes <b>${{data.keyframes}}</b> · cloud `
    + `<b>${{data.cloud_points}}</b> pts<br>Odometry <b>${{data.odom_state}}</b> `
    + `· lag <b>${{data.lag_frames}}</b> · dropped <b>${{data.dropped_frames}}</b>`;
  const all = data.cloud_xy.concat(data.trajectory_xy);
  if (!all.length) return;
  if (!liveExtent) liveExtent = {{minX: 1e9, maxX: -1e9, minY: 1e9, maxY: -1e9}};
  for (const p of all) {{  // extent only grows, never jitters
    liveExtent.minX = Math.min(liveExtent.minX, p[0]);
    liveExtent.maxX = Math.max(liveExtent.maxX, p[0]);
    liveExtent.minY = Math.min(liveExtent.minY, p[1]);
    liveExtent.maxY = Math.max(liveExtent.maxY, p[1]);
  }}
  lastMap = {{data: {{cloud_xy: data.cloud_xy, trajectory_xy: data.trajectory_xy}},
    extent: liveExtent}};
  drawMap(lastMap.data, lastMap.extent, lastCamera);
}});
source.addEventListener('status', (event) => {{
  rtab.textContent = JSON.parse(event.data).message;
}});
source.addEventListener('final', (event) => {{
  const data = JSON.parse(event.data);
  rtab.innerHTML = `Optimized poses <b>${{data.poses}}</b><br>`
    + `Trajectory travelled <b>${{data.travelled_m}} m</b><br>`
    + `Assembled cloud <b>${{data.cloud_points}} points</b> `
    + `(sample of ${{data.cloud_xy.length}} drawn)`;
  lastMap = null;
  drawMap(data, null, lastCamera);
  source.close();
  pauseButton.disabled = true;
}});
source.onerror = () => {{
  if (frames === 0) {{
    playback.textContent = 'Stream unavailable — the server sent no frames; see its log.';
  }}
}};
}}
function openStream() {{
  source = new EventSource('/stream?dataset=' + encodeURIComponent(SCENE));
  attachListeners();
  pauseButton.disabled = false;
}}
const sceneSelect = document.getElementById('scene');
const pauseButton = document.getElementById('pause');
const progress = document.getElementById('progress');
const progressText = document.getElementById('progress-text');
const barFill = document.getElementById('bar-fill');
function describe(step) {{
  if (!step) return 'Starting…';
  const mb = (n) => (n / 1e6).toFixed(0);
  if (step.phase === 'downloading') {{
    return `Downloading ${{mb(step.done)}} / ${{mb(step.total)}} MB`;
  }}
  if (step.phase === 'verifying') return 'Verifying checksum…';
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
document.getElementById('restart').addEventListener('click', () => location.reload());
fillScenes().then(prepareThenPlay);
function drawMap(data, extent, camera) {{
  const canvas = document.getElementById('map');
  const ctx = canvas.getContext('2d');
  const all = data.cloud_xy.concat(data.trajectory_xy);
  if (!all.length) return;
  const xs = all.map(p => p[0]), ys = all.map(p => p[1]);
  const minX = extent ? extent.minX : Math.min(...xs);
  const maxX = extent ? extent.maxX : Math.max(...xs);
  const minY = extent ? extent.minY : Math.min(...ys);
  const maxY = extent ? extent.maxY : Math.max(...ys);
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  const scale = Math.min(320 / Math.max(0.01, maxX - minX),
    320 / Math.max(0.01, maxY - minY));
  const px = p => [10 + (p[0] - minX) * scale, 330 - (p[1] - minY) * scale];
  for (const point of data.cloud_xy) {{
    // [x, y] or [x, y, r, g, b]
    ctx.fillStyle = point.length === 5
      ? `rgb(${{point[2]}}, ${{point[3]}}, ${{point[4]}})` : '#8a929c';
    const [x, y] = px(point);
    ctx.fillRect(x, y, 1.6, 1.6);
  }}
  ctx.strokeStyle = '#ffb03a'; ctx.lineWidth = 2; ctx.beginPath();
  data.trajectory_xy.forEach((point, i) => {{
    const [x, y] = px(point); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
  }});
  ctx.stroke();
  if (camera) drawCamera(ctx, px([camera.x, camera.z]), camera);
}}
function drawCamera(ctx, [x, y], camera) {{
  // Field-of-view wedge along the heading (canvas y grows downward).
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
</script>
</body>
</html>
"""
