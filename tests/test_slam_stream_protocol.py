"""Protocol codec tests: pure encode/decode, no Docker."""

import struct

import pytest

from surmap.slam.stream_protocol import (
    PROTOCOL_VERSION,
    GraphUpdate,
    KeyframeUpdate,
    OdomUpdate,
    ProtocolError,
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
