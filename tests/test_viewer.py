"""Survey viewer: snapshot adapter, synced replay, and the ask hook."""

import json
import threading
import urllib.request
from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray
from PIL import Image

from surmap.demo.datasets import DATASETS, DatasetSpec, PreparedDataset
from surmap.detection.tracker import TrackedDetection
from surmap.geometry import to_camera_frame
from surmap.types import Pose, Vec3
from surmap.viewer.ask import answer_map_question
from surmap.viewer.euroc import EurocReplay
from surmap.viewer.model import (
    CameraModel,
    Observation,
    SemanticMapSnapshot,
    Track,
    empty_snapshot,
    hud_badges,
)
from surmap.viewer.poses import camera_pose
from surmap.viewer.preview import PreviewReplay
from surmap.viewer.project import detection_overlays, track_overlays
from surmap.viewer.server import make_viewer_server
from surmap.viewer.sitl import SitlReplay
from surmap.viewer.snapshot import read_snapshot
from surmap.viewer.timeline import placed_tracks

FIXTURE = Path(__file__).parent / "fixtures" / "semantic_map_snapshot.json"
CAMERA = CameraModel(fx=500.0, fy=500.0, cx=320.0, cy=180.0, width=640, height=360)

_IDENTITY_YAML = """
T_BS:
  data: [1, 0, 0, 0,
         0, 1, 0, 0,
         0, 0, 1, 0,
         0, 0, 0, 1]
resolution: [64, 48]
intrinsics: [40.0, 40.0, 32.0, 24.0]
"""
_CAM1_YAML = """
T_BS:
  data: [1, 0, 0, 0,
         0, 1, 0, 0.11,
         0, 0, 1, 0,
         0, 0, 0, 1]
resolution: [64, 48]
intrinsics: [40.0, 40.0, 32.0, 24.0]
"""


def test_the_fixture_is_a_v1_snapshot_with_separate_moving_tracks() -> None:
    # Given the copied semantic-map fixture (not imported from the unmerged writer)
    snapshot = read_snapshot(FIXTURE)

    # When the layers are read
    landmark_ids = [track.id for track in snapshot.landmarks]
    dynamic_ids = [track.id for track in snapshot.dynamic]

    # Then static and unknown tracks stay out of dynamic, and the car's mask is absent
    assert snapshot.origin is not None
    assert snapshot.origin.lat == 54.0
    assert landmark_ids == ["1", "2", "3"]
    assert dynamic_ids == ["4", "5"]
    assert {track.motion for track in snapshot.landmarks} == {"static", "unknown"}
    assert all(track.motion == "moving" for track in snapshot.dynamic)
    person = snapshot.landmarks[0]
    assert person.label == "person"
    assert person.mask_points is not None and len(person.mask_points) >= 3
    assert snapshot.dynamic[0].mask_points is None


def test_a_snapshot_with_the_wrong_schema_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "map.json"
    path.write_text(
        '{"schema": "other", "origin": null, "landmarks": [], "dynamic": []}\n', encoding="utf-8"
    )

    with pytest.raises(ValueError, match="schema"):
        read_snapshot(path)


def test_a_landmark_without_a_map_position_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "map.json"
    landmark = _entry("1", "landmarks", "static", "post")
    del landmark["xyz"]
    document = _door_document()
    document["landmarks"] = [landmark]
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="xyz"):
        read_snapshot(path)


def test_a_snapshot_with_no_origin_keeps_null_coordinates(tmp_path: Path) -> None:
    path = tmp_path / "map.json"
    landmark = _entry("1", "landmarks", "static", "post")
    landmark["lat"] = None
    landmark["lon"] = None
    landmark["alt"] = None
    landmark["anchor_t_ns"] = None
    landmark["offset_ns"] = None
    document = _door_document()
    document["origin"] = None
    document["landmarks"] = [landmark]
    path.write_text(json.dumps(document), encoding="utf-8")

    track = read_snapshot(path).landmarks[0]

    assert track.lat is None
    assert track.lon is None
    assert track.alt is None


def test_an_overlapping_clock_interpolates_a_moving_track() -> None:
    # Given a car that drives from x=0 at t=0 to x=10 at t=100, on that same clock
    snapshot = _car_snapshot(start=Vec3(0.0, 0.0, 0.0), end=Vec3(10.0, 0.0, 0.0), t0=0, t1=100)

    # When the replay is halfway
    placed = placed_tracks(snapshot, 50, replay_start=0, replay_end=100)

    # Then the car is visible halfway along its trail
    car = placed[0]
    assert car.visible
    assert car.xyz.x == pytest.approx(5.0)
    assert car.trail[-1].x == pytest.approx(5.0)


def test_a_track_is_hidden_before_its_first_observation() -> None:
    snapshot = _car_snapshot(start=Vec3(0.0, 0.0, 0.0), end=Vec3(1.0, 0.0, 0.0), t0=50, t1=100)

    placed = placed_tracks(snapshot, 10, replay_start=0, replay_end=100)

    assert placed[0].visible is False


def test_a_foreign_clock_scrubs_the_trail_by_replay_progress() -> None:
    # Given observations that do not overlap the replay timestamps
    snapshot = _car_snapshot(start=Vec3(0.0, 0.0, 0.0), end=Vec3(10.0, 0.0, 0.0), t0=0, t1=100)

    # When the replay finishes
    placed = placed_tracks(snapshot, 2_000, replay_start=1_000, replay_end=2_000)

    # Then progress, not the raw timestamp, selects the last observation
    assert placed[0].visible
    assert placed[0].xyz.x == pytest.approx(10.0)


def test_looking_north_puts_a_point_ahead_on_the_optical_axis() -> None:
    pose = camera_pose(Vec3(0.0, 0.0, 2.0), yaw_rad=0.0, pitch_down_rad=0.0)

    local = to_camera_frame(Vec3(0.0, 5.0, 2.0), pose)

    assert local.x == pytest.approx(0.0, abs=1e-6)
    assert local.y == pytest.approx(0.0, abs=1e-6)
    assert local.z == pytest.approx(5.0, abs=1e-6)


def test_a_person_ahead_of_the_camera_is_a_labelled_box_with_a_mask() -> None:
    # Given a level camera looking north at a standing person 8 m ahead
    pose = camera_pose(Vec3(0.0, 0.0, 1.0), yaw_rad=0.0, pitch_down_rad=0.0)
    person = _track(
        "1",
        "person",
        "static",
        "landmarks",
        Vec3(0.0, 8.0, 1.0),
        mask=(
            Vec3(-0.3, 8.0, 1.8),
            Vec3(0.3, 8.0, 1.8),
            Vec3(0.3, 8.0, 0.2),
            Vec3(-0.3, 8.0, 0.2),
        ),
    )
    placed = placed_tracks(
        SemanticMapSnapshot(None, (person,), ()),
        t_ns=0,
        replay_start=0,
        replay_end=0,
    )

    # When the track is projected
    overlays = track_overlays(pose, placed, CAMERA)

    # Then the box sits on the principal point and names the range
    assert len(overlays) == 1
    box = overlays[0]
    assert box.motion == "static"
    assert box.label == "PERSON 8.0 m"
    assert len(box.mask) >= 3
    assert (box.xyxy[0] + box.xyxy[2]) / 2 == pytest.approx(320.0, abs=5)
    assert box.xyxy[3] - box.xyxy[1] > 40


def test_a_landmark_behind_the_camera_is_not_drawn() -> None:
    pose = camera_pose(Vec3(0.0, 0.0, 1.0), yaw_rad=0.0, pitch_down_rad=0.0)
    person = _track("1", "person", "static", "landmarks", Vec3(0.0, -4.0, 1.0), mask=None)
    placed = placed_tracks(
        SemanticMapSnapshot(None, (person,), ()), t_ns=0, replay_start=0, replay_end=0
    )

    assert track_overlays(pose, placed, CAMERA) == ()


def test_a_tracked_detection_is_labelled_with_its_depth() -> None:
    # Given one point 4.2 m in front of the camera, inside the box
    detection = TrackedDetection("person", 0.91, (10.0, 20.0, 80.0, 140.0), 7, 1)
    camera = CameraModel(fx=100.0, fy=100.0, cx=40.0, cy=60.0, width=80, height=160)

    overlays = detection_overlays(
        Pose(Vec3(0.0, 0.0, 0.0)), (detection,), (Vec3(0.0, 0.0, 4.2),), camera
    )

    assert overlays[0].label == "PERSON 4.2 m"
    assert overlays[0].motion == "static"
    assert overlays[0].track_id == "det-7"


def test_a_weak_detection_is_marked_unknown() -> None:
    detection = TrackedDetection("bicycle", 0.4, (0.0, 0.0, 10.0, 10.0), 2, 1)
    camera = CameraModel(10.0, 10.0, 5.0, 5.0, 20, 20)

    overlays = detection_overlays(Pose(Vec3(0.0, 0.0, 0.0)), (detection,), (), camera)

    assert overlays[0].motion == "unknown"
    assert overlays[0].label == "BICYCLE"


def test_survey_badges_follow_pose_and_gps() -> None:
    assert hud_badges(mapping=True, landmark_count=4, gps_fix=True, pose_ok=True) == (
        "SURVEY",
        "MAPPING",
        "LANDMARKS 4",
        "GPS FIX",
    )
    assert hud_badges(mapping=False, landmark_count=0, gps_fix=False, pose_ok=True)[-1] == "POSE"
    assert (
        hud_badges(mapping=False, landmark_count=0, gps_fix=False, pose_ok=False)[-1] == "NO POSE"
    )


def test_euroc_ground_truth_places_the_drone_and_a_landmark(tmp_path: Path) -> None:
    # Given two EuRoC frames whose body pose is the recorded ground truth
    prepared = _euroc_root(tmp_path)
    snapshot = tmp_path / "map.json"
    snapshot.write_text(json.dumps(_ahead_snapshot()), encoding="utf-8")

    # When the replay is played without stereo
    ticks = list(EurocReplay(prepared, snapshot_path=snapshot, stereo=False, max_width=64).ticks())

    # Then the drone follows the file and the landmark ahead is labelled in metres
    assert ticks[0].drone == Vec3(0.0, 0.0, 0.0)
    assert ticks[1].drone == Vec3(2.0, 0.0, 1.0)
    assert ticks[1].height_m == pytest.approx(1.0)
    assert "POSE" in ticks[0].hud
    assert "GPS FIX" not in ticks[0].hud
    overlay = ticks[0].overlays[0]
    assert overlay.track_id == "1"
    assert "5.0 m" in overlay.label


def test_a_detector_box_is_drawn_on_the_euroc_frame(tmp_path: Path) -> None:
    class _Boxes:
        def detect_tracked(
            self, frame_id: int, rgb: NDArray[np.uint8]
        ) -> tuple[TrackedDetection, ...]:
            del rgb
            return (TrackedDetection("car", 0.8, (4.0, 4.0, 20.0, 20.0), 3, frame_id),)

    ticks = list(
        EurocReplay(_euroc_root(tmp_path), stereo=False, max_width=64, detections=_Boxes()).ticks()
    )

    assert any(
        overlay.track_id == "det-3" and overlay.label == "CAR" for overlay in ticks[0].overlays
    )


def test_sitl_gps_anchors_the_track_east_and_up(tmp_path: Path) -> None:
    # Given a two-frame capture whose second fix is east and higher
    capture = _sitl_capture(tmp_path)

    ticks = list(SitlReplay(capture).ticks())

    # Then the first fix is the origin and the second is east of it
    assert ticks[0].drone.x == pytest.approx(0.0, abs=1e-6)
    assert ticks[0].drone.z == pytest.approx(0.0, abs=1e-6)
    assert ticks[1].drone.x > 50.0
    assert ticks[1].height_m == pytest.approx(5.0)
    assert "GPS FIX" in ticks[1].hud


def test_ask_cites_matching_labels_and_their_mask_cloud() -> None:
    snapshot = read_snapshot(FIXTURE)

    # When the question names the car
    answer = answer_map_question("where is the car", snapshot)

    # Then that dynamic track is cited and a person question cites both people
    assert answer.landmark_ids == ("4",)
    assert answer.highlight_points == (snapshot.dynamic[0].xyz,)
    people = answer_map_question("person", snapshot)
    assert people.landmark_ids == ("1", "5")
    assert len(people.highlight_points) > 1


def test_the_live_flag_does_not_call_a_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SURMAP_LIVE_MAP_QA", "1")

    answer = answer_map_question("car", read_snapshot(FIXTURE))

    assert "SURMAP_LIVE_MAP_QA" in answer.answer
    assert "does not call a model" in answer.answer
    assert answer.landmark_ids == ("4",)


def test_preview_replay_moves_the_car_on_one_clock() -> None:
    ticks = list(PreviewReplay(frames=4).ticks())

    assert ticks[0].t_ns < ticks[-1].t_ns
    start = _placed(ticks[0], "4")
    end = _placed(ticks[-1], "4")
    assert start is not None and end is not None
    assert end.x > start.x
    assert ticks[0].jpeg
    assert "GPS FIX" in ticks[0].hud
    assert any(overlay.track_id == "1" for overlay in ticks[0].overlays)


def test_the_viewer_serves_one_clock_and_answers_ask(tmp_path: Path) -> None:
    # Given a short preview and a second snapshot that only contains a door
    door = tmp_path / "door.json"
    door.write_text(json.dumps(_door_document()), encoding="utf-8")
    server = make_viewer_server(
        lambda: PreviewReplay(frames=2), host="127.0.0.1", port=0, fps=200.0
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host = str(server.server_address[0])
    port = int(server.server_address[1])
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/", timeout=5) as response:
            page = response.read().decode()
        with urllib.request.urlopen(f"http://{host}:{port}/stream", timeout=15) as response:
            body = response.read().decode()
        payload = json.dumps({"question": "car"}).encode()
        request = urllib.request.Request(
            f"http://{host}:{port}/ask", data=payload, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            asked = json.loads(response.read())
        door_payload = json.dumps({"question": "door", "snapshot_path": str(door)}).encode()
        door_request = urllib.request.Request(
            f"http://{host}:{port}/ask",
            data=door_payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(door_request, timeout=5) as response:
            cited = json.loads(response.read())
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    # Then the page, the stream, and the hook share one replay
    assert "Ask the map" in page
    assert "MAP, CHASE VIEW" in page
    assert body.count("event: tick") == 2
    assert "event: session" in body
    assert asked["landmark_ids"] == ["4"]
    assert "highlight_points" in asked
    assert cited["landmark_ids"] == ["9"]
    assert cited["answer"]


def _placed(tick: object, track_id: str) -> Vec3 | None:
    from surmap.viewer.model import ViewerTick

    assert isinstance(tick, ViewerTick)
    for item in tick.placed:
        if item.track.id == track_id:
            return item.xyz
    return None


def _track(
    track_id: str,
    label: str,
    motion: str,
    layer: str,
    position: Vec3,
    mask: tuple[Vec3, ...] | None,
) -> Track:
    return Track(
        id=track_id,
        xyz=position,
        lat=54.0,
        lon=25.0,
        alt=120.0,
        label=label,
        description="",
        model_id="",
        motion=motion,
        t_ns=0,
        anchor_t_ns=0,
        offset_ns=0,
        observations=(Observation(0, position),),
        mask_points=mask,
        layer=layer,
    )


def _car_snapshot(*, start: Vec3, end: Vec3, t0: int, t1: int) -> SemanticMapSnapshot:
    car = Track(
        id="4",
        xyz=end,
        lat=54.0,
        lon=25.0,
        alt=120.0,
        label="car",
        description="car on the road",
        model_id="",
        motion="moving",
        t_ns=t1,
        anchor_t_ns=t0,
        offset_ns=t1 - t0,
        observations=(Observation(t0, start), Observation(t1, end)),
        mask_points=None,
        layer="dynamic",
    )
    return SemanticMapSnapshot(None, (), (car,))


def _door_document() -> dict[str, object]:
    return {
        "schema": "surmap.semantic_map_snapshot.v1",
        "origin": {"t_ns": 0, "lat": 54.0, "lon": 25.0, "alt": 100.0, "accuracy_m": 1.0},
        "landmarks": [_entry("9", "landmarks", "static", "door")],
        "dynamic": [],
    }


def _entry(track_id: str, layer: str, motion: str, label: str) -> dict[str, object]:
    del layer
    return {
        "id": track_id,
        "xyz": {"x": 0.0, "y": 0.0, "z": 0.0},
        "lat": 54.0,
        "lon": 25.0,
        "alt": 100.0,
        "label": label,
        "description": "",
        "model_id": "",
        "motion": motion,
        "t_ns": 0,
        "anchor_t_ns": 0,
        "offset_ns": 0,
        "observations": [{"t_ns": 0, "xyz": {"x": 0.0, "y": 0.0, "z": 0.0}}],
        "mask_points": None,
    }


def _ahead_snapshot() -> dict[str, object]:
    entry = _entry("1", "landmarks", "static", "person")
    entry["xyz"] = {"x": 0.0, "y": 0.0, "z": 5.0}
    entry["observations"] = [
        {"t_ns": 100, "xyz": {"x": 0.0, "y": 0.0, "z": 5.0}},
        {"t_ns": 200, "xyz": {"x": 0.0, "y": 0.0, "z": 5.0}},
    ]
    entry["t_ns"] = 200
    return {
        "schema": "surmap.semantic_map_snapshot.v1",
        "origin": None,
        "landmarks": [entry],
        "dynamic": [],
    }


def _euroc_root(tmp_path: Path) -> PreparedDataset:
    root = tmp_path / "euroc"
    for channel in (0, 1):
        folder = root / "mav0" / f"cam{channel}" / "data"
        folder.mkdir(parents=True)
        for stamp in (100, 200):
            Image.new("RGB", (64, 48), (70, 80, 90)).save(folder / f"{stamp}.png")
        yaml = _IDENTITY_YAML if channel == 0 else _CAM1_YAML
        (root / "mav0" / f"cam{channel}" / "sensor.yaml").write_text(yaml, encoding="utf-8")
    gt = root / "mav0" / "state_groundtruth_estimate0" / "data.csv"
    gt.parent.mkdir(parents=True)
    gt.write_text(
        "#timestamp, p_x, p_y, p_z, q_w, q_x, q_y, q_z\n100,0,0,0,1,0,0,0\n200,2,0,1,1,0,0,0\n",
        encoding="utf-8",
    )
    spec = DatasetSpec(
        dataset_id="tiny-euroc",
        title="Tiny EuRoC",
        description="two pairs",
        zip_url="https://example.invalid/tiny.zip",
        zip_size_bytes=1,
        zip_sha256="0" * 64,
        official_url="https://example.invalid/",
    )
    return PreparedDataset(spec, root, (100, 200))


def _sitl_capture(tmp_path: Path) -> Path:
    capture = tmp_path / "hover"
    images = capture / "images"
    images.mkdir(parents=True)
    for name in ("left_000.png", "left_001.png", "right_000.png", "right_001.png"):
        Image.new("RGB", (32, 24), (40, 50, 60)).save(images / name)
    (capture / "calibration.json").write_text(
        json.dumps(
            {
                "calibration_id": "gazebo-stereo-v1",
                "width": 32,
                "height": 24,
                "fx": 20.0,
                "fy": 20.0,
                "cx": 16.0,
                "cy": 12.0,
                "baseline_m": 0.07,
            }
        ),
        encoding="utf-8",
    )
    (capture / "frames.jsonl").write_text(
        '{"frame_id": 0, "t_ns": 1000000000, "left": "images/left_000.png", '
        '"right": "images/right_000.png"}\n'
        '{"frame_id": 1, "t_ns": 2000000000, "left": "images/left_001.png", '
        '"right": "images/right_001.png"}\n',
        encoding="utf-8",
    )
    (capture / "gps.csv").write_text(
        "t_ns,lat,lon,alt,accuracy_m\n"
        "1000000000,47.0,8.0,400.0,1.5\n"
        "2000000000,47.0,8.001,405.0,1.5\n",
        encoding="utf-8",
    )
    return capture


def test_dataset_registry_remains_the_euroc_default() -> None:
    # The viewer reuses the demo registry rather than a second download path.
    assert "euroc-v1-01-easy" in DATASETS
    assert empty_snapshot().tracks() == ()
