"""Picking in the 3D pane: hover names and selects a surface, a click opens it in the feed.

The server sends every cloud image with its id image (`cloud_ids_png`,
`surmap.demo.cloud_view.render_cloud_ids`), so the page knows which
surface each pixel shows without any geometry of its own:

- Hovering finds the surface nearest the cursor (`surfaceIdNear`, within
  a few image pixels, since surfaces are drawn as sparse splats), shows
  `label #id · points · static/moving` in a tooltip, and tints every
  pixel of that surface (`selectionMask`) as selected.
- A click (`isClick`: released where it was pressed, so a drag still
  orbits) scrolls the feed to that surface's card and highlights it
  (`focusFeedItem`, `object_feed.py`).
- Hovering a feed card selects its surface in the pane.

Spliced into the page before the server formats it, so its braces stay
doubled for str.format.
"""

from __future__ import annotations

CLOUD_PICK_MARKUP = (
    '<div class="cloud-tip" id="cloud-tip" hidden style="position: absolute;'
    " pointer-events: none; background: rgba(16, 18, 21, 0.92); color: #e8f8ff;"
    " border: 1px solid #ffd23c; border-radius: 4px; padding: 2px 6px;"
    ' font-size: 12px; white-space: nowrap;"></div>'
)

CLOUD_PICK_SCRIPT = """// --- 3D pane picking: the id image under the cursor ---
const cloudTip = $('cloud-tip');
const PICK_RADIUS_PX = 4;
let cloudIds = null, cloudSelected = 0, cloudSelection = null;
if (cloudTip) $('cloud-wrap').style.position = 'relative';
function setCloudIds(idsPng) {{
  if (!idsPng) {{ cloudIds = null; refreshCloudSelection(); return; }}
  const image = new Image();
  image.onload = () => {{
    const canvas = document.createElement('canvas');
    canvas.width = image.width; canvas.height = image.height;
    const ctx = canvas.getContext('2d', {{willReadFrequently: true}});
    ctx.drawImage(image, 0, 0);
    cloudIds = ctx.getImageData(0, 0, image.width, image.height);
    refreshCloudSelection();
  }};
  image.src = 'data:image/png;base64,' + idsPng;
}}
function pickAt(event) {{
  if (!cloudIds || !cloudCanvas) return 0;
  const rect = cloudCanvas.getBoundingClientRect();
  const x = (event.clientX - rect.left) / rect.width * cloudIds.width;
  const y = (event.clientY - rect.top) / rect.height * cloudIds.height;
  const radius = Math.max(1, Math.round(PICK_RADIUS_PX * cloudIds.width / rect.width));
  return surfaceIdNear(cloudIds.data, cloudIds.width, cloudIds.height, x, y, radius);
}}
function refreshCloudSelection() {{
  cloudSelection = null;
  if (cloudSelected && cloudIds) {{
    const mask = selectionMask(cloudIds.data, cloudSelected);
    cloudSelection = document.createElement('canvas');
    cloudSelection.width = cloudIds.width; cloudSelection.height = cloudIds.height;
    cloudSelection.getContext('2d').putImageData(
      new ImageData(mask, cloudIds.width, cloudIds.height), 0, 0);
  }}
  drawCloud();
}}
function setCloudSelection(surfaceId, event) {{
  if (surfaceId !== cloudSelected) {{ cloudSelected = surfaceId; refreshCloudSelection(); }}
  if (cloudCanvas) cloudCanvas.style.cursor = surfaceId ? 'pointer' : '';
  if (!cloudTip) return;
  if (!surfaceId || !event) {{ cloudTip.hidden = true; return; }}
  const item = feedItems.get(surfaceId);
  cloudTip.textContent = item
    ? `${{item.label}} #${{surfaceId}} · ${{item.total}} pts · `
      + `${{item.moving ? 'moving' : 'static'}} — click to open in the feed`
    : `surface #${{surfaceId}}`;
  const wrap = $('cloud-wrap').getBoundingClientRect();
  cloudTip.hidden = false;
  // Right of the cursor, or left of it where it would run off the pane.
  const x = event.clientX - wrap.left, width = cloudTip.offsetWidth;
  cloudTip.style.left = `${{x + 14 + width > wrap.width ? Math.max(0, x - 14 - width) : x + 14}}px`;
  cloudTip.style.top = `${{event.clientY - wrap.top + 10}}px`;
}}
function drawCloudSelection(ctx, w, h) {{
  if (cloudSelection) ctx.drawImage(cloudSelection, 0, 0, w, h);
}}
"""
