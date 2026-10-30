"""Protocol codec tests: pure encode/decode, no Docker."""

import struct

import pytest

from surmap.slam.stream_protocol import (
    NEUTRAL_GREY,
    PROTOCOL_VERSION,
    GraphUpdate,
    KeyframeUpdate,
    Keypoint,
    OdomUpdate,
    ProtocolError,
    Ready,
    Rectification,
    decode_server_line,
    encode_hello,
    encode_pair,
)
from surmap.types import Vec3


def _header(blob: bytes) -> tuple[dict[str, object], bytes]:
    (length,) = struct.unpack("<I", blob[:4])
    import json

    return json.loads(blob[4 : 4 + length]), blob[4 + length :]


def test_hello_round_trip_header() -> None:
    # Given / When
    blob = encode_hello("cam0-yaml", "cam1-yaml", 376, 240, {"Rtabmap/DetectionRate": "2"})

    # Then
    header, rest = _header(blob)
    assert header["type"] == "hello"
    assert header["version"] == PROTOCOL_VERSION
    assert header["cam0_yaml"] == "cam0-yaml"
    assert header["width"] == 376
    assert rest == b""


def test_pair_encoding_is_binary_safe() -> None:
    # Given payloads containing newlines and zero bytes
    left = b"\x00\xff\nleft"
    right = b"right\x00"

    # When
    blob = encode_pair(7, 123, 4, 3, left, right, encoding="png")

    # Then header + two length-prefixed payloads survive intact
    header, rest = _header(blob)
    assert header["frame_id"] == 7 and header["encoding"] == "png"
    (llen,) = struct.unpack("<I", rest[:4])
    assert rest[4 : 4 + llen] == left
    rest = rest[4 + llen :]
    (rlen,) = struct.unpack("<I", rest[:4])
    assert rest[4 : 4 + rlen] == right


def test_decode_odom_lost_and_keyframe_and_graph() -> None:
    odom = decode_server_line(
        '{"type":"odom","frame_id":3,"t_ns":99,"pose":[1,2,3,0,0,0,1],"lost":false,"ms":12.5}'
    )
    assert isinstance(odom, OdomUpdate) and odom.pose is not None
    assert odom.pose.position == Vec3(1.0, 2.0, 3.0) and not odom.lost

    lost = decode_server_line(
        '{"type":"odom","frame_id":4,"t_ns":100,"pose":null,"lost":true,"ms":1.0}'
    )
    assert isinstance(lost, OdomUpdate) and lost.pose is None and lost.lost

    kf = decode_server_line(
        '{"type":"keyframe","node_id":2,"frame_id":3,"t_ns":99,'
        '"pose":[0,0,0,0,0,0,1],"points_local":[[1,2,3]]}'
    )
    assert isinstance(kf, KeyframeUpdate) and kf.points_local == (Vec3(1.0, 2.0, 3.0),)

    graph = decode_server_line(
        '{"type":"graph","poses":[{"node_id":2,"pose":[5,0,0,0,0,0,1]}],"final":true}'
    )
    assert isinstance(graph, GraphUpdate) and graph.final
    assert graph.poses[0][1].position.x == 5.0


def test_decode_rejects_malformed_and_version_mismatch() -> None:
    with pytest.raises(ProtocolError):
        decode_server_line("not json")
    with pytest.raises(ProtocolError):
        decode_server_line('{"type":"mystery"}')
    with pytest.raises(ProtocolError):
        decode_server_line('{"type":"ready","version":999}')
    with pytest.raises(ProtocolError):
        decode_server_line('{"type":"odom","frame_id":1}')


def test_protocol_version_is_three_for_keypoints_and_rectification() -> None:
    # Given / When a v3 sidecar announces itself without a rectification
    ready = decode_server_line('{"type":"ready","version":3}')

    # Then it is accepted, and v2 is a mismatch
    assert PROTOCOL_VERSION == 3
    assert ready == Ready(3)
    with pytest.raises(ProtocolError, match="version mismatch"):
        decode_server_line('{"type":"ready","version":2}')


def test_ready_carries_the_left_camera_rectification() -> None:
    # Given a ready line with the left camera's rectification
    line = (
        '{"type":"ready","version":3,"rectification":{'
        '"rotation":[1,0,0,0,1,0,0,0,1],"rectified":[200,200,100,80],'
        '"raw":[210,209,101,79],"distortion":[-0.28,0.07,0.0002,0.00002]}}'
    )

    # When it is decoded
    ready = decode_server_line(line)

    # Then the rectification is kept, value for value
    assert ready == Ready(
        3,
        Rectification(
            rotation=(1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0),
            rectified=(200.0, 200.0, 100.0, 80.0),
            raw=(210.0, 209.0, 101.0, 79.0),
            distortion=(-0.28, 0.07, 0.0002, 0.00002),
        ),
    )


def test_odometry_carries_the_frames_tracked_keypoints() -> None:
    # Given an odom line with two inlier keypoints as [word_id, u, v, depth]
    line = (
        '{"type":"odom","frame_id":3,"t_ns":99,"pose":[0,0,0,0,0,0,1],"lost":false,'
        '"ms":12.5,"keypoints":[[41,10.5,20.25,1.5],[42,30,40,4]]}'
    )

    # When it is decoded
    odom = decode_server_line(line)

    # Then each keypoint keeps its word id, rectified pixel and depth
    assert isinstance(odom, OdomUpdate)
    assert odom.keypoints == (Keypoint(41, 10.5, 20.25, 1.5), Keypoint(42, 30.0, 40.0, 4.0))


def test_odometry_without_keypoints_has_none() -> None:
    # Given / When an odom line without a keypoints field is decoded
    odom = decode_server_line(
        '{"type":"odom","frame_id":3,"t_ns":99,"pose":null,"lost":true,"ms":1.0}'
    )

    # Then it carries no keypoints
    assert isinstance(odom, OdomUpdate) and odom.keypoints == ()


def test_keyframe_points_carry_their_colour() -> None:
    # Given a keyframe whose points carry r, g, b after x, y, z
    line = (
        '{"type":"keyframe","node_id":2,"frame_id":3,"t_ns":99,'
        '"pose":[0,0,0,0,0,0,1],"points_local":[[1,2,3,10,20,30],[4,5,6,200,200,200]]}'
    )

    # When it is decoded
    keyframe = decode_server_line(line)

    # Then each point keeps its colour, in order
    assert isinstance(keyframe, KeyframeUpdate)
    assert keyframe.points_local == (Vec3(1.0, 2.0, 3.0), Vec3(4.0, 5.0, 6.0))
    assert keyframe.colors == ((10, 20, 30), (200, 200, 200))


def test_keyframe_points_without_colour_decode_as_neutral_grey() -> None:
    # Given a keyframe whose points are bare x, y, z
    line = (
        '{"type":"keyframe","node_id":2,"frame_id":3,"t_ns":99,'
        '"pose":[0,0,0,0,0,0,1],"points_local":[[1,2,3]]}'
    )

    # When it is decoded
    keyframe = decode_server_line(line)

    # Then the point gets the neutral grey
    assert isinstance(keyframe, KeyframeUpdate)
    assert keyframe.colors == (NEUTRAL_GREY,)
