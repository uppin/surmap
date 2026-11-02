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
