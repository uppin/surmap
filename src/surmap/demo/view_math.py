"""Pure page-script helpers shared by the 3D pane, the object feed and the SAM pane.

No DOM here, so the functions run in node on their own
(`tests/test_demo_object_feed.py`):

- `mergeCloudBody(pending, body)` folds a PTZ post into the one still
  pending, so a drag sends its whole movement: orbit and pan deltas add,
  zoom factors multiply, a different action replaces the pending one.
- `depthColour(t)` is the near → far gradient (`t` in [0, 1]) the SAM pane
  and the feed colour an object's points with: warm near, cool far.
- `orbitProject(points, view, width, height)` projects an object's points
  into a preview canvas with its own orbit camera, centred on the
  object's bounding box and fitted to the canvas at zoom 1.
- `surfaceIdNear(ids, width, height, x, y, radius)` reads the 3D pane's id
  image (`cloud_ids_png`: R + 256 * G where alpha is set): the surface
  nearest pixel (x, y) within `radius`, or 0.
- `selectionMask(ids, id)` is an RGBA overlay of every pixel of surface `id`.
- `isClick(down, up)` tells a click (released within 4 px) from a drag.
- `polygonContains(polygon, x, y)` is the even-odd test on a SAM mask outline;
  `maskAt(objects, x, y)` is the track of the smallest mask under (x, y), or 0.
- `layoutCards(items, width, height)` places one card per object as close to
  its own object's box as it fits: just above it when free, else the
  nearest free spot beside it, never overlapping another card, never off
  the image and not over its object while a spot beside it is free; with a
  leader from the card's nearest edge point (`from`) to the object (`to`). `cardAt(cards, x, y)` is
  the key of the card under (x, y), or 0.

Spliced into the page before the server formats it, so its braces stay
doubled for str.format.
"""

from __future__ import annotations

VIEW_HELPERS = """// --- View helpers: pure functions (no DOM) ---
function mergeCloudBody(pending, body) {{
  if (!pending || pending.action !== body.action) return {{...body}};
  const merged = {{...pending}};
  for (const key of ['d_azimuth', 'd_elevation', 'dx', 'dz']) {{
    if (key in body) merged[key] = (merged[key] || 0) + body[key];
  }}
  if ('factor' in body) merged.factor = (merged.factor ?? 1) * body.factor;
  return merged;
}}
const DEPTH_STOPS = [[255, 72, 40], [255, 200, 40], [80, 230, 120], [40, 170, 255], [120, 90, 255]];
function depthColour(t) {{
  const clamped = Math.max(0, Math.min(1, Number.isFinite(t) ? t : 0));
  const scaled = clamped * (DEPTH_STOPS.length - 1);
  const i = Math.min(DEPTH_STOPS.length - 2, Math.floor(scaled));
  const f = scaled - i;
  return DEPTH_STOPS[i].map((c, k) => Math.round(c + (DEPTH_STOPS[i + 1][k] - c) * f));
}}
function surfaceIdNear(ids, width, height, x, y, radius) {{
  let best = 0, bestDistance = Infinity;
  const cx = Math.round(x), cy = Math.round(y);
  for (let v = Math.max(0, cy - radius); v <= Math.min(height - 1, cy + radius); v++) {{
    for (let u = Math.max(0, cx - radius); u <= Math.min(width - 1, cx + radius); u++) {{
      const i = (v * width + u) * 4;
      if (!ids[i + 3]) continue;
      const distance = (u - x) ** 2 + (v - y) ** 2;
      if (distance < bestDistance) {{ best = ids[i] + 256 * ids[i + 1]; bestDistance = distance; }}
    }}
  }}
  return best;
}}
function selectionMask(ids, id) {{
  const mask = new Uint8ClampedArray(ids.length);
  const low = id & 255, high = (id >> 8) & 255;
  for (let i = 0; i < ids.length; i += 4) {{
    if (ids[i + 3] && ids[i] === low && ids[i + 1] === high) {{
      mask[i] = 255; mask[i + 1] = 255; mask[i + 2] = 255; mask[i + 3] = 230;
    }}
  }}
  return mask;
}}
function polygonContains(polygon, x, y) {{
  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {{
    const [xi, yi] = polygon[i], [xj, yj] = polygon[j];
    if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) inside = !inside;
  }}
  return inside;
}}
function polygonArea(polygon) {{
  let twice = 0;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {{
    twice += polygon[j][0] * polygon[i][1] - polygon[i][0] * polygon[j][1];
  }}
  return Math.abs(twice) / 2;
}}
function maskAt(objects, x, y) {{
  let best = 0, bestArea = Infinity;
  for (const object of objects || []) {{
    const polygon = object.mask_polygon || [];
    if (polygon.length < 3 || !polygonContains(polygon, x, y)) continue;
    const area = polygonArea(polygon);
    if (area < bestArea) {{ best = object.track_id; bestArea = area; }}
  }}
  return best;
}}
const CARD_MARGIN_PX = 4, CARD_GAP_PX = 4, CARD_GRID_PX = 4;
const cardLayouts = new Map();  // memo: the same frame's cards are laid out once
function layoutCards(items, width, height) {{
  const memo = JSON.stringify([items, width, height]);
  if (cardLayouts.has(memo)) return cardLayouts.get(memo);
  const boxOf = (item) => item.box || [...item.anchor, ...item.anchor];
  const area = (b) => (b[2] - b[0]) * (b[3] - b[1]);
  // Smallest objects first: they have the fewest free spots near them.
  const order = items.map((_, i) => i)
    .sort((a, b) => area(boxOf(items[a])) - area(boxOf(items[b])) || a - b);
  const placed = [], laid = new Map();
  for (const i of order) {{
    const item = items[i], w = item.width, h = item.height;
    const [bx1, by1, bx2, by2] = boxOf(item), cx = (bx1 + bx2) / 2, cy = (by1 + by2) / 2;
    const maxX = Math.max(CARD_MARGIN_PX, width - CARD_MARGIN_PX - w);
    const maxY = Math.max(CARD_MARGIN_PX, height - CARD_MARGIN_PX - h);
    const clamp = ([x, y]) => [Math.min(maxX, Math.max(CARD_MARGIN_PX, x)),
      Math.min(maxY, Math.max(CARD_MARGIN_PX, y))];
    // Just above, below, left and right of the box; then every free spot on a grid.
    const candidates = [[cx - w / 2, by1 - CARD_GAP_PX - h], [cx - w / 2, by2 + CARD_GAP_PX],
      [bx1 - CARD_GAP_PX - w, cy - h / 2], [bx2 + CARD_GAP_PX, cy - h / 2]].map(clamp);
    for (let y = CARD_MARGIN_PX; y <= maxY; y += CARD_GRID_PX) {{
      for (let x = CARD_MARGIN_PX; x <= maxX; x += CARD_GRID_PX) candidates.push([x, y]);
    }}
    let best = candidates[0], bestScore = Infinity;
    for (const [x, y] of candidates) {{
      if (placed.some((p) => x < p.x + p.width + CARD_GAP_PX && p.x < x + w + CARD_GAP_PX
        && y < p.y + p.height + CARD_GAP_PX && p.y < y + h + CARD_GAP_PX)) continue;
      const dx = Math.max(bx1 - (x + w), x - bx2, 0), dy = Math.max(by1 - (y + h), y - by2, 0);
      const covers = x < bx2 && bx1 < x + w && y < by2 && by1 < y + h;
      // Touching (within the gap) is as close as it gets; then the most centred above it.
      const score = Math.max(Math.hypot(dx, dy), CARD_GAP_PX) + (covers ? 1e4 : 0)
        + 1e-3 * Math.abs(x + w / 2 - cx) + 1e-4 * Math.max(0, y - by1);
      if (score < bestScore) {{ best = [x, y]; bestScore = score; }}
    }}
    const [x, y] = best;
    const card = {{key: item.key, x, y, width: w, height: h, to: item.anchor,
      from: [Math.min(x + w, Math.max(x, item.anchor[0])),
        Math.min(y + h, Math.max(y, item.anchor[1]))]}};
    placed.push(card);
    laid.set(i, card);
  }}
  const cards = items.map((_, i) => laid.get(i));
  cardLayouts.set(memo, cards);
  while (cardLayouts.size > 64) cardLayouts.delete(cardLayouts.keys().next().value);
  return cards;
}}
function cardAt(cards, x, y) {{
  const card = (cards || []).find((c) => x >= c.x && x <= c.x + c.width
    && y >= c.y && y <= c.y + c.height);
  return card ? card.key : 0;
}}
const CLICK_SLOP_PX = 4;
function isClick(down, up) {{
  return Math.hypot(up.x - down.x, up.y - down.y) <= CLICK_SLOP_PX;
}}
function orbitProject(points, view, width, height) {{
  if (!points.length) return [];
  const lo = [Infinity, Infinity, Infinity], hi = [-Infinity, -Infinity, -Infinity];
  for (const p of points) for (let k = 0; k < 3; k++) {{
    lo[k] = Math.min(lo[k], p[k]); hi[k] = Math.max(hi[k], p[k]);
  }}
  const centre = lo.map((l, k) => (l + hi[k]) / 2);
  const radius = Math.max(0.05, Math.hypot(hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]) / 2);
  const ca = Math.cos(view.azimuth), sa = Math.sin(view.azimuth);
  const ce = Math.cos(view.elevation), se = Math.sin(view.elevation);
  const scale = 0.9 * Math.min(width, height) / (2 * radius) * view.zoom;
  return points.map((p) => {{
    // Map frame: x right, y down, z ahead (camera convention). Turn about y, then tilt about x.
    const x = p[0] - centre[0], y = p[1] - centre[1], z = p[2] - centre[2];
    const xr = ca * x - sa * z, zr = sa * x + ca * z;
    const yr = ce * y - se * zr, depth = se * y + ce * zr;
    return [width / 2 + (xr + view.panX) * scale, height / 2 + (yr + view.panY) * scale, depth];
  }});
}}
"""
