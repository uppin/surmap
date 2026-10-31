"""WebGL point-cloud script for the test console page (see page.py).

Kept separate from page.py so both files stay under the 500-line gate;
page.py splices CLOUD_SCRIPT into PAGE before the server formats it,
so its braces stay doubled for str.format like the rest of the page.
"""

from __future__ import annotations

CLOUD_SCRIPT = """// --- 3D point cloud: raw WebGL points, PTZ orbit camera (no external deps) ---
const cloudCanvas = $('cloud');
const gl = cloudCanvas.getContext('webgl', {{antialias: true}});
const ptz = {{az: -0.8, el: 0.85, dist: 12, target: [0, 0, 0]}};
let cloudData = null, cloudBuffer = null, cloudCount = 0;
let cloudProgram = null, cloudCentered = false;
// The latest SAM region(s) in 3D: replaced by each region event, never accumulated.
let regionBuffer = null, regionCount = 0;
const REGION_COLOURS = [[1, 0.25, 0.6], [0.2, 0.9, 1], [1, 0.85, 0.1], [0.5, 1, 0.3]];
function cloudShader(type, text) {{
  const shader = gl.createShader(type);
  gl.shaderSource(shader, text); gl.compileShader(shader);
  return shader;
}}
function initCloud() {{
  if (!gl) {{ $('ptz-readout').textContent = 'WebGL unavailable in this browser'; return; }}
  const vs = 'attribute vec3 aPos; attribute vec3 aCol; uniform mat4 uMvp; varying vec3 vCol;'
    + 'void main(){{ vCol = aCol; gl_Position = uMvp * vec4(aPos, 1.0); gl_PointSize = 2.6; }}';
  const fs = 'precision mediump float; varying vec3 vCol;'
    + 'void main(){{ vec2 d = gl_PointCoord - 0.5; if (dot(d, d) > 0.25) discard;'
    + ' gl_FragColor = vec4(vCol, 1.0); }}';
  cloudProgram = gl.createProgram();
  gl.attachShader(cloudProgram, cloudShader(gl.VERTEX_SHADER, vs));
  gl.attachShader(cloudProgram, cloudShader(gl.FRAGMENT_SHADER, fs));
  gl.linkProgram(cloudProgram);
  cloudBuffer = gl.createBuffer();
  regionBuffer = gl.createBuffer();
}}
function setCloud(points, colors) {{
  cloudData = {{points: points || [], colors: colors || []}};
  cloudCount = cloudData.points.length;
  if (!gl || !cloudData.points.length) {{ drawCloud(); return; }}
  const flat = new Float32Array(cloudCount * 6);
  cloudData.points.forEach((p, i) => {{
    // Map frame (x right, y down, z forward) -> view (x right, z up, y forward)
    flat.set([p[0], p[2], -p[1]], i * 6);
    const c = (cloudData.colors[i] || [180, 180, 180]);
    flat.set([c[0] / 255, c[1] / 255, c[2] / 255], i * 6 + 3);
  }});
  gl.bindBuffer(gl.ARRAY_BUFFER, cloudBuffer);
  gl.bufferData(gl.ARRAY_BUFFER, flat, gl.DYNAMIC_DRAW);
  if (!cloudCentered) resetCloudView();
  drawCloud();
}}
function setRegionLayer(regions) {{
  const placed = (regions || []).filter((r) => r.points && r.points.length);
  regionCount = placed.reduce((n, r) => n + r.points.length, 0);
  if (gl && regionCount) {{
    const flat = new Float32Array(regionCount * 6);
    let i = 0;
    placed.forEach((region, k) => {{
      const c = REGION_COLOURS[(region.track_id ?? k) % REGION_COLOURS.length];
      for (const p of region.points) {{
        flat.set([p[0], p[2], -p[1], c[0], c[1], c[2]], i * 6);
        i += 1;
      }}
    }});
    gl.bindBuffer(gl.ARRAY_BUFFER, regionBuffer);
    gl.bufferData(gl.ARRAY_BUFFER, flat, gl.DYNAMIC_DRAW);
  }}
  drawCloud();
}}
function drawPoints(buffer, count, mvp) {{
  gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
  const pos = gl.getAttribLocation(cloudProgram, 'aPos');
  const col = gl.getAttribLocation(cloudProgram, 'aCol');
  gl.enableVertexAttribArray(pos); gl.enableVertexAttribArray(col);
  gl.vertexAttribPointer(pos, 3, gl.FLOAT, false, 24, 0);
  gl.vertexAttribPointer(col, 3, gl.FLOAT, false, 24, 12);
  gl.uniformMatrix4fv(gl.getUniformLocation(cloudProgram, 'uMvp'), false, mvp);
  gl.drawArrays(gl.POINTS, 0, count);
}}
function cloudBounds() {{
  if (!cloudData || !cloudData.points.length) return null;
  const lo = [Infinity, Infinity, Infinity], hi = [-Infinity, -Infinity, -Infinity];
  for (const p of cloudData.points) {{
    const v = [p[0], p[2], -p[1]];
    v.forEach((value, axis) => {{
      lo[axis] = Math.min(lo[axis], value);
      hi[axis] = Math.max(hi[axis], value);
    }});
  }}
  return {{lo, hi}};
}}
function resetCloudView() {{
  const bounds = cloudBounds();
  if (bounds) {{
    ptz.target = bounds.lo.map((v, i) => (v + bounds.hi[i]) / 2);
    const span = Math.max(...bounds.hi.map((v, i) => v - bounds.lo[i]), 0.5);
    ptz.dist = span * 1.9;
  }} else {{ ptz.target = [0, 0, 0]; ptz.dist = 12; }}
  ptz.az = -0.8; ptz.el = 0.85; cloudCentered = true;
  drawCloud();
}}
function mvpMatrix() {{
  const aspect = cloudCanvas.width / Math.max(1, cloudCanvas.height);
  const f = 1 / Math.tan(0.35), near = 0.05, far = 500;
  const ce = Math.cos(ptz.el), se = Math.sin(ptz.el);
  const eye = [
    ptz.target[0] + ptz.dist * ce * Math.sin(ptz.az),
    ptz.target[1] + ptz.dist * se,
    ptz.target[2] + ptz.dist * ce * Math.cos(ptz.az),
  ];
  const zAxis = eye.map((v, i) => v - ptz.target[i]);
  const zl = Math.hypot(...zAxis) || 1; zAxis.forEach((v, i) => zAxis[i] = v / zl);
  let xAxis = [zAxis[2], 0, -zAxis[0]];
  const xl = Math.hypot(...xAxis) || 1; xAxis = xAxis.map((v) => v / xl);
  const yAxis = [
    zAxis[1] * xAxis[2] - zAxis[2] * xAxis[1],
    zAxis[2] * xAxis[0] - zAxis[0] * xAxis[2],
    zAxis[0] * xAxis[1] - zAxis[1] * xAxis[0],
  ];
  const view = new Float32Array([
    xAxis[0], yAxis[0], zAxis[0], 0, xAxis[1], yAxis[1], zAxis[1], 0,
    xAxis[2], yAxis[2], zAxis[2], 0,
    -xAxis.reduce((s, v, i) => s + v * eye[i], 0),
    -yAxis.reduce((s, v, i) => s + v * eye[i], 0),
    -zAxis.reduce((s, v, i) => s + v * eye[i], 0), 1,
  ]);
  const proj = new Float32Array([
    f / aspect, 0, 0, 0, 0, f, 0, 0, 0, 0, (far + near) / (near - far), -1,
    0, 0, 2 * far * near / (near - far), 0,
  ]);
  const out = new Float32Array(16);
  for (let c = 0; c < 4; c++) for (let r = 0; r < 4; r++) {{
    out[c * 4 + r] = proj[r] * view[c * 4] + proj[4 + r] * view[c * 4 + 1]
      + proj[8 + r] * view[c * 4 + 2] + proj[12 + r] * view[c * 4 + 3];
  }}
  return out;
}}
function drawCloud() {{
  if (!gl || !cloudProgram) return;
  gl.viewport(0, 0, cloudCanvas.width, cloudCanvas.height);
  gl.clearColor(0.04, 0.05, 0.06, 1); gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
  gl.enable(gl.DEPTH_TEST);
  if (!cloudCount && !regionCount) return;
  gl.useProgram(cloudProgram);
  const mvp = mvpMatrix();
  if (cloudCount) drawPoints(cloudBuffer, cloudCount, mvp);
  if (regionCount) drawPoints(regionBuffer, regionCount, mvp);
  $('ptz-readout').textContent =
    `${{cloudCount}} pts · region ${{regionCount}} pts · pan ${{Math.round(ptz.az * 57.3)}}° · `
    + `tilt ${{Math.round(ptz.el * 57.3)}}° · zoom ${{ptz.dist.toFixed(1)}} m`;
}}
function resizeCloud() {{
  const wrap = $('cloud-wrap');
  const dpr = window.devicePixelRatio || 1;
  cloudCanvas.width = Math.max(2, Math.round(wrap.clientWidth * dpr));
  cloudCanvas.height = Math.max(2, Math.round(wrap.clientHeight * dpr));
  drawCloud();
}}
function ptzAction(action) {{
  const step = 0.18, panStep = Math.max(0.15, ptz.dist * 0.08);
  if (action === 'pan-left') ptz.az -= step;
  if (action === 'pan-right') ptz.az += step;
  if (action === 'tilt-up') ptz.el = Math.min(1.5, ptz.el + step);
  if (action === 'tilt-down') ptz.el = Math.max(-1.5, ptz.el - step);
  if (action === 'zoom-in') ptz.dist = Math.max(0.4, ptz.dist * 0.82);
  if (action === 'zoom-out') ptz.dist = Math.min(300, ptz.dist * 1.22);
  if (action === 'pan-forward' || action === 'pan-back') {{
    const s = action === 'pan-forward' ? panStep : -panStep;
    ptz.target[0] += -Math.sin(ptz.az) * s; ptz.target[2] += -Math.cos(ptz.az) * s;
  }}
  drawCloud();
}}
document.querySelectorAll('[data-ptz]').forEach((button) => {{
  button.addEventListener('click', () => ptzAction(button.dataset.ptz));
}});
$('cloud-reset').addEventListener('click', resetCloudView);
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
    const s = ptz.dist * 0.0016;
    ptz.target[0] += (-dx * Math.cos(ptz.az)) * s;
    ptz.target[1] += dy * s;
    ptz.target[2] += (dx * Math.sin(ptz.az)) * s;
  }} else {{
    ptz.az -= dx * 0.008;
    ptz.el = Math.max(-1.5, Math.min(1.5, ptz.el + dy * 0.008));
  }}
  drawCloud();
}});
cloudCanvas.addEventListener('pointerup', () => {{ cloudDrag = null; }});
cloudCanvas.addEventListener('wheel', (event) => {{
  event.preventDefault();
  ptz.dist = Math.max(0.4, Math.min(300, ptz.dist * Math.exp(event.deltaY * 0.001)));
  drawCloud();
}}, {{passive: false}});
cloudCanvas.addEventListener('contextmenu', (event) => event.preventDefault());
initCloud();
"""
