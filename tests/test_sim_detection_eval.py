"""Scoring on-board detections against a simulation capture's ground truth."""

import json
import math
from pathlib import Path
from typing import NamedTuple

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from surmap.simulation.bevy_capture import BevyCapture, CapturedFrame
from surmap.simulation.bevy_wire import GroundTruthBox
from surmap.simulation.calibration import StereoCalibrationSpec
from surmap.simulation.detection_eval import (
    COCO_LABELS,
    VEHICLE_FOOTPRINT_M,
    ExpectedObject,
    detect_capture,
    score_capture,
    score_frame,
    visible_objects,
)
from surmap.types import Detection, Pose, StereoFramePair, Vec3
from tests.sim_fakes import POC_ASSETS

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


class Drive(NamedTuple):
    """One track-only vehicle (it has no ground-truth box): where, what and which way."""

    tracks: dict[str, Vec3]
    kinds: dict[str, str]
    yaw_deg: dict[str, float]


def a_drive(kind: str, east: float, north: float, heading_deg: float) -> Drive:
    return Drive(
        {f"{kind}-1": Vec3(east, north, 0.0)}, {f"{kind}-1": kind}, {f"{kind}-1": heading_deg}
    )


def a_detection(label: str, box: tuple[float, float, float, float], frame_id: int = 1) -> Detection:
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


def test_finding_a_person_too_small_to_be_expected_is_not_a_false_positive() -> None:
    # Given a person 60 m ahead: present in the image, but under the size an object must have
    # to be expected
    far = a_person_ahead(metres=60.0)
    rig = a_north_facing_rig()
    assert visible_objects((far,), rig, a_calibration()) == ()
    (present,) = visible_objects((far,), rig, a_calibration(), min_side_px=0.0)

    # When a detector finds them anyway
    score = score_frame((), (a_detection("person", present.box_xyxy),), unresolved=(present,))

    # Then that is neither a hit nor a false positive
    assert (score.hit_ids, score.false_positives) == (frozenset(), ())


def expected_vehicle(kind: str, heading_deg: float, metres: float = 15.0) -> ExpectedObject:
    drive = a_drive(kind, 0.0, metres, heading_deg)
    (found,) = visible_objects(
        (),
        a_north_facing_rig(),
        a_calibration(),
        tracks=drive.tracks,
        kinds=drive.kinds,
        yaw_deg=drive.yaw_deg,
    )
    return found


def test_a_bus_that_only_has_a_track_is_expected_where_the_track_puts_it() -> None:
    bus = expected_vehicle("bus", heading_deg=90.0)

    x0, _, x1, _ = bus.box_xyxy
    assert (bus.id, bus.kind) == ("bus-1", "bus")
    assert x0 < 320.0 < x1


def test_a_vehicle_driving_across_the_view_shows_its_side_wider_than_driving_away() -> None:
    away = expected_vehicle("bus", heading_deg=90.0)
    across = expected_vehicle("bus", heading_deg=0.0)

    def width(obj: ExpectedObject) -> float:
        return obj.box_xyxy[2] - obj.box_xyxy[0]

    assert width(across) > 2.0 * width(away)


def test_a_track_of_a_kind_with_no_footprint_is_not_expected() -> None:
    assert (
        visible_objects(
            (),
            a_north_facing_rig(),
            a_calibration(),
            tracks={"x": Vec3(0.0, 12.0, 0.0)},
            kinds={"x": "balloon"},
            yaw_deg={"x": 0.0},
        )
        == ()
    )


def test_a_bus_is_found_only_by_a_bus_label_but_a_car_by_any_vehicle_label() -> None:
    bus, car = expected_vehicle("bus", 90.0), expected(a_car_ahead())

    as_truck = score_frame((bus,), (a_detection("truck", bus.box_xyxy),))
    as_bus = score_frame((bus,), (a_detection("bus", bus.box_xyxy),))
    car_as_bus = score_frame((car,), (a_detection("bus", car.box_xyxy),))

    assert (as_truck.hit_ids, as_bus.hit_ids, car_as_bus.hit_ids) == (
        frozenset(),
        frozenset({"bus-1"}),
        frozenset({"car-1"}),
    )


def test_a_train_is_found_only_by_a_train_label() -> None:
    train = expected_vehicle("train", 90.0, metres=30.0)

    as_truck = score_frame((train,), (a_detection("truck", train.box_xyxy),))
    as_train = score_frame((train,), (a_detection("train", train.box_xyxy),))

    assert (as_truck.hit_ids, as_train.hit_ids) == (frozenset(), frozenset({"train-1"}))


def test_a_vehicle_called_another_vehicle_is_a_confusion_not_a_false_positive() -> None:
    bus = expected_vehicle("bus", 90.0)

    score = score_frame((bus,), (a_detection("truck", bus.box_xyxy),))

    assert (score.hit_ids, score.false_positives, score.as_another_vehicle) == (
        frozenset(),
        (),
        frozenset({"bus-1"}),
    )


def test_a_person_label_on_a_bus_is_a_false_positive_not_a_confusion() -> None:
    bus = expected_vehicle("bus", 90.0)

    score = score_frame((bus,), (a_detection("person", bus.box_xyxy),))

    assert (score.as_another_vehicle, len(score.false_positives)) == (frozenset(), 1)


def test_a_capture_scores_track_only_vehicles_per_kind_with_their_confusions() -> None:
    # Given a bus and a train that only the tracks place, in two frames
    drive_bus, drive_train = a_drive("bus", 0.0, 15.0, 90.0), a_drive("train", 6.0, 40.0, 90.0)
    tracks = {**drive_bus.tracks, **drive_train.tracks}
    kinds = {**drive_bus.kinds, **drive_train.kinds}
    yaw = {**drive_bus.yaw_deg, **drive_train.yaw_deg}
    frames = (a_frame(1, a_north_facing_rig()), a_frame(2, a_north_facing_rig()))
    capture = BevyCapture(
        calibration=a_calibration(),
        objects=(),
        frames=frames,
        object_tracks={f.pair.t_ns: tracks for f in frames},
        object_kinds=kinds,
        object_yaw_deg={f.pair.t_ns: yaw for f in frames},
    )
    bus = expected_vehicle("bus", 90.0)
    detections = {
        1: (a_detection("bus", bus.box_xyxy, frame_id=1),),
        2: (a_detection("truck", bus.box_xyxy, frame_id=2),),
    }

    report = score_capture(capture, detections)

    assert (report.kinds["bus"].visible, report.kinds["bus"].found) == (2, 1)
    assert report.kinds["bus"].as_another_vehicle == 1
    assert report.kinds["train"].visible == 2
    assert report.kinds["car"].as_another_vehicle == 0


def test_a_capture_report_counts_each_persons_object_frames_by_the_pose_they_hold() -> None:
    # Given a standing and a sitting person side by side, over two frames
    standing = a_box("person", -1.5, 8.0, (0.6, 0.4, 1.8), "standing-1")
    sitting = a_box("person", 1.5, 8.0, (0.6, 0.4, 1.0), "sitting-1")
    frames = (a_frame(1, a_north_facing_rig()), a_frame(2, a_north_facing_rig()))
    poses = {"standing-1": "standing", "sitting-1": "sitting"}
    capture = BevyCapture(
        calibration=a_calibration(),
        objects=(standing, sitting),
        frames=frames,
        object_poses={frame.pair.t_ns: poses for frame in frames},
    )
    # and only the sitting person found, in the first frame
    detections = {1: (a_detection("person", expected(sitting).box_xyxy, frame_id=1),)}

    # When the capture is scored
    report = score_capture(capture, detections)

    # Then each pose's object-frames seen and found are counted
    assert {pose: (s.visible, s.found) for pose, s in report.poses.items()} == {
        "standing": (2, 0),
        "sitting": (2, 1),
    }


def test_a_boat_and_a_ship_are_both_kinds_a_boat_label_names() -> None:
    assert COCO_LABELS["boat"] == frozenset({"boat"})
    assert COCO_LABELS["ship"] == frozenset({"boat"})


def test_the_vessel_footprints_are_the_sizes_their_class_files_declare() -> None:
    for kind in ("boat", "ship"):
        text = (POC_ASSETS / "vehicle" / f"{kind}.vehicle.json").read_text(encoding="utf-8")
        declared = json.loads(text)

        assert VEHICLE_FOOTPRINT_M[kind] == (
            declared["length_m"],
            declared["width_m"],
            declared["height_m"],
        )


def test_a_boat_that_only_has_a_track_is_expected_where_the_track_puts_it() -> None:
    boat = expected_vehicle("boat", heading_deg=90.0)

    assert (boat.id, boat.kind) == ("boat-1", "boat")


def test_a_boat_is_found_by_a_boat_label_but_not_by_a_truck_label() -> None:
    boat = expected_vehicle("boat", heading_deg=90.0)

    as_truck = score_frame((boat,), (a_detection("truck", boat.box_xyxy),))
    as_boat = score_frame((boat,), (a_detection("boat", boat.box_xyxy),))

    assert (as_truck.hit_ids, as_boat.hit_ids) == (frozenset(), frozenset({"boat-1"}))


def test_a_ship_is_found_by_a_boat_label() -> None:
    ship = expected_vehicle("ship", heading_deg=90.0, metres=80.0)

    as_boat = score_frame((ship,), (a_detection("boat", ship.box_xyxy),))

    assert as_boat.hit_ids == frozenset({"ship-1"})
