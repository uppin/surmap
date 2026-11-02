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

Spliced into the page before the server formats it, so its braces stay
doubled for str.format.
"""

from __future__ import annotations

SAM_DEPTH_SCRIPT = """// --- SAM pane: each mask's dense points, coloured by depth ---
const samRegions = new Map();
const SAM_REGION_FRAMES = 32;
let samLast = null;
function noteRegions(data) {{
  samRegions.set(data.frame_id, data.regions || []);
  while (samRegions.size > SAM_REGION_FRAMES) samRegions.delete(samRegions.keys().next().value);
  if (samView && samLast && samLast.data.frame_id === data.frame_id) {{
    samView.drawImage(samLast.image, 0, 0, samCanvas.width, samCanvas.height);
    drawSamObjects(samView, samLast.data.objects);
    drawSamDepth(samView, samLast.data);
  }}
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
