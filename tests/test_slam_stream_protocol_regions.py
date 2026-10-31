"""Protocol v4 region requests: pure encode/decode, no Docker."""

import pytest

from surmap.slam.regions import RegionQuery, RegionResult, RegionStatus
from surmap.slam.stream_protocol import (
    PROTOCOL_VERSION,
    ProtocolError,
    decode_server_line,
    encode_hello,
    encode_region,
)
from surmap.types import Vec3
from tests.test_slam_stream_protocol import _header


def test_the_protocol_is_version_four_for_region_requests() -> None:
    # Given / When / Then region requests are a v4 addition
    assert PROTOCOL_VERSION == 4


def test_hello_carries_how_long_frames_stay_queryable() -> None:
    # Given / When a hello asking frames to stay queryable for 12.5 s
    blob = encode_hello("cam0", "cam1", 376, 240, {}, region_buffer_s=12.5)

    # Then the sidecar is told the ring length
    header, _ = _header(blob)
    assert header["region_buffer_s"] == 12.5


def test_hello_keeps_frames_queryable_for_ten_seconds_by_default() -> None:
    # Given / When
    header, _ = _header(encode_hello("cam0", "cam1", 376, 240, {}))

    # Then
    assert header["region_buffer_s"] == 10.0


def test_a_region_request_names_frame_channel_image_size_and_polygon() -> None:
    # Given a polygon SAM drew on the right image of frame 42
    query = RegionQuery(9, 42, 1, 376, 240, ((10.0, 20.0), (30.0, 20.0), (30.0, 40.0)))

    # When it is encoded for the sidecar
    header, rest = _header(encode_region(query))

    # Then it is a framed header with no payload
    assert header == {
        "type": "region",
        "query_id": 9,
        "frame_id": 42,
        "channel": 1,
        "width": 376,
        "height": 240,
        "polygon": [[10.0, 20.0], [30.0, 20.0], [30.0, 40.0]],
    }
    assert rest == b""


def test_a_region_answer_decodes_to_map_frame_points() -> None:
    # Given the sidecar's answer to query 9
    line = (
        '{"type":"region","query_id":9,"frame_id":42,"channel":1,"status":"ok",'
        '"points":[[1.0,2.0,3.0],[1.5,2.0,3.25]]}'
    )

    # When it is decoded
    result = decode_server_line(line)

    # Then it is that query's result with its points
    assert result == RegionResult(
        9, 42, 1, RegionStatus.OK, (Vec3(1.0, 2.0, 3.0), Vec3(1.5, 2.0, 3.25))
    )


@pytest.mark.parametrize(
    ("wire", "status"),
    [
        ("expired", RegionStatus.FRAME_EXPIRED),
        ("no_pose", RegionStatus.NO_POSE),
        ("invalid", RegionStatus.INVALID_QUERY),
    ],
)
def test_a_region_answer_without_points_keeps_its_status(wire: str, status: RegionStatus) -> None:
    # Given / When an answer that could not place the region
    result = decode_server_line(
        f'{{"type":"region","query_id":1,"frame_id":2,"channel":0,"status":"{wire}","points":[]}}'
    )

    # Then the reason survives and no point is invented
    assert isinstance(result, RegionResult)
    assert result.status is status and result.points == ()


def test_a_region_answer_with_an_unknown_status_is_rejected() -> None:
    # Given / When / Then
    with pytest.raises(ProtocolError):
        decode_server_line(
            '{"type":"region","query_id":1,"frame_id":2,"channel":0,"status":"maybe","points":[]}'
        )
