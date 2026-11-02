"""Server-rendered point-cloud script for the test console page.

The 3D pane shares the floor plan's rendering logic: the server
renders *every* map point into a PNG (`render_cloud_view` in
server.py, the orbit sibling of `render_floor_plan`) and this
script only displays the image. The only difference from the
floor plan is the PTZ pose, which lives server-side in
the session's `CloudViewer` (`cloud_view.py`): buttons, drag and wheel
post pose deltas to `/control`, which answers with the last scene drawn
from the new pose (`cloud_png`) — during a run, after it and on a
scrubbed moment alike. Deltas made while a post waits are merged
(`mergeCloudBody`), so a drag sends its whole movement. No sampling,
no client-side geometry — nothing can flicker or go sparse. The SAM
surface layer is drawn into the same image server-side; the
Surfaces button only shows or hides it (`cloud_surfaces`).

Kept separate from page.py so both files stay under the 500-line
gate; page.py splices CLOUD_SCRIPT into PAGE before the server
formats it, so its braces stay doubled for str.format.
"""

from __future__ import annotations

CLOUD_SCRIPT = """// --- 3D point cloud: server-rendered image, PTZ pose on the server ---
const cloudCanvas = $('cloud');
const cloudCtx = cloudCanvas ? cloudCanvas.getContext('2d') : null;
let cloudImage = null;
// Created with the pane's other controls below; declared here so postCloud sees it.
let surfacesButton = null;
async function postCloud(body) {{
  try {{
    const response = await fetch('/control', {{
      method: 'POST', headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify(body),
    }});
    if (!response.ok) return;
    const pose = await response.json();
    // The server answers with the last scene drawn from the new pose; a
    // moment scrubbed during a live run is drawn again from its snapshot.
    if (mode === 'scrub' && source) showSnapshot(scrubSeq);
    else if (pose.cloud_png) setCloud(pose.cloud_png, pose.cloud_ids_png);
    if (surfacesButton) {{
      surfacesButton.textContent = pose.surfaces_visible ? 'Hide surfaces' : 'Show surfaces';
    }}
    $('ptz-readout').textContent =
      `az ${{Math.round(pose.azimuth * 57.3)}}° · el ${{Math.round(pose.elevation * 57.3)}}° `
      + `· zoom ${{pose.zoom.toFixed(2)}}×`;
  }} catch (error) {{ /* server unreachable; the next post carries the movement */ }}
}}
let cloudPostTimer = null, cloudPending = null;
function postCloudDebounced(body) {{
  // Moves made while a post waits add up (mergeCloudBody), so a drag
  // sends its whole movement, not the last pointer event's.
  cloudPending = mergeCloudBody(cloudPending, body);
  if (cloudPostTimer) return;
  cloudPostTimer = setTimeout(() => {{
    cloudPostTimer = null;
    if (cloudPending) postCloud(cloudPending);
    cloudPending = null;
  }}, 120);
}}
function setCloud(cloudPng, idsPng) {{
  setCloudIds(cloudPng ? idsPng : null);  // which surface each pixel shows (cloud_pick.py)
  if (!cloudPng) {{ cloudImage = null; drawCloud(); return; }}
  const image = new Image();
  image.onload = () => {{ cloudImage = image; drawCloud(); }};
  image.src = 'data:image/png;base64,' + cloudPng;
}}
function drawCloud() {{
  if (!cloudCtx || !cloudCanvas) return;
  const w = cloudCanvas.width, h = cloudCanvas.height;
  cloudCtx.fillStyle = '#0a0c0e';
  cloudCtx.fillRect(0, 0, w, h);
  if (cloudImage) cloudCtx.drawImage(cloudImage, 0, 0, w, h);
  drawCloudSelection(cloudCtx, w, h);
}}
function resizeCloud() {{
  if (!cloudCanvas) return;
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
if (cloudCanvas) {{
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
  cloudDrag = {{x: event.clientX, y: event.clientY, pan: event.shiftKey || event.button === 2,
    down: {{x: event.clientX, y: event.clientY}}}};
  cloudCanvas.setPointerCapture(event.pointerId);
}});
cloudCanvas.addEventListener('pointermove', (event) => {{
  if (!cloudDrag) {{ setCloudSelection(pickAt(event), event); return; }}  // hover: name, select
  const dx = event.clientX - cloudDrag.x, dy = event.clientY - cloudDrag.y;
  cloudDrag.x = event.clientX; cloudDrag.y = event.clientY;
  if (cloudDrag.pan) {{
    postCloudDebounced({{action: 'cloud_pan', dx: -dx * 0.01, dz: dx * 0.004}});
  }} else {{
    postCloudDebounced({{action: 'cloud_orbit', d_azimuth: dx * 0.008, d_elevation: dy * 0.008}});
  }}
}});
const endCloudDrag = () => {{ cloudDrag = null; }};
cloudCanvas.addEventListener('pointerup', (event) => {{
  // A click on a surface (not a drag) opens it in the object feed.
  const clicked = cloudDrag && isClick(cloudDrag.down, {{x: event.clientX, y: event.clientY}});
  cloudDrag = null;
  const surfaceId = clicked ? pickAt(event) : 0;
  if (surfaceId) focusFeedItem(surfaceId);
}});
cloudCanvas.addEventListener('pointerleave', () => {{
  if (!cloudDrag) setCloudSelection(0, null);
}});
cloudCanvas.addEventListener('pointercancel', endCloudDrag);
cloudCanvas.addEventListener('lostpointercapture', endCloudDrag);
cloudCanvas.addEventListener('wheel', (event) => {{
  event.preventDefault();
  const rate = event.ctrlKey ? 0.01 : 0.001;  // ctrl+wheel is a trackpad pinch
  postCloudDebounced({{action: 'cloud_zoom', factor: Math.exp(event.deltaY * rate)}});
}}, {{passive: false}});
cloudCanvas.addEventListener('contextmenu', (event) => event.preventDefault());
// SAM surfaces: the server draws the station's surface layer into the
// cloud image; this button only toggles it.
surfacesButton = document.createElement('button');
surfacesButton.className = 'btn';
surfacesButton.type = 'button';
surfacesButton.textContent = 'Hide surfaces';
$('cloud-reset').before(surfacesButton);
surfacesButton.addEventListener('click', () => postCloud({{action: 'cloud_surfaces'}}));
}}
"""
