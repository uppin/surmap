"""The object feed: one card per SAM surface, each with its own 3D preview.

The feed lists the run's surfaces (`surmap.survey.surfaces`): label and
id, points, static or moving, and the frames it was seen on. Each card
draws its surface's points client-side with its own orbit camera
(`orbitProject` in `view_math.py`), centred on the object: drag to orbit,
Shift+drag (or right-drag) to pan, wheel or pinch to zoom, or the
buttons. Unlike the server-rendered 3D pane, a card needs no round trip,
so every card moves on its own. Points are coloured by height, red when
the surface is moving, and capped per card (evenly thinned).

It fills from `surface` events on every stream (live, replay, cached
rerun), is rebuilt from a scrubbed moment's `snap.surfaces`, and is
cleared when a new run starts. The script is spliced into the page before
the server formats it, so its braces stay doubled for str.format; the
markup goes in with the 3D pane's aside, a format argument, so its CSS
braces are single.
"""

from __future__ import annotations

OBJECT_FEED_MARKUP = """    <div class="feed-pane">
      <style>
        .feed-pane h2 { font-size: 14px; margin: 16px 0 6px; font-weight: 650; }
        .object-feed { display: grid; gap: 8px; max-height: 560px; overflow-y: auto; }
        .feed-card { border: 1px solid #34383e; border-radius: 6px; background: #16181b;
          padding: 6px; }
        .feed-card header { display: flex; gap: 6px; align-items: baseline; flex-wrap: wrap;
          font-size: 12px; margin-bottom: 4px; }
        .feed-card header b { font-size: 13px; }
        .feed-card .badge { border-radius: 4px; padding: 0 5px; background: #2b3a2e;
          color: #8fe39b; }
        .feed-card .badge.moving { background: #4a2222; color: #ff8a8a; }
        .feed-card canvas { width: 100%; height: 150px; display: block; background: #0a0c0e;
          touch-action: none; cursor: grab; }
        .feed-card .ptz { margin-top: 4px; }
      </style>
      <h2>Objects <span class="stat" id="feed-count">— none yet</span></h2>
      <div class="object-feed" id="object-feed"></div>
      <p class="legend">One card per SAM surface. Drag to orbit · Shift+drag to pan ·
        wheel or pinch to zoom. Coloured by height; red = moving.</p>
    </div>"""

OBJECT_FEED_SCRIPT = """// --- Object feed: a card and a client-side 3D preview per surface ---
const objectFeed = $('object-feed');
const feedCount = $('feed-count');
const feedItems = new Map();
const FEED_MAX_POINTS = 4000;
let feedFrame = null;
function thinned(points) {{
  if (points.length <= FEED_MAX_POINTS) return points;
  const step = points.length / FEED_MAX_POINTS;
  return Array.from({{length: FEED_MAX_POINTS}}, (_, i) => points[Math.floor(i * step)]);
}}
function clearFeed() {{
  feedItems.clear();
  if (objectFeed) objectFeed.innerHTML = '';
  updateFeedCount();
}}
function updateFeedCount() {{
  if (!feedCount) return;
  const moving = [...feedItems.values()].filter((item) => item.moving).length;
  feedCount.textContent = feedItems.size
    ? `— ${{feedItems.size}} surface(s), ${{moving}} moving` : '— none yet';
}}
function feedItem(surfaceId, label) {{
  let item = feedItems.get(surfaceId);
  if (item || !objectFeed) return item;
  const card = document.createElement('div');
  card.className = 'feed-card';
  card.innerHTML = '<header></header><canvas width="440" height="300"></canvas>'
    + '<div class="ptz">'
    + ['◀:orbit:-0.2:0', '▶:orbit:0.2:0', '▲:orbit:0:0.2', '▼:orbit:0:-0.2',
       '+:zoom:1.25:0', '−:zoom:0.8:0', '⟲:reset:0:0']
      .map((spec) => {{
        const [text, kind, a, b] = spec.split(':');
        return `<button class="btn" type="button" data-kind="${{kind}}" data-a="${{a}}" `
          + `data-b="${{b}}">${{text}}</button>`;
      }}).join('') + '</div>';
  objectFeed.appendChild(card);
  const canvas = card.querySelector('canvas');
  item = {{surfaceId, label, moving: false, points: [], total: 0, first: null, last: null,
    card, canvas, ctx: canvas.getContext('2d'), radius: 1, dirty: true,
    view: {{azimuth: 0, elevation: 0.35, zoom: 1, panX: 0, panY: 0}}}};
  feedItems.set(surfaceId, item);
  wireFeedCard(item);
  return item;
}}
function wireFeedCard(item) {{
  const {{canvas, view}} = item;
  for (const button of item.card.querySelectorAll('button')) {{
    button.addEventListener('click', () => {{
      const a = Number(button.dataset.a), b = Number(button.dataset.b);
      if (button.dataset.kind === 'orbit') {{
        view.azimuth += a; view.elevation = Math.max(-1.5, Math.min(1.5, view.elevation + b));
      }} else if (button.dataset.kind === 'zoom') {{
        view.zoom = Math.max(0.2, Math.min(20, view.zoom * a));
      }} else {{
        Object.assign(view, {{azimuth: 0, elevation: 0.35, zoom: 1, panX: 0, panY: 0}});
      }}
      markFeedDirty(item);
    }});
  }}
  let drag = null;
  canvas.addEventListener('pointerdown', (event) => {{
    drag = {{x: event.clientX, y: event.clientY, pan: event.shiftKey || event.button === 2}};
    canvas.setPointerCapture(event.pointerId);
  }});
  canvas.addEventListener('pointermove', (event) => {{
    if (!drag) return;
    const dx = event.clientX - drag.x, dy = event.clientY - drag.y;
    drag.x = event.clientX; drag.y = event.clientY;
    if (drag.pan) {{
      const metresPerPx = 2 * item.radius / (0.9 * canvas.clientHeight * view.zoom);
      view.panX += dx * metresPerPx; view.panY += dy * metresPerPx;
    }} else {{
      view.azimuth += dx * 0.01;
      view.elevation = Math.max(-1.5, Math.min(1.5, view.elevation + dy * 0.01));
    }}
    markFeedDirty(item);
  }});
  const endDrag = () => {{ drag = null; }};
  canvas.addEventListener('pointerup', endDrag);
  canvas.addEventListener('pointercancel', endDrag);
  canvas.addEventListener('lostpointercapture', endDrag);
  canvas.addEventListener('wheel', (event) => {{
    event.preventDefault();
    const rate = event.ctrlKey ? 0.01 : 0.002;  // ctrl+wheel is a trackpad pinch
    view.zoom = Math.max(0.2, Math.min(20, view.zoom * Math.exp(-event.deltaY * rate)));
    markFeedDirty(item);
  }}, {{passive: false}});
  canvas.addEventListener('contextmenu', (event) => event.preventDefault());
}}
function markFeedDirty(item) {{
  item.dirty = true;
  if (feedFrame === null) feedFrame = requestAnimationFrame(drawFeed);
}}
function drawFeed() {{
  feedFrame = null;
  for (const item of feedItems.values()) if (item.dirty) drawFeedItem(item);
}}
function drawFeedItem(item) {{
  item.dirty = false;
  const header = item.card.querySelector('header');
  const seen = item.first === null ? `up to frame ${{item.last}}`
    : item.first === item.last ? `frame ${{item.last}}`
      : `frames ${{item.first}}–${{item.last}}`;
  header.innerHTML = `<b>${{item.label}} #${{item.surfaceId}}</b>`
    + `<span>${{item.total}} pts</span>`
    + `<span class="badge${{item.moving ? ' moving' : ''}}">`
    + `${{item.moving ? 'moving' : 'static'}}</span><span>${{seen}}</span>`;
  const {{canvas, ctx, points}} = item;
  ctx.fillStyle = '#0a0c0e';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  if (!points.length) return;
  let low = Infinity, high = -Infinity;
  const lo = [Infinity, Infinity, Infinity], hi = [-Infinity, -Infinity, -Infinity];
  for (const p of points) {{
    low = Math.min(low, p[1]); high = Math.max(high, p[1]);
    for (let k = 0; k < 3; k++) {{ lo[k] = Math.min(lo[k], p[k]); hi[k] = Math.max(hi[k], p[k]); }}
  }}
  item.radius = Math.max(0.05, Math.hypot(hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]) / 2);
  const projected = orbitProject(points, item.view, canvas.width, canvas.height);
  const order = projected.map((_, i) => i).sort((a, b) => projected[b][2] - projected[a][2]);
  const size = Math.max(2, Math.round(canvas.width / 180));
  for (const i of order) {{
    // Map y points down: the top of the object is the smallest y.
    const t = high > low ? (high - points[i][1]) / (high - low) : 0.5;
    const [r, g, b] = item.moving ? [255, 40 + Math.round(90 * t), 40] : depthColour(1 - t);
    ctx.fillStyle = `rgb(${{r}}, ${{g}}, ${{b}})`;
    ctx.fillRect(projected[i][0] - size / 2, projected[i][1] - size / 2, size, size);
  }}
}}
function feedSurfaceEvent(data) {{
  for (const surface of data.surfaces || []) {{
    const item = feedItem(surface.surface_id, surface.label);
    if (!item) continue;
    item.points = thinned(item.points.concat(surface.points || []));
    item.moving = Boolean(surface.moving);
    item.total = surface.total_points ?? item.points.length;
    item.first = item.first ?? data.frame_id;
    item.last = data.frame_id;
    markFeedDirty(item);
  }}
  updateFeedCount();
}}
function feedSnapshot(surfaces, frameId) {{
  clearFeed();
  for (const surface of surfaces || []) {{
    const item = feedItem(surface.surface_id, surface.label);
    if (!item) continue;
    item.points = thinned(surface.points || []);
    item.moving = Boolean(surface.moving);
    item.total = (surface.points || []).length;
    item.first = null;  // a moment's surfaces do not say when each was first seen
    item.last = frameId;
    markFeedDirty(item);
  }}
  updateFeedCount();
}}
"""
