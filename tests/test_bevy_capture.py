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
