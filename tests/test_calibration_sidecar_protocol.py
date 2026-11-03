"""The OpenCV sidecar's line protocol, on paths that need no OpenCV."""

import base64

import pytest

from surmap.calibration.board import CheckerboardSpec
from surmap.calibration.opencv_sidecar import OpenCvSidecarVision, handle_request
from surmap.calibration.port import EncodedFrame, UnreadableFrame


def a_short_raw_frame_request() -> dict[str, object]:
    return {
        "op": "detect",
        "width": 640,
        "height": 480,
        "encoding": "raw_rgb",
        "data_b64": base64.b64encode(b"\x00" * 12).decode(),
        "cols": 9,
        "rows": 6,
        "square_size_m": 0.04,
    }


def test_a_frame_of_the_wrong_byte_count_is_answered_unreadable() -> None:
    # When the sidecar is handed 12 bytes for a 640x480 RGB frame
    reply = handle_request(a_short_raw_frame_request())

    # Then it names the frame as unreadable rather than failing the sidecar
    assert "unreadable" in reply
    assert "error" not in reply


async def test_the_client_raises_unreadable_frame_for_an_undecodable_frame() -> None:
    # Given a spawned sidecar
    vision = OpenCvSidecarVision()
    try:
        # Then a short frame raises the per-frame error, not CalibrationUnavailable
        with pytest.raises(UnreadableFrame, match="bytes"):
            await vision.detect(
                EncodedFrame(
                    frame_id=1, width=640, height=480, encoding="raw_rgb", data=b"\x00" * 12
                ),
                board=CheckerboardSpec(9, 6, 0.04),
                max_scale=1,
            )
    finally:
        await vision.close()
