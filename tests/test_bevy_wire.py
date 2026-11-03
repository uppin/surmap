"""The browser-to-bridge wire format, pinned by the shared goldens."""

import json
import struct
from pathlib import Path

import pytest
from surmap.simulation.bevy_wire import (
    BevyHello,
    BevyPair,
    BevyWireError,
    BridgeStatus,
    decode_bevy_message,
    encode_status,
)

from surmap.types import Vec3

GOLDENS = Path(__file__).parent / "fixtures" / "bevy_sim_wire"


def a_message(header: bytes, payload: bytes = b"") -> bytes:
    return struct.pack("<I", len(header)) + header + payload


def test_the_hello_golden_decodes_into_the_calibration_and_its_objects() -> None:
    # Given the hello the browser sends when a session opens
    message = (GOLDENS / "hello.bin").read_bytes()

    # When the bridge decodes it
    decoded = decode_bevy_message(message)

    # Then it carries the rig as a calibration spec and the car as a ground-truth box
    assert isinstance(decoded, BevyHello)
    assert decoded.calibration_id == "bevy-sitl-poc-v1"
    assert decoded.rate_hz == pytest.approx(10.0)
    assert decoded.calibration.calibration_id == "bevy-sitl-poc-v1"
    assert decoded.calibration.rate_hz == pytest.approx(10.0)
    assert (decoded.calibration.width, decoded.calibration.height) == (640, 480)
    assert decoded.calibration.fx == pytest.approx(381.36)
    assert decoded.calibration.baseline_m == pytest.approx(0.07)
    assert len(decoded.objects) == 1
    assert decoded.objects[0].id == "car-1"
    assert decoded.objects[0].kind == "car"
    assert decoded.objects[0].min_enu == Vec3(1.0, 2.0, 0.0)
    assert decoded.objects[0].max_enu == Vec3(3.0, 6.5, 1.5)


def test_the_pair_golden_decodes_into_a_frame_with_its_rig_pose() -> None:
    # Given one 4x2 stereo pair from the shared goldens
    message = (GOLDENS / "pair.bin").read_bytes()

    # When the bridge decodes it
    decoded = decode_bevy_message(message)

    # Then it carries the frame, the rig pose in ENU and both grey8 payloads
    assert isinstance(decoded, BevyPair)
    assert (decoded.frame_id, decoded.t_ns) == (7, 700_000_000)
    assert (decoded.width, decoded.height, decoded.encoding) == (4, 2, "gray8")
    assert decoded.pose_enu.position == Vec3(1.0, 3.0, 2.0)
    assert decoded.pose_enu.orientation_xyzw == (0.0, 0.0, 0.0, 1.0)
    assert decoded.left_data == bytes(range(8))
    assert decoded.right_data == bytes(range(8, 16))


def test_a_message_shorter_than_its_header_length_is_refused() -> None:
    # Given two bytes, too few to hold the little-endian header length
    message = b"\x05\x00"

    # When the bridge decodes it, Then the wire error is raised
    with pytest.raises(BevyWireError):
        decode_bevy_message(message)


def test_a_header_that_is_not_json_is_refused() -> None:
    # Given a framed header that is not JSON at all
    message = a_message(b"not json")

    # When the bridge decodes it, Then the wire error is raised
    with pytest.raises(BevyWireError):
        decode_bevy_message(message)


def test_a_message_of_an_unknown_type_is_refused() -> None:
    # Given a well-framed header naming a message type that does not exist
    message = a_message(b'{"type":"mystery"}')

    # When the bridge decodes it, Then the wire error is raised
    with pytest.raises(BevyWireError):
        decode_bevy_message(message)


def test_a_pair_whose_payload_is_shorter_than_its_frame_is_refused() -> None:
    # Given the pair golden with its last payload byte cut off
    message = (GOLDENS / "pair.bin").read_bytes()[:-1]

    # When the bridge decodes it, Then the wire error is raised
    with pytest.raises(BevyWireError):
        decode_bevy_message(message)


def test_the_status_reply_is_one_compact_json_text_message() -> None:
    # Given the bridge state after two frames, one of them posed
    status = BridgeStatus(frames=2, posed=1, lost=False, keyframes=1, dropped=0)

    # When the bridge encodes its reply
    text = encode_status(status)

    # Then it is the exact status shape the page renders
    assert text == '{"type":"status","frames":2,"posed":1,"lost":false,"keyframes":1,"dropped":0}'
    assert json.loads(text) == {
        "type": "status",
        "frames": 2,
        "posed": 1,
        "lost": False,
        "keyframes": 1,
        "dropped": 0,
    }
