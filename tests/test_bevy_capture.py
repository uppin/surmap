"""A recorded Bevy session round-trips through the capture directory."""

import json
from pathlib import Path

from PIL import Image

from surmap.simulation.bevy_capture import CaptureRecorder, load_bevy_capture
from surmap.simulation.bevy_wire import BevyPair, GroundTruthBox
from surmap.simulation.calibration import StereoCalibrationSpec
from surmap.simulation.camera_profile import load_camera_profile
from surmap.types import Pose, Vec3


def a_calibration() -> StereoCalibrationSpec:
    return StereoCalibrationSpec(
        calibration_id="bevy-test-v1",
        width=4,
        height=2,
        fx=100.0,
        fy=100.0,
        cx=2.0,
        cy=1.0,
        baseline_m=0.07,
        rate_hz=10.0,
    )


def a_car() -> GroundTruthBox:
    return GroundTruthBox(
        id="car-1", kind="car", min_enu=Vec3(1.0, 2.0, 0.0), max_enu=Vec3(3.0, 6.5, 1.5)
    )


def a_pair(frame_id: int, t_ns: int, east: float) -> BevyPair:
    return BevyPair(
        frame_id=frame_id,
        t_ns=t_ns,
        width=4,
        height=2,
        encoding="gray8",
        pose_enu=Pose(Vec3(east, 3.0, 2.0), (0.0, 0.0, 0.0, 1.0)),
        left_data=bytes(range(8)),
        right_data=bytes(range(8, 16)),
    )


def test_a_recorded_session_loads_back_with_its_poses_and_ground_truth(tmp_path: Path) -> None:
    # Given a recorder that saw two pairs of the tiny rig
    root = tmp_path / "capture"
    recorder = CaptureRecorder(root, a_calibration(), objects=(a_car(),))
    recorder.record_pair(a_pair(1, 1_000_000, 1.0))
    recorder.record_pair(a_pair(2, 1_100_000, 1.5))
    recorder.finish()

    # When the capture is loaded back
    capture = load_bevy_capture(root)

    # Then calibration, poses, ground truth, PNG frames and the EuRoC export all survived
    assert capture.calibration == a_calibration()
    assert capture.objects == (a_car(),)
    assert len(capture.frames) == 2
    assert capture.frames[0].pair.frame_id == 1
    assert capture.frames[0].pose_enu == Pose(Vec3(1.0, 3.0, 2.0), (0.0, 0.0, 0.0, 1.0))
    assert capture.frames[1].pose_enu.position == Vec3(1.5, 3.0, 2.0)
    with Image.open(capture.frames[0].pair.left_ref) as left_image:
        assert left_image.size == (4, 2)
    assert (root / "calibration.json").is_file()
    ground_truth = json.loads((root / "ground_truth.json").read_text(encoding="utf-8"))
    assert ground_truth == [
        {"id": "car-1", "kind": "car", "min_enu": [1.0, 2.0, 0.0], "max_enu": [3.0, 6.5, 1.5]}
    ]
    assert (root / "euroc" / "mav0" / "cam0" / "sensor.yaml").is_file()
    assert (root / "euroc" / "mav0" / "cam1" / "sensor.yaml").is_file()
    assert (root / "euroc" / "mav0" / "cam0" / "data" / "1000000.png").is_file()
    assert (root / "euroc" / "mav0" / "cam1" / "data" / "1100000.png").is_file()


def test_a_capture_carries_the_camera_profile_it_was_rendered_with(tmp_path: Path) -> None:
    # Given a recorded session whose recorder left the renderer's camera profile beside it
    shipped = (
        Path(__file__).parents[1]
        / "examples"
        / "bevy-sitl-poc"
        / "assets"
        / "cameras"
        / "elp-stereo-pinhole.camera.json"
    )
    recorder = CaptureRecorder(tmp_path, a_calibration(), objects=(a_car(),))
    recorder.record_pair(a_pair(1, 1_000_000_000, 0.0))
    recorder.finish()
    (tmp_path / "camera.json").write_text(shipped.read_text(encoding="utf-8"), encoding="utf-8")

    # When it is loaded
    capture = load_bevy_capture(tmp_path)

    # Then the profile comes with it, so RTAB-Map's calibration is derived from the same file
    assert capture.camera == load_camera_profile(shipped)


def test_a_capture_without_a_camera_profile_has_none(tmp_path: Path) -> None:
    # Given a recorded session from before camera profiles existed
    recorder = CaptureRecorder(tmp_path, a_calibration(), objects=(a_car(),))
    recorder.record_pair(a_pair(1, 1_000_000_000, 0.0))
    recorder.finish()

    # When it is loaded
    capture = load_bevy_capture(tmp_path)

    # Then it says so rather than inventing one
    assert capture.camera is None


def test_a_capture_carries_the_fire_perimeter_per_frame(tmp_path: Path) -> None:
    # Given a recorded session whose recorder wrote the fire front beside its frames
    recorder = CaptureRecorder(tmp_path, a_calibration(), objects=(a_car(),))
    recorder.record_pair(a_pair(1, 1_000_000_000, 0.0))
    recorder.finish()
    front = [[-19.0, 60.0], [-20.0, 61.0], [-21.0, 60.0], [-20.0, 59.0]]
    (tmp_path / "fire_perimeter.jsonl").write_text(
        json.dumps({"t_ns": 1_000_000_000, "fires": [{"id": "front-1", "polygon_enu": front}]})
        + "\n",
        encoding="utf-8",
    )

    # When it is loaded
    capture = load_bevy_capture(tmp_path)

    # Then each frame's fire fronts are there by id
    assert capture.fire_perimeters[1_000_000_000]["front-1"] == tuple(tuple(p) for p in front)


def test_a_capture_without_fire_has_no_perimeters(tmp_path: Path) -> None:
    recorder = CaptureRecorder(tmp_path, a_calibration(), objects=(a_car(),))
    recorder.record_pair(a_pair(1, 1_000_000_000, 0.0))
    recorder.finish()

    assert load_bevy_capture(tmp_path).fire_perimeters == {}


def test_a_capture_carries_each_persons_track_and_the_wind_per_frame(tmp_path: Path) -> None:
    # Given a recorded session whose recorder wrote the moving bodies and the wind
    recorder = CaptureRecorder(tmp_path, a_calibration(), objects=(a_car(),))
    recorder.record_pair(a_pair(1, 1_000_000_000, 0.0))
    recorder.finish()
    line = {
        "t_ns": 1_000_000_000,
        "wind_enu": [6.0, 0.5],
        "objects": [{"id": "evacuee-1", "enu": [12.0, 61.0, 0.0], "action": "flee_from_fire"}],
    }
    (tmp_path / "object_tracks.jsonl").write_text(json.dumps(line) + "\n", encoding="utf-8")

    # When it is loaded
    capture = load_bevy_capture(tmp_path)

    # Then each frame has every person's position and the wind
    assert capture.object_tracks[1_000_000_000]["evacuee-1"] == Vec3(12.0, 61.0, 0.0)
    assert capture.wind[1_000_000_000] == (6.0, 0.5)


def test_a_capture_without_moving_bodies_has_no_tracks(tmp_path: Path) -> None:
    recorder = CaptureRecorder(tmp_path, a_calibration(), objects=(a_car(),))
    recorder.record_pair(a_pair(1, 1_000_000_000, 0.0))
    recorder.finish()

    capture = load_bevy_capture(tmp_path)

    assert (capture.object_tracks, capture.wind) == ({}, {})


def test_a_capture_carries_each_buildings_burning_and_burnt_floors_per_frame(
    tmp_path: Path,
) -> None:
    # Given a recorded session whose recorder wrote the building fires beside its frames
    recorder = CaptureRecorder(tmp_path, a_calibration(), objects=(a_car(),))
    recorder.record_pair(a_pair(1, 1_000_000_000, 0.0))
    recorder.finish()
    line = {
        "t_ns": 1_000_000_000,
        "buildings": [{"id": "tower-2", "burning": [3, 4], "burnt": [2]}],
    }
    (tmp_path / "building_fires.jsonl").write_text(json.dumps(line) + "\n", encoding="utf-8")

    # When it is loaded
    capture = load_bevy_capture(tmp_path)

    # Then each frame has every burning building's floors
    assert capture.building_fires[1_000_000_000]["tower-2"] == ((3, 4), (2,))


def test_a_capture_without_building_fires_has_none(tmp_path: Path) -> None:
    recorder = CaptureRecorder(tmp_path, a_calibration(), objects=(a_car(),))
    recorder.record_pair(a_pair(1, 1_000_000_000, 0.0))
    recorder.finish()

    assert load_bevy_capture(tmp_path).building_fires == {}


def test_a_capture_recorded_in_colour_names_each_frames_colour_left_image(
    tmp_path: Path,
) -> None:
    # Given a recorded session whose recorder also wrote a colour left image per frame
    recorder = CaptureRecorder(tmp_path, a_calibration(), objects=(a_car(),))
    recorder.record_pair(a_pair(1, 1_000_000_000, 0.0))
    recorder.finish()
    frames = tmp_path / "frames.jsonl"
    line = json.loads(frames.read_text(encoding="utf-8"))
    line["left_rgb_ref"] = "frames/left_rgb/1000000000.jpg"
    frames.write_text(json.dumps(line) + "\n", encoding="utf-8")

    # When it is loaded
    capture = load_bevy_capture(tmp_path)

    # Then the frame names its colour image beside the grey eyes
    assert capture.frames[0].left_rgb_ref == str(tmp_path / "frames/left_rgb/1000000000.jpg")


def test_a_grey_only_capture_has_no_colour_images(tmp_path: Path) -> None:
    recorder = CaptureRecorder(tmp_path, a_calibration(), objects=(a_car(),))
    recorder.record_pair(a_pair(1, 1_000_000_000, 0.0))
    recorder.finish()

    capture = load_bevy_capture(tmp_path)

    assert capture.frames[0].left_rgb_ref is None


def test_a_capture_carries_what_each_tracked_body_is_and_its_heading_per_frame(
    tmp_path: Path,
) -> None:
    # Given a capture whose tracks hold a person and a bus
    recorder = CaptureRecorder(tmp_path, a_calibration(), objects=(a_car(),))
    recorder.record_pair(a_pair(1, 1_000_000_000, 0.0))
    recorder.finish()
    line = {
        "t_ns": 1_000_000_000,
        "wind_enu": [0.0, 0.0],
        "objects": [
            {
                "id": "bus-1",
                "enu": [-2.5, 10.0, 0.0],
                "action": "follow_path",
                "kind": "bus",
                "yaw_deg": 90.0,
            },
            {
                "id": "evacuee-1",
                "enu": [1.0, 2.0, 0.0],
                "action": None,
                "kind": "person",
                "yaw_deg": -30.0,
            },
        ],
    }
    (tmp_path / "object_tracks.jsonl").write_text(json.dumps(line) + "\n", encoding="utf-8")

    # When it is loaded
    capture = load_bevy_capture(tmp_path)

    # Then each body's kind and each frame's headings come back by id
    assert capture.object_kinds == {"bus-1": "bus", "evacuee-1": "person"}
    assert capture.object_yaw_deg[1_000_000_000] == {"bus-1": 90.0, "evacuee-1": -30.0}
