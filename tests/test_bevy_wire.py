"""The browser-to-bridge wire format, pinned by the shared goldens."""

import hashlib
import json
import struct
from pathlib import Path

import pytest

from surmap.simulation.bevy_wire import (
    BevyHello,
    BevyPair,
    BevyWireError,
    BridgeStatus,
    FrameKeypoints,
    decode_bevy_message,
    encode_status,
)
from surmap.simulation.camera_profile import load_camera_profile
from surmap.types import Vec3

PROFILE = (
    Path(__file__).parents[1]
    / "examples"
    / "bevy-sitl-poc"
    / "assets"
    / "cameras"
    / "elp-stereo-pinhole.camera.json"
)
GOLDENS = Path(__file__).parent / "fixtures" / "bevy_sim_wire"


def a_message(header: bytes, payload: bytes = b"") -> bytes:
    return struct.pack("<I", len(header)) + header + payload


def test_the_hello_golden_decodes_into_the_camera_profile_and_its_objects() -> None:
    # Given the hello the browser sends when a session opens
    message = (GOLDENS / "hello.bin").read_bytes()

    # When the bridge decodes it
    decoded = decode_bevy_message(message)

    # Then it carries exactly the profile file the renderer used, and the car
    assert isinstance(decoded, BevyHello)
    assert decoded.camera == load_camera_profile(PROFILE)
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


# ---- a fleet page: the scenario and each pair's drone -----------------------------------------

# The single-drone goldens, pinned: a fleet page's optional fields must leave them unchanged.
SINGLE_DRONE_GOLDENS = {
    "hello.bin": "508903f5be271a2d91f0da4cd5109481cef093f04f1657cef63c0170e86d7b20",
    "pair.bin": "e5b2acc4b5b910e77d3c590129922b3e5ce6aece2f069265d6ba1808b63aeb80",
}


def a_hello_naming(scenario: str) -> bytes:
    hello = (GOLDENS / "hello.bin").read_bytes()
    (length,) = struct.unpack_from("<I", hello, 0)
    header = json.loads(hello[4 : 4 + length])
    header["scenario"] = scenario
    return a_message(json.dumps(header, separators=(",", ":")).encode("utf-8"))


def test_the_drone_pair_golden_decodes_with_the_drone_that_rendered_it() -> None:
    # Given nest-sw-d1's 4x2 pair from a fleet page
    message = (GOLDENS / "pair-drone.bin").read_bytes()

    # When the bridge decodes it
    decoded = decode_bevy_message(message)

    # Then it is the golden frame, labelled with its drone
    assert isinstance(decoded, BevyPair)
    assert (decoded.drone_id, decoded.frame_id, decoded.left_data) == (
        "nest-sw-d1",
        7,
        bytes(range(8)),
    )


def test_a_pair_without_a_drone_id_belongs_to_no_drone() -> None:
    # Given the single-drone pair golden
    message = (GOLDENS / "pair.bin").read_bytes()

    # When the bridge decodes it
    decoded = decode_bevy_message(message)

    # Then it names no drone
    assert isinstance(decoded, BevyPair)
    assert decoded.drone_id is None


def test_a_fleet_page_s_hello_names_its_scenario() -> None:
    # Given the golden hello from a page running quake-fleet
    message = a_hello_naming("quake-fleet")

    # When the bridge decodes it
    decoded = decode_bevy_message(message)

    # Then it carries the scenario beside the camera profile
    assert isinstance(decoded, BevyHello)
    assert (decoded.scenario, decoded.camera) == ("quake-fleet", load_camera_profile(PROFILE))


def test_the_single_drone_goldens_stay_byte_identical() -> None:
    # Given the hello and pair goldens a page without a fleet sends
    names = sorted(SINGLE_DRONE_GOLDENS)

    # When their bytes are hashed
    digests = {name: hashlib.sha256((GOLDENS / name).read_bytes()).hexdigest() for name in names}

    # Then they are the bytes pinned before drones were named on the wire
    assert digests == SINGLE_DRONE_GOLDENS


def test_a_drone_s_status_names_it_and_why_its_pair_was_not_processed() -> None:
    # Given the status of a fifth drone's refused pair
    status = BridgeStatus(
        frames=0,
        posed=0,
        lost=False,
        keyframes=0,
        dropped=0,
        drone_id="nest-roof-d1",
        error="drone session limit (4) reached; nest-roof-d1 not processed",
    )

    # When the bridge encodes its reply
    text = encode_status(status)

    # Then the single-drone fields come first, then the drone and the reason
    assert text == (
        '{"type":"status","frames":0,"posed":0,"lost":false,"keyframes":0,"dropped":0,'
        '"drone_id":"nest-roof-d1",'
        '"error":"drone session limit (4) reached; nest-roof-d1 not processed"}'
    )


# ---- RTAB-Map's keypoints on the frame they were tracked in ----------------------------------


def test_a_status_carries_each_odometry_frame_s_keypoints_after_the_counts() -> None:
    # Given a reply whose pair brought frame 7's odometry with two tracked keypoints
    status = BridgeStatus(
        frames=8,
        posed=7,
        lost=False,
        keyframes=3,
        dropped=0,
        odometry=(FrameKeypoints(frame_id=7, keypoints=((1.5, 0.5, 2.25), (3.0, 1.0, 9.0))),),
    )

    # When the bridge encodes it
    text = encode_status(status)

    # Then the frame's id and its keypoints as [u, v, depth] follow the counts
    assert text == (
        '{"type":"status","frames":8,"posed":7,"lost":false,"keyframes":3,"dropped":0,'
        '"odometry":[{"frame_id":7,"keypoints":[[1.5,0.5,2.25],[3.0,1.0,9.0]]}]}'
    )


def test_a_status_without_odometry_keeps_the_counts_only_shape() -> None:
    # Given a reply whose pair brought no odometry yet
    status = BridgeStatus(frames=1, posed=0, lost=False, keyframes=0, dropped=0, odometry=())

    # When the bridge encodes it
    text = encode_status(status)

    # Then no odometry field appears
    assert "odometry" not in json.loads(text)
