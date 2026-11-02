"""The SAM pane's dense points and object cards, in the shared selection.

A `region` event names, per SAM mask, the object's own dense points (the
surface layer's depth band) as `[u, v, range_m]` on the SAM image
(`pixels`, `surmap.demo.events.RegionPlacer`). The SAM pane keeps the
last frames' regions and draws them over the masks of the frame it
shows: each point coloured near → far over that object's own range
(`depthColour` in `view_math.py`). A region that arrives after its
frame's image was drawn redraws the pane. A scrubbed moment carries no
region pixels, so it shows masks only.

Each object's id sits on a card (`samCardsFor`, laid out by `layoutCards`):
`label #surface` in cyan once the object is a surface (it is in 3D), else
`label #track` (SAM's track id) in grey: too few depth points to be in 3D
yet; and its depth range when it has any. A card
sits as close to its own object as it fits (just above it when free, else
the nearest free spot beside it); cards never overlap and stay on the
image, and a leader with a filled circle at each end joins a card to its
object.

The SAM view shares the 3D pane's selection (`cloudSelected`,
`cloud_pick.py`). `surface` events say which surface each SAM track became
on each frame (`noteSurfaces`). Hovering a mask (`maskAt`) or its card
(`cardAt`) selects that surface, which lights up its points in 3D, and a
click opens its feed card. A surface selected anywhere (3D hover, a feed
card) is drawn in yellow: its masks' outline and its card.

Spliced into the page before the server formats it, so its braces stay
doubled for str.format.
"""

from __future__ import annotations

SAM_DEPTH_SCRIPT = """// --- SAM pane: each mask's dense points, coloured by depth ---
const samRegions = new Map();
const samSurfaces = new Map();  // frame id -> (SAM track id -> surface id)
const SAM_REGION_FRAMES = 32;
let samLast = null;
let samCardRects = [];  // the cards last drawn, for hovering
// Card colours: a surface (in 3D), pending (too few depth points yet), selected.
const SAM_LINKED_COLOUR = '#22d3ee', SAM_PENDING_COLOUR = '#8a939c';
const SAM_SELECTED_COLOUR = '#ffd23c';
function remember(frames, frameId, value) {{
  frames.set(frameId, value);
  while (frames.size > SAM_REGION_FRAMES) frames.delete(frames.keys().next().value);
}}
function noteRegions(data) {{
  remember(samRegions, data.frame_id, data.regions || []);
  if (samLast && samLast.data.frame_id === data.frame_id) redrawSam();
}}
function noteSurfaces(data) {{
  const tracks = new Map((data.surfaces || []).map((s) => [s.track_id, s.surface_id]));
  remember(samSurfaces, data.frame_id, tracks);
  if (samLast && samLast.data.frame_id === data.frame_id) redrawSam();
}}
function redrawSam() {{
  if (!samView || !samLast || !samLast.image) return;
  samView.drawImage(samLast.image, 0, 0, samCanvas.width, samCanvas.height);
  drawSamObjects(samView, samLast.data.objects);
  drawSamDepth(samView, samLast.data);
  drawSamSelection(samView, samLast.data);
  drawSamCards(samView, samLast.data);
}}
function samSurfaceAt(x, y) {{
  if (!samLast) return 0;
  // A card first (it lies over the image), else the mask under the cursor.
  const track = cardAt(samCardRects, x, y) || maskAt(samLast.data.objects, x, y);
  const tracks = samSurfaces.get(samLast.data.frame_id);
  return (track && tracks && tracks.get(track)) || 0;
}}
function samCardsFor(data, measure) {{
  const tracks = samSurfaces.get(data.frame_id);
  const regions = new Map((samRegions.get(data.frame_id) || []).map((r) => [r.track_id, r]));
  const items = [], details = new Map();
  for (const object of data.objects || []) {{
    const surface = (tracks && tracks.get(object.track_id)) || 0;
    // Without a surface (not in 3D yet) the card names SAM's track; its colour says so.
    const lines = [`${{object.label}} #${{surface || object.track_id}}`];
    const pixels = (regions.get(object.track_id) || {{}}).pixels || [];
    if (pixels.length) {{
      const ranges = pixels.map(([, , range]) => range);
      lines.push(`${{Math.min(...ranges).toFixed(1)}}–${{Math.max(...ranges).toFixed(1)}} m`);
    }}
    const polygon = object.mask_polygon || [];
    const [x1, y1, x2, y2] = object.box || [0, 0, 0, 0];
    const anchor = polygon.length >= 3
      ? [polygon.reduce((s, p) => s + p[0], 0) / polygon.length,
        polygon.reduce((s, p) => s + p[1], 0) / polygon.length]
      : [(x1 + x2) / 2, (y1 + y2) / 2];
    const box = polygon.length >= 3
      ? [Math.min(...polygon.map((p) => p[0])), Math.min(...polygon.map((p) => p[1])),
        Math.max(...polygon.map((p) => p[0])), Math.max(...polygon.map((p) => p[1]))]
      : [x1, y1, x2, y2];
    items.push({{key: object.track_id, anchor, box,
      width: Math.ceil(Math.max(...lines.map(measure))) + 12, height: 6 + 13 * lines.length}});
    details.set(object.track_id, {{lines, surface, pending: !surface}});
  }}
  const width = samCanvas ? samCanvas.width : 620, height = samCanvas ? samCanvas.height : 188;
  return layoutCards(items, width, height).map((card) => ({{...card, ...details.get(card.key)}}));
}}
function drawSamCards(ctx, data) {{
  ctx.font = '11px system-ui';
  samCardRects = samCardsFor(data, (text) => ctx.measureText(text).width);
  // Cyan: a surface (in 3D); grey: pending, too few depth points yet; yellow: selected.
  const colour = (card) => (card.surface && card.surface === cloudSelected) ? SAM_SELECTED_COLOUR
    : card.pending ? SAM_PENDING_COLOUR : SAM_LINKED_COLOUR;
  // Leaders under the cards, a filled circle at each end.
  ctx.lineWidth = 1.5;
  for (const card of samCardRects) {{
    ctx.strokeStyle = ctx.fillStyle = colour(card);
    ctx.beginPath(); ctx.moveTo(...card.from); ctx.lineTo(...card.to); ctx.stroke();
    for (const [x, y] of [card.from, card.to]) {{
      ctx.beginPath(); ctx.arc(x, y, 3, 0, 2 * Math.PI); ctx.fill();
    }}
  }}
  for (const card of samCardRects) {{
    const selected = colour(card) === SAM_SELECTED_COLOUR;
    ctx.fillStyle = 'rgba(12, 14, 17, 0.9)';
    ctx.fillRect(card.x, card.y, card.width, card.height);
    ctx.strokeStyle = colour(card); ctx.lineWidth = selected ? 2 : 1;
    ctx.strokeRect(card.x + 0.5, card.y + 0.5, card.width - 1, card.height - 1);
    card.lines.forEach((line, i) => {{
      ctx.fillStyle = card.pending ? '#b8c0c8' : i ? '#9fdcea' : '#e8f8ff';
      ctx.fillText(line, card.x + 6, card.y + 14 + 13 * i);
    }});
  }}
}}
function samSelectedTracks() {{
  const tracks = samLast && samSurfaces.get(samLast.data.frame_id);
  if (!cloudSelected || !tracks) return [];
  return [...tracks].filter(([, surface]) => surface === cloudSelected).map(([track]) => track);
}}
function drawSamSelection(ctx, data) {{
  const selected = new Set(samSelectedTracks());
  ctx.strokeStyle = '#ffd23c'; ctx.lineWidth = 3;
  ctx.fillStyle = 'rgba(255, 210, 60, 0.18)';
  for (const object of data.objects || []) {{
    const polygon = object.mask_polygon || [];
    if (!selected.has(object.track_id) || polygon.length < 3) continue;
    ctx.beginPath();
    polygon.forEach(([x, y], i) => i ? ctx.lineTo(x, y) : ctx.moveTo(x, y));
    ctx.closePath(); ctx.fill(); ctx.stroke();
  }}
}}
if (samCanvas) {{
let samDown = null;
const samPoint = (event) => {{
  const rect = samCanvas.getBoundingClientRect();
  return [(event.clientX - rect.left) / rect.width * samCanvas.width,
    (event.clientY - rect.top) / rect.height * samCanvas.height];
}};
samCanvas.addEventListener('pointermove', (event) => {{
  // Hovering a mask selects the surface its object became: lit up in 3D too.
  const surfaceId = samSurfaceAt(...samPoint(event));
  setCloudSelection(surfaceId, null);
  const item = surfaceId && feedItems.get(surfaceId);
  samCanvas.style.cursor = surfaceId ? 'pointer' : '';
  samCanvas.title = item ? `${{item.label}} #${{surfaceId}} — click to open in the feed` : '';
}});
samCanvas.addEventListener('pointerdown', (event) => {{
  samDown = {{x: event.clientX, y: event.clientY}};
}});
samCanvas.addEventListener('pointerup', (event) => {{
  // A click on a mask (not a drag) opens its object in the feed.
  const clicked = samDown && isClick(samDown, {{x: event.clientX, y: event.clientY}});
  samDown = null;
  const surfaceId = clicked ? samSurfaceAt(...samPoint(event)) : 0;
  if (surfaceId) focusFeedItem(surfaceId);
}});
samCanvas.addEventListener('pointerleave', () => setCloudSelection(0, null));
}}
function drawSamDepth(ctx, data) {{
  const regions = samRegions.get(data.frame_id);
  if (!ctx || !regions) return;
  for (const region of regions) {{
    const pixels = region.pixels || [];
    if (!pixels.length) continue;
    let near = Infinity, far = -Infinity;
    for (const [, , range] of pixels) {{
      near = Math.min(near, range); far = Math.max(far, range);
    }}
    const span = far - near;
    for (const [u, v, range] of pixels) {{
      const [r, g, b] = depthColour(span > 0 ? (range - near) / span : 0);
      ctx.fillStyle = `rgb(${{r}}, ${{g}}, ${{b}})`;
      ctx.fillRect(u - 1, v - 1, 2, 2);
    }}
  }}
}}
"""
