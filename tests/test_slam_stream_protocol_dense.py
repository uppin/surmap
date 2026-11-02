"""Wire protocol v5: the region rig on `ready` and journalled `dense` lines."""

import base64
import json
import struct

import numpy as np
import pytest

from surmap.slam.dense import ChannelRig, DenseFrame, RegionRig, encode_disparity
from surmap.slam.stream_protocol import (
    PROTOCOL_VERSION,
    ProtocolError,
    Ready,
    decode_server_line,
    encode_hello,
)
from surmap.types import Pose, Vec3

IDENTITY = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]
K = [229.0, 0.0, 183.5, 0.0, 228.5, 124.0, 0.0, 0.0, 1.0]
LEFT_P = [229.0, 0.0, 183.5, 0.0, 0.0, 229.0, 124.0, 0.0, 0.0, 0.0, 1.0, 0.0]
RIGHT_P = [229.0, 0.0, 183.5, -25.2, 0.0, 229.0, 124.0, 0.0, 0.0, 0.0, 1.0, 0.0]
DISTORTION = [-0.28, 0.07, 0.0002, 0.00002, 0.0]


def a_region_rig_message() -> dict[str, object]:
    return {
        "size": [376, 240],
        "baseline": 0.11,
        "max_depth_m": 30.0,
        "channels": [
            {"K": K, "D": DISTORTION, "R": IDENTITY, "P": LEFT_P},
            {"K": K, "D": DISTORTION, "R": IDENTITY, "P": RIGHT_P},
        ],
    }


def a_disparity_png() -> bytes:
    return encode_disparity(np.full((240, 376), 40, np.uint16))


def a_dense_line(png_b64: str) -> str:
    return json.dumps(
        {
            "type": "dense",
            "frame_id": 12,
            "t_ns": 1_200_000_000,
            "channel": 0,
            "to_map": [1.0, 2.0, 3.0, 0.0, 0.0, 0.0, 1.0],
            "disparity_png": png_b64,
        }
    )


def hello_of(frame: bytes) -> dict[str, object]:
    (length,) = struct.unpack("<I", frame[:4])
    hello: dict[str, object] = json.loads(frame[4 : 4 + length])
    return hello


def test_the_dense_journal_is_protocol_version_5() -> None:
    assert PROTOCOL_VERSION == 5


def test_the_hello_asks_for_the_dense_journal_only_when_wanted() -> None:
    # When a hello is built with and without the journal
    journalled = hello_of(encode_hello("c0", "c1", 376, 240, {}, dense_journal=True))
    plain = hello_of(encode_hello("c0", "c1", 376, 240, {}))

    # Then only the journalled one asks the sidecar for dense lines
    assert journalled["dense_journal"] is True
    assert plain["dense_journal"] is False


def test_ready_carries_the_rig_regions_are_answered_with() -> None:
    # Given a v5 ready line with its region rig
    line = json.dumps(
        {"type": "ready", "version": PROTOCOL_VERSION, "region_rig": a_region_rig_message()}
    )

    # When it is decoded
    message = decode_server_line(line)

    # Then the rig is there, channel by channel
    assert isinstance(message, Ready)
    assert message.region_rig == RegionRig(
        width=376,
        height=240,
        baseline_m=0.11,
        max_depth_m=30.0,
        channels=(
            ChannelRig(tuple(K), tuple(DISTORTION), tuple(IDENTITY), tuple(LEFT_P)),
            ChannelRig(tuple(K), tuple(DISTORTION), tuple(IDENTITY), tuple(RIGHT_P)),
        ),
    )


def test_a_dense_line_is_the_frames_disparity_with_the_transform_it_was_placed_with() -> None:
    # Given the sidecar's dense line for frame 12
    png = a_disparity_png()

    # When it is decoded
    message = decode_server_line(a_dense_line(base64.b64encode(png).decode()))

    # Then it is that frame's journal entry, PNG bytes untouched
    assert message == DenseFrame(
        frame_id=12,
        t_ns=1_200_000_000,
        channel=0,
        to_map=Pose(Vec3(1.0, 2.0, 3.0), (0.0, 0.0, 0.0, 1.0)),
        disparity_png=png,
    )


def test_a_dense_line_whose_disparity_is_not_base64_is_rejected() -> None:
    with pytest.raises(ProtocolError, match="disparity_png"):
        decode_server_line(a_dense_line("not base64 at all!"))
