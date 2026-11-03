"""The frame tool — `get_frame` — and the crop helpers behind it.

Integration tests over `DemoWorkspace` on recorded runs of the tiny EuRoC scene (752 x 480
frames in the scene cache, 376 x 240 display JPEGs in the history), plus unit tests of
`surmap.agent.tools.frames`. Image sizes are read back with Pillow.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from connectrpc.code import Code
from connectrpc.errors import ConnectError
from PIL import Image

from surmap.agent.proto import survey_tools_pb2 as pb
from surmap.agent.tools.frames import crop_box_for_object, frame_image
from surmap.agent.tools.handlers import OBJECT_CROP_PAD_PX, get_frame
from tests.agent_tool_fakes import (
    TINY_DISPLAY_SIZE,
    TINY_FULL_SIZE,
    ToolRig,
    a_cube,
    a_recorded_run,
    a_run_of_a_retired_scene,
    a_tool_rig,
    centred_box,
    image_format,
    image_size,
    with_an_object,
)

SEEN_BOX = "obj_1"  # tracked as SAM track 1: the fake SAM's centred box on every frame


def a_run_with_a_seen_object(rig: ToolRig) -> str:
    run_id = a_recorded_run(rig)
    with_an_object(rig, run_id, 1, a_cube(centre=(0.0, 0.0, 3.0), half=0.3), track_id=1)
    return run_id


def a_png(size: tuple[int, int] = (200, 100)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, (30, 120, 200)).save(buffer, format="PNG")
    return buffer.getvalue()


def size_of(response: pb.GetFrameResponse) -> tuple[int, int]:
    return (response.width, response.height)


def object_crop_size() -> tuple[float, float]:
    """The fake SAM's centred box on the full frame, before padding."""
    x0, y0, x1, y1 = centred_box(TINY_FULL_SIZE)
    return (x1 - x0, y1 - y0)


# --- which frame ----------------------------------------------------------------------------


async def test_get_frame_returns_the_full_resolution_frame_when_the_cache_has_it(
    tmp_path: Path,
) -> None:
    # Given a recorded run of a scene still in the cache
    with a_tool_rig(tmp_path) as rig:
        run_id = a_recorded_run(rig)

        # When the agent asks for its first frame
        response = await get_frame(pb.GetFrameRequest(run_id=run_id, frame_index=0), rig.workspace)

    # Then it is the 752 x 480 original, as a JPEG
    assert (response.source, size_of(response)) == (pb.FULL, TINY_FULL_SIZE)
    assert (response.media_type, image_format(response.image)) == ("image/jpeg", "JPEG")


async def test_get_frame_falls_back_to_the_display_jpeg_when_the_cache_does_not(
    tmp_path: Path,
) -> None:
    # Given a recorded run of a scene no longer cached
    with a_tool_rig(tmp_path) as rig:
        run_id = a_run_of_a_retired_scene(rig, frames=3)

        # When the agent asks for its first frame
        response = await get_frame(pb.GetFrameRequest(run_id=run_id), rig.workspace)

    # Then it is the run's 376 x 240 display frame
    assert (response.source, size_of(response)) == (pb.DISPLAY, TINY_DISPLAY_SIZE)
    assert image_size(response.image) == TINY_DISPLAY_SIZE


async def test_get_frame_with_no_frame_chosen_returns_the_run_s_first(tmp_path: Path) -> None:
    # Given a recorded run of the tiny scene
    with a_tool_rig(tmp_path) as rig:
        run_id = a_recorded_run(rig)

        # When the agent asks for a frame without choosing one
        response = await get_frame(pb.GetFrameRequest(run_id=run_id), rig.workspace)

    # Then it is frame 1, at t_ns 100
    assert (response.frame_id, response.t_ns) == (1, 100)


async def test_get_frame_picks_a_frame_by_its_id(tmp_path: Path) -> None:
    # Given a recorded run of the tiny scene
    with a_tool_rig(tmp_path) as rig:
        run_id = a_recorded_run(rig)

        # When the agent asks for frame 2
        response = await get_frame(pb.GetFrameRequest(run_id=run_id, frame_id=2), rig.workspace)

    # Then it is frame 2, at t_ns 200
    assert (response.frame_id, response.t_ns) == (2, 200)


async def test_get_frame_picks_the_frame_nearest_a_timestamp(tmp_path: Path) -> None:
    # Given a recorded run with frames at t_ns 100 and 200
    with a_tool_rig(tmp_path) as rig:
        run_id = a_recorded_run(rig)

        # When the agent asks for the frame at t_ns 180
        response = await get_frame(pb.GetFrameRequest(run_id=run_id, t_ns=180), rig.workspace)

    # Then it is the frame at 200
    assert (response.frame_id, response.t_ns) == (2, 200)


async def test_get_frame_refuses_an_index_past_the_run_s_end(tmp_path: Path) -> None:
    # Given a recorded run of two frames
    with a_tool_rig(tmp_path) as rig:
        run_id = a_recorded_run(rig)

        # When the agent asks for the sixth
        with pytest.raises(ConnectError) as refused:
            await get_frame(pb.GetFrameRequest(run_id=run_id, frame_index=5), rig.workspace)

    # Then the call fails as not found
    assert refused.value.code == Code.NOT_FOUND


async def test_get_frame_refuses_a_run_the_history_does_not_have(tmp_path: Path) -> None:
    # Given an empty history
    with a_tool_rig(tmp_path) as rig:
        # When the agent asks for a frame of a run
        with pytest.raises(ConnectError) as refused:
            await get_frame(pb.GetFrameRequest(run_id="no-such-run"), rig.workspace)

    # Then the call fails as not found
    assert refused.value.code == Code.NOT_FOUND


# --- crops and size -------------------------------------------------------------------------


async def test_get_frame_crops_to_a_pixel_box(tmp_path: Path) -> None:
    # Given a recorded run of the tiny scene
    with a_tool_rig(tmp_path) as rig:
        run_id = a_recorded_run(rig)

        # When the agent crops its first frame to a 100 x 50 box
        response = await get_frame(
            pb.GetFrameRequest(run_id=run_id, crop_box=pb.PixelBox(x0=10, y0=20, x1=110, y1=70)),
            rig.workspace,
        )

    # Then the image is that box
    assert size_of(response) == (100, 50) == image_size(response.image)


async def test_get_frame_pads_a_crop_but_never_past_the_frame_s_edge(tmp_path: Path) -> None:
    # Given a recorded run of the tiny scene
    with a_tool_rig(tmp_path) as rig:
        run_id = a_recorded_run(rig)

        # When the agent crops to the top-left 50 x 50 corner with 16 px of padding
        response = await get_frame(
            pb.GetFrameRequest(
                run_id=run_id, crop_box=pb.PixelBox(x0=0, y0=0, x1=50, y1=50), pad_px=16
            ),
            rig.workspace,
        )

    # Then the crop grows only to the right and down
    assert size_of(response) == (66, 66)


async def test_get_frame_crops_to_an_object_s_mask_box_with_its_padding(tmp_path: Path) -> None:
    # Given a recorded run with an object SAM outlined in the middle of every frame
    with a_tool_rig(tmp_path) as rig:
        run_id = a_run_with_a_seen_object(rig)

        # When the agent crops frame 1 to that object
        response = await get_frame(
            pb.GetFrameRequest(run_id=run_id, frame_id=1, crop_object_id=SEEN_BOX), rig.workspace
        )

    # Then the image holds the object's whole box on the full frame, plus the default padding
    box_w, box_h = object_crop_size()
    pad = 2 * OBJECT_CROP_PAD_PX
    assert box_w + pad - 2 <= response.width <= box_w + pad + 2
    assert box_h + pad - 2 <= response.height <= box_h + pad + 2


async def test_get_frame_crops_to_an_object_on_its_first_frame_when_none_is_chosen(
    tmp_path: Path,
) -> None:
    # Given a recorded run with an object SAM outlined on both frames
    with a_tool_rig(tmp_path) as rig:
        run_id = a_run_with_a_seen_object(rig)

        # When the agent crops to the object without choosing a frame
        response = await get_frame(
            pb.GetFrameRequest(run_id=run_id, crop_object_id=SEEN_BOX), rig.workspace
        )

    # Then the crop is taken from frame 1
    assert response.frame_id == 1


async def test_get_frame_refuses_to_crop_to_an_object_the_run_does_not_have(
    tmp_path: Path,
) -> None:
    # Given a recorded run with one object
    with a_tool_rig(tmp_path) as rig:
        run_id = a_run_with_a_seen_object(rig)

        # When the agent crops to obj_99
        with pytest.raises(ConnectError) as refused:
            await get_frame(
                pb.GetFrameRequest(run_id=run_id, crop_object_id="obj_99"), rig.workspace
            )

    # Then the call fails as not found
    assert refused.value.code == Code.NOT_FOUND


async def test_get_frame_downscales_to_max_side_keeping_the_aspect(tmp_path: Path) -> None:
    # Given a recorded run of 752 x 480 frames
    with a_tool_rig(tmp_path) as rig:
        run_id = a_recorded_run(rig)

        # When the agent asks for its first frame at most 200 px on a side
        response = await get_frame(pb.GetFrameRequest(run_id=run_id, max_side=200), rig.workspace)

    # Then the frame is 200 x 128
    assert size_of(response) == (200, 128) == image_size(response.image)


# --- frame_image ----------------------------------------------------------------------------


def test_frame_image_crops_to_the_box() -> None:
    # Given a 200 x 100 image
    image = a_png((200, 100))

    # When it is cropped to a 60 x 40 box
    encoded = frame_image(image, crop=(20.0, 30.0, 80.0, 70.0))

    # Then the JPEG is 60 x 40
    assert (encoded.width, encoded.height, encoded.media_type) == (60, 40, "image/jpeg")


def test_frame_image_without_a_crop_keeps_the_whole_image() -> None:
    # Given a 200 x 100 image
    image = a_png((200, 100))

    # When it is encoded whole
    encoded = frame_image(image)

    # Then the JPEG is the whole image
    assert image_size(encoded.data) == (200, 100)


def test_frame_image_clamps_a_padded_crop_to_the_image() -> None:
    # Given a 200 x 100 image
    image = a_png((200, 100))

    # When the bottom-right 20 x 20 corner is cropped with 10 px of padding
    encoded = frame_image(image, crop=(180.0, 80.0, 200.0, 100.0), pad_px=10)

    # Then the crop grows only up and to the left
    assert (encoded.width, encoded.height) == (30, 30)


def test_frame_image_downscales_the_longer_side_to_max_side() -> None:
    # Given a 200 x 100 image
    image = a_png((200, 100))

    # When it is limited to 50 px on a side
    encoded = frame_image(image, max_side=50)

    # Then it is 50 x 25
    assert (encoded.width, encoded.height) == (50, 25)


def test_frame_image_never_enlarges_an_image_within_max_side() -> None:
    # Given a 200 x 100 image
    image = a_png((200, 100))

    # When it is limited to 1000 px on a side
    encoded = frame_image(image, max_side=1000)

    # Then it keeps its size
    assert (encoded.width, encoded.height) == (200, 100)


def test_frame_image_refuses_a_crop_outside_the_image() -> None:
    # Given a 200 x 100 image
    image = a_png((200, 100))

    # When it is cropped to a box entirely past its right edge
    # Then the crop is refused
    with pytest.raises(ValueError, match="crop"):
        frame_image(image, crop=(300.0, 10.0, 350.0, 50.0))


# --- crop_box_for_object --------------------------------------------------------------------


def test_an_object_box_from_the_display_frame_scales_to_the_full_frame() -> None:
    # Given a mask box measured on the 376 x 240 display frame
    box = (131.6, 84.0, 244.4, 156.0)

    # When it is carried over to the 752 x 480 original
    scaled = crop_box_for_object(box, measured_on=TINY_DISPLAY_SIZE, image_size=TINY_FULL_SIZE)

    # Then every coordinate doubles
    assert scaled == pytest.approx((263.2, 168.0, 488.8, 312.0))


def test_an_object_box_on_the_same_size_image_is_unchanged() -> None:
    # Given a mask box measured on the display frame
    box = (131.6, 84.0, 244.4, 156.0)

    # When it is carried over to the display frame itself
    scaled = crop_box_for_object(box, measured_on=TINY_DISPLAY_SIZE, image_size=TINY_DISPLAY_SIZE)

    # Then it is the same box
    assert scaled == pytest.approx(box)
