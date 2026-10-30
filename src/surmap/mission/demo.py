"""Chain a disaster survey from a session export to a scored snapshot.

Offline is the default. It exports the recorded SITL fixture to EuRoC
and projects a second recorded fixture onto the ground-truth people.
Live calls are built only when the matching ``SURMAP_LIVE_*`` flag is
set. API keys are read by the clients and are not written into the report.
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from PIL import Image

from surmap.geometry import centroid, to_camera_frame
from surmap.labelling.baseten_muse import BasetenMuseLabelClient, ObjectLabel
from surmap.labelling.meta_muse import MetaMuseSceneClient
from surmap.map.snapshot import build_snapshot, write_snapshot
from surmap.mission.metrics import (
    ImpactMetrics,
    OfflinePerception,
    SurvivorDetection,
    load_offline_perception,
    score_survivors,
)
from surmap.simulation.calibration import StereoCalibrationSpec, render_cam_sensor_yaml
from surmap.simulation.disaster_world import DisasterGroundTruth, load_disaster_ground_truth
from surmap.simulation.euroc_export import export_euroc_session
from surmap.simulation.sitl_capture import load_sitl_capture
from surmap.slam.base import FrameResult
from surmap.survey.mask_cloud import points_in_mask
from surmap.survey.meta_sam import MetaSamDetector
from surmap.survey.modal_sam import ModalSamDetector
from surmap.survey.sam import RawFrame, SamDetection
from surmap.survey.stereo import StereoRig
from surmap.types import (
    GpsCheckpoint,
    Motion,
    ObjectPoints,
    ObjectTrack3D,
    Pose,
    StereoFramePair,
    Vec3,
)
from surmap.viewer.ask import answer_map_question
from surmap.viewer.snapshot import read_snapshot

_QUESTION = "Where are the survivors?"
_FIXTURE_JPEG = bytes.fromhex("ffd8ffd9")
_CAMERA_POINT = Vec3(0.0, 0.0, 2.0)
_RIG = StereoRig(fx=100.0, fy=100.0, cx=50.0, cy=40.0, baseline_m=0.12)
_POLYGON = ((20.0, 10.0), (80.0, 10.0), (80.0, 70.0), (20.0, 70.0))
_FRAME_WIDTH = 120
_FRAME_HEIGHT = 80
_Segmenter = Callable[[RawFrame], tuple[SamDetection, ...]]
_MAP_BACKEND_FIXTURE = "fixture-cloud"
_MAP_BACKEND_LIVE = "live-rtabmap"
_BASIS_NOTE = (
    "Computed from fixtures. These figures are not a live flight. "
    "Each detection is a recorded camera point posed at a fixed offset "
    "from a person in the ground-truth JSON, then matched by distance."
)


class MissionConfigError(RuntimeError):
    """The mission cannot start with the flags and paths it was given."""


class LiveMap(Protocol):
    """The streaming-map surface the live mission drives.

    ``StreamingRtabmapBackend`` is the production adapter. Tests stand
    in at ``open_live_map``.
    """

    def process_frame(self, frame: StereoFramePair) -> FrameResult: ...

    def flush(self) -> list[FrameResult]: ...

    def map_snapshot(self) -> tuple[Vec3, ...]: ...

    def close(self) -> None: ...


@dataclass(frozen=True)
class MissionAsk:
    """The responder question and the points the viewer should highlight."""

    question: str
    answer: str
    landmark_ids: tuple[str, ...]
    highlight_points: tuple[Vec3, ...]


@dataclass(frozen=True)
class MissionResult:
    """What one command writes and prints."""

    metrics: ImpactMetrics
    snapshot_path: Path
    report_path: Path
    euroc_path: Path
    ask: MissionAsk
    map_backend: str
    scene_note: str


@dataclass(frozen=True)
class LiveServices:
    """Real clients. Constructing them does not send a request."""

    sam: str
    labels: str
    scene_note: str


def gazebo_on_path() -> bool:
    """True when the ``gz`` binary is installed. This does not launch it."""
    return shutil.which("gz") is not None


def live_map_backend() -> str:
    """The live map is PR #38's streaming RTAB-Map backend."""
    return _MAP_BACKEND_LIVE


def open_live_map(calibration: StereoCalibrationSpec) -> LiveMap:
    """Open the streaming backend calibrated from a capture. This starts the sidecar."""
    from surmap.slam.streaming import StreamingRtabmapBackend

    return StreamingRtabmapBackend(
        cam0_yaml=render_cam_sensor_yaml(calibration, 0),
        cam1_yaml=render_cam_sensor_yaml(calibration, 1),
        width=calibration.width,
        height=calibration.height,
    )


def resolve_live_session(capture: Path | None) -> Path:
    """A capture directory, or an error that names how to record one."""
    if capture is not None:
        if not capture.is_dir():
            raise MissionConfigError(f"capture not found: {capture}")
        return capture
    if gazebo_on_path():
        raise MissionConfigError(
            "Gazebo is on PATH. This process does not arm PX4. "
            "Start scripts/launch_disaster_sitl.sh, dump a capture, "
            "and re-run with --live --capture <dir>."
        )
    raise MissionConfigError(
        "Gazebo is not on PATH and no --capture was given. "
        "Record a SITL capture and re-run with --live --capture <dir>."
    )


def build_live_services() -> LiveServices:
    """Check the live flags and keys. Does not send a request or log a key."""
    meta = os.environ.get("SURMAP_LIVE_META") == "1"
    baseten = os.environ.get("SURMAP_LIVE_BASETEN") == "1"
    modal = os.environ.get("SURMAP_LIVE_MODAL") == "1"
    problems: list[str] = []
    if not meta and not modal:
        problems.append("set SURMAP_LIVE_META=1 or SURMAP_LIVE_MODAL=1 for SAM 3.1")
    if not baseten:
        problems.append("set SURMAP_LIVE_BASETEN=1 for Muse Spark labels")
    if not meta:
        problems.append("set SURMAP_LIVE_META=1 for the Meta scene note")
    if problems:
        raise MissionConfigError("; ".join(problems))
    if meta and not os.environ.get("MODEL_API_KEY", "").strip():
        raise MissionConfigError("MODEL_API_KEY is not set")
    if baseten and not os.environ.get("BASETEN_API_KEY", "").strip():
        raise MissionConfigError("BASETEN_API_KEY is not set")
    if modal and not os.environ.get("MODAL_SAM_URL", "").strip():
        raise MissionConfigError("MODAL_SAM_URL is not set")
    sam = "meta" if meta else "modal"
    return LiveServices(sam=sam, labels="baseten", scene_note="meta")


def run_offline_mission(output_dir: Path) -> MissionResult:
    """Fixture session, fixture masks, real projection, fixture labels, real snapshot."""
    output_dir.mkdir(parents=True, exist_ok=True)
    euroc_path = _export_recorded_session(output_dir / "euroc")
    truth = load_disaster_ground_truth()
    spec = load_offline_perception()
    tracks, detections, mask_points, descriptions, model_ids, scene_note = _perceive_fixture(
        truth, spec
    )
    checkpoints = (
        GpsCheckpoint(
            spec.mission_start_ns,
            truth.latitude_deg,
            truth.longitude_deg,
            truth.elevation_m,
            2.0,
        ),
    )
    snapshot = build_snapshot(
        tracks,
        checkpoints,
        descriptions=descriptions,
        model_ids=model_ids,
        mask_points=mask_points,
    )
    snapshot_path = output_dir / "semantic_map_snapshot.json"
    write_snapshot(snapshot, snapshot_path)
    ask = _ask(snapshot_path)
    metrics = score_survivors(
        truth,
        detections,
        mission_start_ns=spec.mission_start_ns,
        match_radius_m=spec.match_radius_m,
        basis="fixtures",
    )
    report_path = output_dir / "impact.json"
    _write_report(
        report_path,
        metrics,
        ask,
        scene_note=scene_note,
        map_backend=_MAP_BACKEND_FIXTURE,
        basis_note=_BASIS_NOTE,
        euroc_path=euroc_path,
        gazebo="not-used",
    )
    return MissionResult(
        metrics=metrics,
        snapshot_path=snapshot_path,
        report_path=report_path,
        euroc_path=euroc_path,
        ask=ask,
        map_backend=_MAP_BACKEND_FIXTURE,
        scene_note=scene_note,
    )


def run_live_mission(output_dir: Path, capture: Path) -> MissionResult:
    """Real SAM, labels, and scene note. The cloud is the streaming RTAB-Map map."""
    capture_dir = resolve_live_session(capture)
    try:
        frames, calibration, gps = load_sitl_capture(capture_dir)
    except (OSError, ValueError) as exc:
        raise MissionConfigError(str(exc)) from exc
    services = build_live_services()
    output_dir.mkdir(parents=True, exist_ok=True)
    euroc_path = export_euroc_session(output_dir / "euroc", frames, calibration, gps).root
    truth = load_disaster_ground_truth()
    backend = live_map_backend()
    map_cloud, poses = _stream_capture(frames, calibration)
    segmenter = _live_segmenter(services.sam)
    labeller = BasetenMuseLabelClient()
    note_client = MetaMuseSceneClient()
    rig = StereoRig(
        calibration.fx,
        calibration.fy,
        calibration.cx,
        calibration.cy,
        calibration.baseline_m,
    )
    tracks: list[ObjectTrack3D] = []
    detections: list[SurvivorDetection] = []
    clouds: dict[int, tuple[Vec3, ...]] = {}
    descriptions: dict[int, str] = {}
    model_ids: dict[int, str] = {}
    labels: list[str] = []
    first_jpeg = _FIXTURE_JPEG
    for frame in frames:
        image = Path(frame.left_ref).read_bytes()
        if image.startswith(b"\xff\xd8"):
            first_jpeg = image
        pose = poses.get(frame.frame_id)
        if pose is None or not map_cloud:
            continue
        raw = RawFrame(
            frame.frame_id,
            frame.t_ns,
            0,
            calibration.width,
            calibration.height,
            "png",
            image,
        )
        camera_cloud = tuple(to_camera_frame(point, pose) for point in map_cloud)
        for detection in segmenter(raw):
            claimed = points_in_mask(
                camera_cloud,
                rig,
                detection.mask_polygon,
                calibration.width,
                calibration.height,
                pose,
            )
            if not claimed:
                continue
            _append_track(
                tracks,
                detections,
                clouds,
                descriptions,
                model_ids,
                labels,
                labeller,
                raw,
                claimed,
                detection.label,
            )
    scene_note = note_client.note(labels or ["none"], _as_jpeg(first_jpeg))
    origin_gps = gps or (
        GpsCheckpoint(
            frames[0].t_ns,
            truth.latitude_deg,
            truth.longitude_deg,
            truth.elevation_m,
            5.0,
        ),
    )
    snapshot_path = output_dir / "semantic_map_snapshot.json"
    write_snapshot(
        build_snapshot(
            tracks,
            origin_gps,
            descriptions=descriptions,
            model_ids=model_ids,
            mask_points=clouds,
        ),
        snapshot_path,
    )
    ask = _ask(snapshot_path)
    start_ns = frames[0].t_ns
    metrics = score_survivors(
        truth,
        detections,
        mission_start_ns=start_ns,
        match_radius_m=load_offline_perception().match_radius_m,
        basis="live",
    )
    note = "Computed from the live run. " + (
        "The cloud came from the live RTAB-Map streaming backend."
        if map_cloud
        else "The live RTAB-Map streaming backend returned no map points, "
        "so positions were not estimated."
    )
    report_path = output_dir / "impact.json"
    _write_report(
        report_path,
        metrics,
        ask,
        scene_note=scene_note,
        map_backend=backend,
        basis_note=note,
        euroc_path=euroc_path,
        gazebo="capture",
    )
    return MissionResult(
        metrics,
        snapshot_path,
        report_path,
        euroc_path,
        ask,
        backend,
        scene_note,
    )


def _stream_capture(
    frames: list[StereoFramePair],
    calibration: StereoCalibrationSpec,
) -> tuple[tuple[Vec3, ...], dict[int, Pose]]:
    """Feed the capture to the streaming backend and read its final map."""
    slam = open_live_map(calibration)
    try:
        for frame in frames:
            slam.process_frame(frame)
        flushed = slam.flush()
        cloud = slam.map_snapshot()
    finally:
        slam.close()
    poses = {result.frame_id: result.pose for result in flushed if result.pose is not None}
    return cloud, poses


def _live_segmenter(kind: str) -> _Segmenter:
    if kind == "meta":
        detector = MetaSamDetector()

        def segment_meta(frame: RawFrame) -> tuple[SamDetection, ...]:
            return asyncio.run(detector.detect(frame))

        return segment_meta
    detector_modal = ModalSamDetector()

    def segment_modal(frame: RawFrame) -> tuple[SamDetection, ...]:
        return asyncio.run(detector_modal.detect(frame))

    return segment_modal


def _export_recorded_session(destination: Path) -> Path:
    capture = _repo_root() / "tests" / "fixtures" / "sitl_capture_tiny"
    frames, calibration, gps = load_sitl_capture(capture)
    return export_euroc_session(destination, frames, calibration, gps).root


def _perceive_fixture(
    truth: DisasterGroundTruth,
    spec: OfflinePerception,
) -> tuple[
    list[ObjectTrack3D],
    list[SurvivorDetection],
    dict[int, tuple[Vec3, ...]],
    dict[int, str],
    dict[int, str],
    str,
]:
    tracks: list[ObjectTrack3D] = []
    detections: list[SurvivorDetection] = []
    clouds: dict[int, tuple[Vec3, ...]] = {}
    descriptions: dict[int, str] = {}
    model_ids: dict[int, str] = {}
    labels: list[str] = []
    included = [person for person in truth.people if person.id not in spec.skip_ids]
    for index, person in enumerate(included):
        t_ns = spec.first_detection_ns + index * spec.step_ns
        target = Vec3(
            person.map_enu.x_m + spec.east_offset_m,
            person.map_enu.y_m + spec.north_offset_m,
            person.map_enu.z_m + spec.up_offset_m,
        )
        pose = Pose(
            Vec3(
                target.x - _CAMERA_POINT.x,
                target.y - _CAMERA_POINT.y,
                target.z - _CAMERA_POINT.z,
            )
        )
        raw = RawFrame(index + 1, t_ns, 0, _FRAME_WIDTH, _FRAME_HEIGHT, "jpeg", _FIXTURE_JPEG)
        detection = _fixture_sam(raw)
        claimed = points_in_mask(
            (_CAMERA_POINT,),
            _RIG,
            detection.mask_polygon,
            _FRAME_WIDTH,
            _FRAME_HEIGHT,
            pose,
        )
        if not claimed:
            raise MissionConfigError(f"fixture mask claimed no points for {person.id}")
        _append_track(
            tracks,
            detections,
            clouds,
            descriptions,
            model_ids,
            labels,
            _FixtureLabeller(),
            raw,
            claimed,
            detection.label,
        )
    scene_note = _FixtureSceneNote().note(labels, _FIXTURE_JPEG)
    return tracks, detections, clouds, descriptions, model_ids, scene_note


def _fixture_sam(frame: RawFrame) -> SamDetection:
    del frame
    return SamDetection(
        label="person",
        score=0.9,
        box_xyxy=(20.0, 10.0, 80.0, 70.0),
        mask_polygon=_POLYGON,
        track_id=None,
    )


class _FixtureLabeller:
    """Stands in for Baseten. The label is the word the viewer question matches."""

    def label(self, jpeg: bytes, coarse_label: str, xyz: Vec3) -> ObjectLabel:
        del jpeg, coarse_label
        return ObjectLabel(
            label="survivor",
            description="survivor in the disaster block",
            confidence=None,
            model_id="fixture",
            raw_text="survivor",
            map_point=xyz,
        )


class _FixtureSceneNote:
    def note(self, labels: list[str], frame_jpeg: bytes) -> str:
        del labels, frame_jpeg
        return "Fixture scene note for a civilian search-and-rescue map. Not a live model call."


def _append_track(
    tracks: list[ObjectTrack3D],
    detections: list[SurvivorDetection],
    clouds: dict[int, tuple[Vec3, ...]],
    descriptions: dict[int, str],
    model_ids: dict[int, str],
    labels: list[str],
    labeller: _FixtureLabeller | BasetenMuseLabelClient,
    raw: RawFrame,
    claimed: tuple[Vec3, ...],
    coarse_label: str,
) -> None:
    centre = centroid(claimed)
    labelled = labeller.label(raw.data, coarse_label, centre)
    track_id = len(tracks) + 1
    tracks.append(
        ObjectTrack3D(
            track_id=track_id,
            label=labelled.label,
            observations=[
                ObjectPoints(
                    track_id=track_id,
                    frame_id=raw.frame_id,
                    t_ns=raw.t_ns,
                    points=claimed,
                    centroid=centre,
                )
            ],
            motion=Motion.UNKNOWN,
        )
    )
    detections.append(SurvivorDetection(centre, raw.t_ns, labelled.label))
    clouds[track_id] = claimed
    descriptions[track_id] = labelled.description
    model_ids[track_id] = labelled.model_id
    labels.append(labelled.label)


def _ask(snapshot_path: Path) -> MissionAsk:
    snapshot = read_snapshot(snapshot_path)
    answer = answer_map_question(_QUESTION, snapshot, snapshot_path=str(snapshot_path))
    return MissionAsk(
        _QUESTION,
        answer.answer,
        answer.landmark_ids,
        answer.highlight_points,
    )


def _write_report(
    path: Path,
    metrics: ImpactMetrics,
    ask: MissionAsk,
    *,
    scene_note: str,
    map_backend: str,
    basis_note: str,
    euroc_path: Path,
    gazebo: str,
) -> None:
    body = {
        "schema": "surmap.mission_impact.v1",
        "basis": metrics.basis,
        "basis_note": basis_note,
        "found": metrics.found,
        "total": metrics.total,
        "mean_position_error_m": metrics.mean_position_error_m,
        "time_to_first_detection_s": metrics.time_to_first_detection_s,
        "match_radius_m": metrics.match_radius_m,
        "matched_ids": list(metrics.matched_ids),
        "missed_ids": list(metrics.missed_ids),
        "ground_truth": "docs/simulation/gz/worlds/disaster_block_ground_truth.json",
        "question": ask.question,
        "ask_answer": ask.answer,
        "landmark_ids": list(ask.landmark_ids),
        "highlight_points": [
            {"x": point.x, "y": point.y, "z": point.z} for point in ask.highlight_points
        ],
        "scene_note": scene_note,
        "map_backend": map_backend,
        "mapqa": (
            "No pull request merged surmap.mapqa. POST /ask calls "
            "surmap.mapqa.answer when SURMAP_LIVE_META=1 and that package "
            "imports. Otherwise it uses the local label match."
        ),
        "live_rtabmap": (
            "PR #38 is integrated. Live mode feeds the capture through "
            "StreamingRtabmapBackend and reads map_snapshot() as the cloud. "
            f"This run's map_backend is {map_backend}."
        ),
        "gazebo": gazebo,
        "euroc_session": str(euroc_path),
    }
    path.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")


def _as_jpeg(image: bytes) -> bytes:
    if image.startswith(b"\xff\xd8"):
        return image
    buffer = io.BytesIO()
    with Image.open(io.BytesIO(image)) as opened:
        opened.convert("RGB").save(buffer, format="JPEG")
    return buffer.getvalue()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]
