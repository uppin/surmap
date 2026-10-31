"""Server-rendered point-cloud script for the test console page.

The 3D pane shares the floor plan's rendering logic: the server
renders *every* map point into a PNG (`render_cloud_view` in
server.py, the orbit sibling of `render_floor_plan`) and this
script only displays the image. The only difference from the
floor plan is the PTZ pose, which lives server-side in
`PlaybackControls`: buttons, drag and wheel post pose deltas to
`/control`, and the player re-renders with the next map event
(and immediately when the pose version changes). No sampling,
no client-side geometry — nothing can flicker or go sparse.

Kept separate from page.py so both files stay under the 500-line
gate; page.py splices CLOUD_SCRIPT into PAGE before the server
formats it, so its braces stay doubled for str.format.
"""

from __future__ import annotations

CLOUD_SCRIPT = """// --- 3D point cloud: server-rendered image, PTZ pose on the server ---
const cloudCanvas = $('cloud');
const cloudCtx = cloudCanvas.getContext('2d');
let cloudImage = null;
async function postCloud(body) {{
  try {{
    const response = await fetch('/control', {{
      method: 'POST', headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify(body),
    }});
    if (!response.ok) return;
    const pose = await response.json();
    $('ptz-readout').textContent =
      `az ${{Math.round(pose.azimuth * 57.3)}}° · el ${{Math.round(pose.elevation * 57.3)}}° `
      + `· zoom ${{pose.zoom.toFixed(2)}}× — re-rendered with the next map update`;
  }} catch (error) {{ /* stream not live; pose applies to the next run */ }}
}}
let cloudPostTimer = null, cloudPending = null;
function postCloudDebounced(body) {{
  cloudPending = body;
  if (cloudPostTimer) return;
  cloudPostTimer = setTimeout(() => {{
    cloudPostTimer = null;
    if (cloudPending) postCloud(cloudPending);
    cloudPending = null;
  }}, 120);
}}
function setCloud(cloudPng) {{
  if (!cloudPng) {{ cloudImage = null; drawCloud(); return; }}
  const image = new Image();
  image.onload = () => {{ cloudImage = image; drawCloud(); }};
  image.src = 'data:image/png;base64,' + cloudPng;
}}
function drawCloud() {{
  const w = cloudCanvas.width, h = cloudCanvas.height;
  cloudCtx.fillStyle = '#0a0c0e';
  cloudCtx.fillRect(0, 0, w, h);
  if (cloudImage) cloudCtx.drawImage(cloudImage, 0, 0, w, h);
}}
function resizeCloud() {{
  const wrap = $('cloud-wrap');
  const dpr = window.devicePixelRatio || 1;
  cloudCanvas.width = Math.max(2, Math.round(wrap.clientWidth * dpr));
  cloudCanvas.height = Math.max(2, Math.round(wrap.clientHeight * dpr));
  drawCloud();
}}
function ptzAction(action) {{
  const orbit = (dAz, dEl) =>
    postCloud({{action: 'cloud_orbit', d_azimuth: dAz, d_elevation: dEl}});
  if (action === 'pan-left') orbit(-0.18, 0);
  if (action === 'pan-right') orbit(0.18, 0);
  if (action === 'tilt-up') orbit(0, 0.18);
  if (action === 'tilt-down') orbit(0, -0.18);

  if (action === 'zoom-in') postCloud({{action: 'cloud_zoom', factor: 0.82}});
  if (action === 'zoom-out') postCloud({{action: 'cloud_zoom', factor: 1.22}});
}}
document.querySelectorAll('[data-ptz]').forEach((button) => {{
  button.addEventListener('click', () => ptzAction(button.dataset.ptz));
}});
$('cloud-reset').addEventListener('click', () => postCloud({{action: 'cloud_reset'}}));
$('cloud-fullscreen').addEventListener('click', () => {{
  const pane = $('cloud-pane');
  if (document.fullscreenElement) document.exitFullscreen();
  else pane.requestFullscreen();
}});
document.addEventListener('fullscreenchange', () => setTimeout(resizeCloud, 60));
new ResizeObserver(resizeCloud).observe($('cloud-wrap'));
let cloudDrag = null;
cloudCanvas.addEventListener('pointerdown', (event) => {{
  cloudDrag = {{x: event.clientX, y: event.clientY, pan: event.shiftKey || event.button === 2}};
  cloudCanvas.setPointerCapture(event.pointerId);
}});
cloudCanvas.addEventListener('pointermove', (event) => {{
  if (!cloudDrag) return;
  const dx = event.clientX - cloudDrag.x, dy = event.clientY - cloudDrag.y;
  cloudDrag.x = event.clientX; cloudDrag.y = event.clientY;
  if (cloudDrag.pan) {{
    postCloudDebounced({{action: 'cloud_pan', dx: -dx * 0.01, dz: dx * 0.004}});
  }} else {{
    postCloudDebounced({{action: 'cloud_orbit', d_azimuth: dx * 0.008, d_elevation: dy * 0.008}});
  }}
}});
cloudCanvas.addEventListener('pointerup', () => {{ cloudDrag = null; }});
cloudCanvas.addEventListener('wheel', (event) => {{
  event.preventDefault();
  postCloudDebounced({{action: 'cloud_zoom', factor: Math.exp(event.deltaY * 0.001)}});
}}, {{passive: false}});
cloudCanvas.addEventListener('contextmenu', (event) => event.preventDefault());
"""
