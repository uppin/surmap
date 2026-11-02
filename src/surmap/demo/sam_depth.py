"""The SAM pane's dense points: each mask's own depth, drawn over it.

A `region` event names, per SAM mask, the object's own dense points (the
surface layer's depth band) as `[u, v, range_m]` on the SAM image
(`pixels`, `surmap.demo.events.RegionPlacer`). The SAM pane keeps the
last frames' regions and draws them over the masks of the frame it
shows: each point coloured near → far over that object's own range
(`depthColour` in `view_math.py`), with the range under the mask's
label. A region that arrives after its frame's image was drawn redraws
the pane. A scrubbed moment carries no region pixels, so it shows masks
only.

The SAM view also shares the 3D pane's selection (`cloudSelected`,
`cloud_pick.py`). `surface` events say which surface each SAM track became
on each frame (`noteSurfaces`). Hovering a mask (`maskAt`) selects that
surface, which lights up its points in 3D, and a click opens its feed
card. A surface selected anywhere (3D hover, a feed card) is outlined in
yellow on the masks of the shown frame that became it.

Spliced into the page before the server formats it, so its braces stay
doubled for str.format.
"""

from __future__ import annotations

SAM_DEPTH_SCRIPT = """// --- SAM pane: each mask's dense points, coloured by depth ---
const samRegions = new Map();
const samSurfaces = new Map();  // frame id -> (SAM track id -> surface id)
const SAM_REGION_FRAMES = 32;
let samLast = null;
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
}}
function samSurfaceAt(x, y) {{
  if (!samLast) return 0;
  const track = maskAt(samLast.data.objects, x, y);
  const tracks = samSurfaces.get(samLast.data.frame_id);
  return (track && tracks && tracks.get(track)) || 0;
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
  const objects = new Map((data.objects || []).map((object) => [object.track_id, object]));
  ctx.font = '11px system-ui';
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
    const object = objects.get(region.track_id);
    const polygon = (object && object.mask_polygon) || [];
    const anchor = object ? object.box : [pixels[0][0], pixels[0][1]];
    const [lx, ly] = polygon.length ? polygon[0] : anchor;
    ctx.fillStyle = '#e8f8ff';
    ctx.fillText(`${{near.toFixed(1)}}–${{far.toFixed(1)}} m`, lx + 2, Math.max(22, ly + 10));
  }}
}}
"""
