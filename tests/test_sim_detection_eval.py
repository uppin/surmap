"""Scoring on-board detections against a simulation capture's ground truth."""

import math
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from surmap.simulation.bevy_capture import BevyCapture, CapturedFrame
from surmap.simulation.bevy_wire import GroundTruthBox
from surmap.simulation.calibration import StereoCalibrationSpec
from surmap.simulation.detection_eval import (
    ExpectedObject,
    detect_capture,
    score_capture,
    score_frame,
    visible_objects,
)
from surmap.types import Detection, Pose, StereoFramePair, Vec3

HALF_SQRT2 = math.sqrt(2.0) / 2.0


def a_calibration() -> StereoCalibrationSpec:
    return StereoCalibrationSpec(
        calibration_id="elp-stereo-pinhole-v1",
        width=640,
        height=480,
        fx=381.36,
        fy=381.36,
        cx=320.0,
        cy=240.0,
        baseline_m=0.07,
        rate_hz=10.0,
    )


def a_north_facing_rig(east: float = 0.0, north: float = 0.0) -> Pose:
    # Forward-left-up to ENU for a north-facing rig is a +90 degree turn about up.
    return Pose(Vec3(east, north, 1.0), (0.0, 0.0, HALF_SQRT2, HALF_SQRT2))


def a_box(
    kind: str, east: float, north: float, size: tuple[float, float, float], obj_id: str = ""
) -> GroundTruthBox:
    width, depth, height = size
    return GroundTruthBox(
        id=obj_id or f"{kind}-1",
        kind=kind,
        min_enu=Vec3(east - width / 2, north - depth / 2, 0.0),
        max_enu=Vec3(east + width / 2, north + depth / 2, height),
    )


def a_car_ahead(metres: float = 10.0, obj_id: str = "car-1") -> GroundTruthBox:
    return a_box("car", 0.0, metres, (1.8, 4.3, 1.4), obj_id)


def a_person_ahead(metres: float = 8.0, east: float = 0.0) -> GroundTruthBox:
    return a_box("person", east, metres, (0.6, 0.4, 1.8), "survivor-1")


def a_detection(
    label: str, box: tuple[float, float, float, float], frame_id: int = 1
) -> Detection:
    return Detection(frame_id, box, label, 0.8, "efficientdet-lite0")


def expected(obj: GroundTruthBox, rig: Pose | None = None) -> ExpectedObject:
    (found,) = visible_objects((obj,), rig or a_north_facing_rig(), a_calibration())
    return found


def a_frame(
    frame_id: int, rig: Pose, left_ref: str = "l.png", left_rgb_ref: str | None = None
) -> CapturedFrame:
    t_ns = frame_id * 100_000_000
    pair = StereoFramePair(frame_id, t_ns, left_ref, "r.png", "elp-stereo-pinhole-v1")
    return CapturedFrame(pair=pair, pose_enu=rig, left_rgb_ref=left_rgb_ref)


class PixelReadingDetector:
    """A detector fake that reports the colour of the frame's first pixel as its label."""

    def detect(self, rgb: NDArray[np.uint8], frame_id: int) -> tuple[Detection, ...]:
        r, g, b = (int(v) for v in rgb[0, 0])
        return (Detection(frame_id, (0.0, 0.0, 1.0, 1.0), f"{r},{g},{b}", 0.9, "fake"),)


def an_image(path: Path, mode: str, colour: int | tuple[int, int, int]) -> str:
    Image.new(mode, (4, 2), colour).save(path)
    return str(path)


def test_a_car_ahead_of_the_rig_is_expected_around_the_image_centre() -> None:
    # Given a car ten metres ahead of a north-facing rig
    car = a_car_ahead()

    # When the objects the frame should show are listed
    (found,) = visible_objects((car,), a_north_facing_rig(), a_calibration())

    # Then the car is expected, its box straddling the image centre column
    x0, _, x1, _ = found.box_xyxy
    assert (found.id, found.kind) == ("car-1", "car")
    assert x0 < 320.0 < x1


def test_a_car_behind_the_rig_is_not_expected() -> None:
    car = a_box("car", 0.0, -10.0, (1.8, 4.3, 1.4))

    assert visible_objects((car,), a_north_facing_rig(), a_calibration()) == ()


def test_a_person_too_far_away_to_resolve_is_not_expected() -> None:
    # Given a person 200 m ahead: under ten pixels tall at fx 381
    person = a_person_ahead(metres=200.0)

    assert visible_objects((person,), a_north_facing_rig(), a_calibration()) == ()


def test_a_person_mostly_outside_the_image_is_not_expected() -> None:
    # Given a person whose box lies beyond the left image edge but for a sliver
    person = a_person_ahead(metres=8.0, east=-6.95)

    assert visible_objects((person,), a_north_facing_rig(), a_calibration()) == ()


def test_kinds_no_coco_detector_can_name_are_never_expected() -> None:
    rubble = a_box("collapsed_building", 0.0, 15.0, (10.0, 10.0, 3.0))

    assert visible_objects((rubble,), a_north_facing_rig(), a_calibration()) == ()


def test_a_moving_persons_box_follows_its_recorded_track() -> None:
    # Given a person recorded standing 8 m ahead who has since walked 2 m east
    person = a_person_ahead(metres=8.0)
    standing = expected(person)

    # When the frame's track places them
    (walked,) = visible_objects(
        (person,),
        a_north_facing_rig(),
        a_calibration(),
        tracks={"survivor-1": Vec3(2.0, 8.0, 0.0)},
    )

    # Then the expected box has moved right in the image
    assert walked.box_xyxy[0] > standing.box_xyxy[2]


def test_a_car_detection_on_a_visible_car_is_a_hit() -> None:
    car = expected(a_car_ahead())

    score = score_frame((car,), (a_detection("car", car.box_xyxy),))

    assert (score.hit_ids, score.false_positives) == (frozenset({"car-1"}), ())


def test_a_truck_detection_on_a_car_counts_as_finding_it() -> None:
    car = expected(a_car_ahead())

    score = score_frame((car,), (a_detection("truck", car.box_xyxy),))

    assert score.hit_ids == frozenset({"car-1"})


def test_a_person_detection_with_nobody_in_view_is_a_false_positive() -> None:
    ghost = a_detection("person", (100.0, 100.0, 120.0, 160.0))

    score = score_frame((), (ghost,))

    assert (score.hit_ids, score.false_positives) == (frozenset(), (ghost,))


def test_a_car_label_on_a_person_misses_the_person_and_is_a_false_positive() -> None:
    person = expected(a_person_ahead())
    wrong = a_detection("car", person.box_xyxy)

    score = score_frame((person,), (wrong,))

    assert (score.hit_ids, score.false_positives) == (frozenset(), (wrong,))


def test_a_detection_far_from_the_expected_box_does_not_find_it() -> None:
    car = expected(a_car_ahead())
    elsewhere = a_detection("car", (0.0, 0.0, 30.0, 30.0))

    score = score_frame((car,), (elsewhere,))

    assert (score.hit_ids, score.false_positives) == (frozenset(), (elsewhere,))


def test_a_capture_report_counts_frames_seen_and_found_per_kind_and_false_positives() -> None:
    # Given two frames with a car ahead and a person beside it, the car found in one frame
    car, person = a_car_ahead(metres=12.0), a_person_ahead(metres=8.0, east=2.5)
    capture = BevyCapture(
        calibration=a_calibration(),
        objects=(car, person),
        frames=(a_frame(1, a_north_facing_rig()), a_frame(2, a_north_facing_rig())),
    )
    car_box = expected(car).box_xyxy
    detections = {
        1: (a_detection("car", car_box, frame_id=1),),
        2: (a_detection("airplane", (0.0, 0.0, 40.0, 40.0), frame_id=2),),
    }

    # When the capture is scored
    report = score_capture(capture, detections)

    # Then each kind's object-frames seen and found, and every false positive by label, are counted
    assert (report.kinds["car"].visible, report.kinds["car"].found) == (2, 1)
    assert (report.kinds["person"].visible, report.kinds["person"].found) == (2, 0)
    assert report.false_positives == {"airplane": 1}


def test_a_capture_is_detected_on_its_colour_left_images_when_it_has_them(
    tmp_path: Path,
) -> None:
    # Given a frame with a grey left eye and a colour left image, both on disk
    grey = an_image(tmp_path / "l.png", "L", 128)
    colour = an_image(tmp_path / "l_rgb.png", "RGB", (200, 40, 10))
    capture = BevyCapture(
        calibration=a_calibration(),
        objects=(),
        frames=(a_frame(1, a_north_facing_rig(), left_ref=grey, left_rgb_ref=colour),),
    )

    # When the capture is run through a detector
    detections = detect_capture(capture, PixelReadingDetector())

    # Then the detector saw the colour image
    assert [d.label for d in detections[1]] == ["200,40,10"]


def test_a_grey_only_capture_is_detected_on_its_grey_left_eye(tmp_path: Path) -> None:
    grey = an_image(tmp_path / "l.png", "L", 128)
    capture = BevyCapture(
        calibration=a_calibration(),
        objects=(),
        frames=(a_frame(1, a_north_facing_rig(), left_ref=grey),),
    )

    detections = detect_capture(capture, PixelReadingDetector())

    assert [d.label for d in detections[1]] == ["128,128,128"]
