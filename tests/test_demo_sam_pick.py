"""Demo: the SAM view shares the 3D pane's selection — hover a mask, see its object in 3D."""

import json
import subprocess
from pathlib import Path

from surmap.demo.sam_depth import SAM_DEPTH_SCRIPT
from surmap.demo.view_math import VIEW_HELPERS
from tests.test_demo_object_feed import NODE, STUB_DOM, a_console_page, needs_node

SQUARE = "[[0, 0], [10, 0], [10, 10], [0, 10]]"
INNER = "[[2, 2], [6, 2], [6, 6], [2, 6]]"


def run_js(prelude: str, expression: str) -> object:
    assert NODE is not None
    script = prelude + f"\nconsole.log(JSON.stringify({expression}));\n"
    done = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=30)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


@needs_node
def test_a_point_is_inside_a_mask_polygon_only_within_its_outline() -> None:
    inside = run_js(
        VIEW_HELPERS.format(),
        f"[polygonContains({SQUARE}, 5, 5), polygonContains({SQUARE}, 12, 5),"
        f" polygonContains({SQUARE}, 5, -1)]",
    )
    assert inside == [True, False, False]


@needs_node
def test_the_hovered_mask_is_the_smallest_one_under_the_cursor() -> None:
    # Given a car (track 4) with a smaller mask (track 9) inside its outline
    objects = f"[{{track_id: 4, mask_polygon: {SQUARE}}}, {{track_id: 9, mask_polygon: {INNER}}}]"

    # When the cursor is over the inner mask, the outer only, and neither
    picks = run_js(
        VIEW_HELPERS.format(),
        f"[maskAt({objects}, 3, 3), maskAt({objects}, 8, 8), maskAt({objects}, 20, 20)]",
    )

    # Then the inner one wins where they overlap
    assert picks == [9, 4, 0]


# The SAM pane script over a stub page: frame 13 shows car track 8 (assigned to
# surface 27) and track 5 (assigned to nothing yet).
SAM_PAGE = (
    STUB_DOM
    + "const samCanvas = null, samView = null; let cloudSelected = 0;"
    + "function drawSamObjects() {}\n"
    + VIEW_HELPERS.format()
    + SAM_DEPTH_SCRIPT.format()
    + "\nnoteSurfaces({frame_id: 13, surfaces: [{surface_id: 27, track_id: 8}]});"
    + f"\nsamLast = {{data: {{frame_id: 13, objects: [{{track_id: 8, mask_polygon: {SQUARE}}},"
    + " {track_id: 5, mask_polygon: [[20, 0], [30, 0], [30, 10], [20, 10]]}]}, image: null};"
)


@needs_node
def test_hovering_a_mask_names_the_surface_its_object_became() -> None:
    picks = run_js(SAM_PAGE, "[samSurfaceAt(5, 5), samSurfaceAt(25, 5), samSurfaceAt(50, 50)]")
    # Track 8's surface; track 5 has no surface yet; outside every mask
    assert picks == [27, 0, 0]


@needs_node
def test_a_surface_selected_anywhere_outlines_its_masks_on_the_sam_frame() -> None:
    outlined = run_js(SAM_PAGE, "(() => { cloudSelected = 27; return samSelectedTracks(); })()")
    assert outlined == [8]


@needs_node
def test_masks_of_another_frame_do_not_link_to_this_frames_surfaces() -> None:
    picks = run_js(SAM_PAGE, "(() => { samLast.data.frame_id = 14; return samSurfaceAt(5, 5); })()")
    assert picks == 0


def test_the_sam_view_is_wired_to_the_shared_selection(tmp_path: Path) -> None:
    with a_console_page(tmp_path) as page:
        script = page.split("<script>", 1)[1]
    move = script.split("samCanvas.addEventListener('pointermove'", 1)[1].split("\n});", 1)[0]
    up = script.split("samCanvas.addEventListener('pointerup'", 1)[1].split("\n});", 1)[0]
    # Hovering a mask selects its surface; a click (not a drag) opens it in the feed
    assert "samSurfaceAt(" in move and "setCloudSelection(" in move
    assert "isClick(" in up and "focusFeedItem(" in up
    # Surface events feed the mapping, and any selection change redraws the SAM view
    assert "noteSurfaces(JSON.parse(event.data))" in script
    refresh = script.split("function refreshCloudSelection()", 1)[1].split("\n}", 1)[0]
    assert "redrawSam()" in refresh
