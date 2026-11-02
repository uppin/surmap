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
import math
import os
import shutil
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol

from PIL import Image

from surmap.geometry import centroid, to_camera_frame
from surmap.labelling.baseten_muse import (
    BasetenMuseLabelClient,
    ObjectLabel,
    _UrllibChatTransport,
)
from surmap.labelling.meta_muse import (
    MetaMuseConceptClient,
    MetaMuseLabelClient,
    MetaMuseSceneClient,
    MetaMuseSceneError,
    UrllibMetaMuseTransport,
)
from surmap.map.snapshot import MetaCallRecord, build_snapshot, write_snapshot
from surmap.mission.metrics import (
    ImpactMetrics,
    OfflinePerception,
    SurvivorDetection,
    load_offline_perception,
    score_survivors,
)
from surmap.mission.recording import (
    SNAPSHOT_FILE,
    CallRecorder,
    RecordedCall,
    Recording,
    RecordingChatTransport,
    RecordingError,
    RecordingMetaMuseTransport,
    RecordingMetaResponsesTransport,
    ReplayChatTransport,
    ReplayMetaMuseTransport,
    ReplayMetaResponsesTransport,
    ReplayQueue,
    has_recording,
    load_recording,
    recording_poster,
    replay_poster,
    write_recording,
)
from surmap.simulation.calibration import StereoCalibrationSpec, render_cam_sensor_yaml
from surmap.simulation.disaster_world import DisasterGroundTruth, load_disaster_ground_truth
from surmap.simulation.euroc_export import export_euroc_session
from surmap.simulation.sitl_capture import load_sitl_capture
from surmap.slam.base import FrameResult
from surmap.slam.streaming import DEFAULT_MAX_DEPTH_M, DEFAULT_MIN_DISPARITY_PX
from surmap.survey.mask_cloud import points_in_mask
from surmap.survey.meta_sam import MetaSamDetector, UrllibMetaTransport
from surmap.survey.modal_sam import ModalSamDetector, post_json
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
from surmap.usage import UsageLedger
from surmap.viewer.ask import answer_map_question
from surmap.viewer.snapshot import read_snapshot

_QUESTION = "Where are the survivors?"
_FIXTURE_JPEG = bytes.fromhex("ffd8ffd9")
_CAMERA_POINT = Vec3(0.0, 0.0, 2.0)
_RIG = StereoRig(fx=100.0, fy=100.0, cx=50.0, cy=40.0, baseline_m=0.12)
_POLYGON = ((20.0, 10.0), (80.0, 10.0), (80.0, 70.0), (20.0, 70.0))
_FRAME_WIDTH = 120
_FRAME_HEIGHT = 80
_Segmenter = Callable[[RawFrame, str], tuple[SamDetection, ...]]
DEFAULT_MAX_CONCEPTS = 4
_MAX_CONCEPTS_LIMIT = 8
DEFAULT_CONCEPT_EVERY = 10


@dataclass(frozen=True)
class _LiveSegmenter:
    """SAM for one frame and one concept. Detectors are cached per concept."""

    model_id: str
    detect: _Segmenter


_MAP_BACKEND_FIXTURE = "fixture-cloud"
_MAP_BACKEND_LIVE = "live-rtabmap"
_BASIS_NOTE = (
    "Computed from fixtures. These figures are not a live flight. "
    "Each detection is a recorded camera point posed at a fixed offset "
    "from a person in the ground-truth JSON, then matched by distance."
)
_SOURCE_FIXTURE = "fixture"
_SOURCE_LIVE = "live"
_SOURCE_RECORDED = "recorded-live"
_REPLAY_KEY = "recorded-replay-no-key"
_MODAL_TIMEOUT_S = 300.0


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


def open_live_map(
    calibration: StereoCalibrationSpec,
    *,
    max_depth_m: float | None = None,
    min_disparity_px: float | None = None,
) -> LiveMap:
    """Open the streaming backend calibrated from a capture. This starts the sidecar."""
    from surmap.slam.streaming import StreamingRtabmapBackend

    depth_m = _resolved_limit(
        max_depth_m,
        "SURMAP_MAX_DEPTH_M",
        DEFAULT_MAX_DEPTH_M,
        minimum=0.0,
        exclusive=True,
    )
    disparity_px = _resolved_limit(
        min_disparity_px,
        "SURMAP_MIN_DISPARITY_PX",
        DEFAULT_MIN_DISPARITY_PX,
        minimum=0.0,
        exclusive=False,
    )
    return StreamingRtabmapBackend(
        cam0_yaml=render_cam_sensor_yaml(calibration, 0),
        cam1_yaml=render_cam_sensor_yaml(calibration, 1),
        width=calibration.width,
        height=calibration.height,
        max_depth_m=depth_m,
        min_disparity_px=disparity_px,
        fx=calibration.fx,
        baseline_m=calibration.baseline_m,
    )


def _resolved_limit(
    explicit: float | None,
    env_name: str,
    default: float,
    *,
    minimum: float,
    exclusive: bool,
) -> float:
    """Explicit argument, otherwise the environment, otherwise `default`."""
    if explicit is None:
        raw = os.environ.get(env_name, "").strip()
        if not raw:
            return default
        try:
            explicit = float(raw)
        except ValueError as exc:
            raise MissionConfigError(f"{env_name} must be a number") from exc
    if exclusive:
        if explicit <= minimum:
            raise MissionConfigError(f"{env_name} must be greater than {minimum}")
    elif explicit < minimum:
        raise MissionConfigError(f"{env_name} must be at least {minimum}")
    return explicit


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


def live_sam_prompt() -> str:
    """Noun sent to SAM. ``SURMAP_SAM_PROMPT`` overrides the default ``person``."""
    chosen = os.environ.get("SURMAP_SAM_PROMPT", "").strip()
    return chosen or "person"


def pinned_sam_prompt() -> str | None:
    """``SURMAP_SAM_PROMPT`` when set. It wins over Muse Spark's concept list."""
    chosen = os.environ.get("SURMAP_SAM_PROMPT", "").strip()
    return chosen or None


def live_max_concepts() -> int:
    """Concepts per keyframe (``SURMAP_SAM_MAX_CONCEPTS``, 1 to 8, default 4)."""
    return _env_int("SURMAP_SAM_MAX_CONCEPTS", DEFAULT_MAX_CONCEPTS, 1, _MAX_CONCEPTS_LIMIT)


def live_concept_every() -> int:
    """Ask Muse Spark for new concepts every N posed frames (``SURMAP_CONCEPT_EVERY``)."""
    return _env_int("SURMAP_CONCEPT_EVERY", DEFAULT_CONCEPT_EVERY, 1, 10_000)


def _env_int(name: str, default: int, low: int, high: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise MissionConfigError(f"{name} must be an integer") from exc
    if not low <= value <= high:
        raise MissionConfigError(f"{name} must be between {low} and {high}")
    return value


def live_raw_frame(frame_id: int, t_ns: int, width: int, height: int, image: bytes) -> RawFrame:
    """A capture image as ``mjpeg`` or ``raw_rgb``. Never the encoding ``png``."""
    if image.startswith(b"\xff\xd8"):
        return RawFrame(frame_id, t_ns, 0, width, height, "mjpeg", image)
    if len(image) == width * height * 3:
        return RawFrame(frame_id, t_ns, 0, width, height, "raw_rgb", image)
    with Image.open(io.BytesIO(image)) as opened:
        rgb = opened.convert("RGB").resize((width, height))
    return RawFrame(frame_id, t_ns, 0, width, height, "raw_rgb", rgb.tobytes())


def detection_crop_jpeg(
    image: bytes,
    box: tuple[float, float, float, float],
    *,
    pad: int = 16,
) -> bytes:
    """JPEG of ``box`` expanded by ``pad`` pixels. Undecodable bytes come back unchanged."""
    try:
        with Image.open(io.BytesIO(image)) as opened:
            rgb = opened.convert("RGB")
    except (OSError, ValueError):
        return image
    width, height = rgb.size
    x0, y0, x1, y1 = box
    left = max(0, math.floor(min(x0, x1)) - pad)
    top = max(0, math.floor(min(y0, y1)) - pad)
    right = min(width, math.ceil(max(x0, x1)) + pad)
    bottom = min(height, math.ceil(max(y0, y1)) + pad)
    crop = rgb if right <= left or bottom <= top else rgb.crop((left, top, right, bottom))
    out = io.BytesIO()
    crop.save(out, format="JPEG", quality=85)
    return out.getvalue()


def build_live_services(*, sam_route: str | None = None) -> LiveServices:
    """Check the live flags and keys. Does not send a request or log a key.

    ``SURMAP_LIVE_META=1`` selects Meta SAM, Muse Spark labels, and the
    Muse Spark scene note. Baseten labels and Modal SAM are used only
    when that Meta flag is unset and their own flags are set. The Meta
    scene note is then ``none``.

    ``sam_route`` (``meta`` or ``modal``) pins only the SAM adapter, for
    example to benchmark Modal SAM while Meta still labels and writes
    the scene note. ``None`` keeps the default above: Meta SAM whenever
    ``SURMAP_LIVE_META=1``.
    """
    meta = os.environ.get("SURMAP_LIVE_META") == "1"
    baseten = os.environ.get("SURMAP_LIVE_BASETEN") == "1"
    modal = os.environ.get("SURMAP_LIVE_MODAL") == "1"
    if meta:
        sam, labels, scene = "meta", "meta", "meta"
    else:
        sam = "modal" if modal else ""
        labels = "baseten" if baseten else ""
        scene = "none"
        problems: list[str] = []
        if not sam and sam_route is None:
            problems.append("set SURMAP_LIVE_META=1 or SURMAP_LIVE_MODAL=1 for SAM 3.1")
        if not labels:
            problems.append("set SURMAP_LIVE_META=1 or SURMAP_LIVE_BASETEN=1 for labels")
        if problems:
            raise MissionConfigError("; ".join(problems))
    sam = resolve_sam_route(sam_route, default=sam, meta=meta, modal=modal)
    if (meta or sam == "meta") and not os.environ.get("MODEL_API_KEY", "").strip():
        raise MissionConfigError("MODEL_API_KEY is not set")
    if labels == "baseten" and not os.environ.get("BASETEN_API_KEY", "").strip():
        raise MissionConfigError("BASETEN_API_KEY is not set")
    if sam == "modal" and not os.environ.get("MODAL_SAM_URL", "").strip():
        raise MissionConfigError("MODAL_SAM_URL is not set")
    return LiveServices(sam=sam, labels=labels, scene_note=scene)


def resolve_sam_route(explicit: str | None, *, default: str, meta: bool, modal: bool) -> str:
    """The SAM adapter: ``default`` unless an explicit route is given.

    Labels and the scene note do not follow this choice.
    """
    if explicit is None:
        return default
    if explicit == "meta":
        if not meta:
            raise MissionConfigError("set SURMAP_LIVE_META=1 for --sam-route meta")
        return "meta"
    if explicit == "modal":
        if not modal:
            raise MissionConfigError("set SURMAP_LIVE_MODAL=1 for --sam-route modal")
        return "modal"
    raise MissionConfigError("--sam-route must be meta or modal")


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
        meta_calls=(),
        model_call_source=_SOURCE_FIXTURE,
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


def run_live_mission(
    output_dir: Path,
    capture: Path,
    *,
    max_depth_m: float | None = None,
    min_disparity_px: float | None = None,
    sam_route: str | None = None,
    record_dir: Path | None = None,
) -> MissionResult:
    """Real SAM, labels, and scene note. The cloud is the streaming RTAB-Map map.

    ``record_dir`` writes every model request (auth dropped, media
    hashed) and response there, plus the snapshot and report, so
    offline mode can replay the run.
    """
    capture_dir = resolve_live_session(capture)
    try:
        frames, calibration, gps = load_sitl_capture(capture_dir)
    except (OSError, ValueError) as exc:
        raise MissionConfigError(str(exc)) from exc
    services = build_live_services(sam_route=sam_route)
    output_dir.mkdir(parents=True, exist_ok=True)
    euroc_path = export_euroc_session(output_dir / "euroc", frames, calibration, gps).root
    truth = load_disaster_ground_truth()
    backend = live_map_backend()
    map_cloud, poses = _stream_capture(
        frames,
        calibration,
        max_depth_m=max_depth_m,
        min_disparity_px=min_disparity_px,
    )
    recorder = CallRecorder() if record_dir is not None else None
    segmenter = _live_segmenter(services.sam, recorder=recorder)
    labeller = _live_labeller(services.labels, recorder)
    note_client = (
        MetaMuseSceneClient(transport=_meta_muse_transport(recorder, "scene_note"))
        if services.scene_note == "meta"
        else None
    )
    pinned = pinned_sam_prompt()
    concept_client = (
        MetaMuseConceptClient(
            transport=_meta_muse_transport(recorder, "concepts"),
            max_concepts=live_max_concepts(),
        )
        if services.scene_note == "meta" and pinned is None
        else None
    )
    concept_every = live_concept_every()
    concepts: tuple[str, ...] = (pinned or live_sam_prompt(),)
    posed = 0
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
    meta_calls: list[MetaCallRecord] = []
    first_jpeg = _FIXTURE_JPEG
    for frame in frames:
        image = Path(frame.left_ref).read_bytes()
        if first_jpeg == _FIXTURE_JPEG:
            first_jpeg = _as_jpeg(image)
        pose = poses.get(frame.frame_id)
        if pose is None or not map_cloud:
            continue
        raw = live_raw_frame(
            frame.frame_id,
            frame.t_ns,
            calibration.width,
            calibration.height,
            image,
        )
        camera_cloud = tuple(to_camera_frame(point, pose) for point in map_cloud)
        if concept_client is not None and posed % concept_every == 0:
            concepts = _propose_concepts(concept_client, _as_jpeg(image), concepts, meta_calls)
        posed += 1
        found: list[SamDetection] = []
        for concept in concepts:
            started = time.perf_counter()
            batch = segmenter.detect(raw, concept)
            elapsed = time.perf_counter() - started
            meta_calls.append(
                MetaCallRecord(
                    "sam",
                    segmenter.model_id,
                    elapsed,
                    tuple(detection.score for detection in batch),
                )
            )
            found.extend(batch)
        for detection in found:
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
                detection.box_xyxy,
                meta_calls,
            )
    if note_client is None:
        scene_note = "Scene note was not requested."
    else:
        started = time.perf_counter()
        scene_note = note_client.note(labels or ["none"], _as_jpeg(first_jpeg))
        meta_calls.append(
            MetaCallRecord(
                "scene_note",
                note_client.model,
                time.perf_counter() - started,
            )
        )
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
        replace(
            build_snapshot(
                tracks,
                origin_gps,
                descriptions=descriptions,
                model_ids=model_ids,
                mask_points=clouds,
            ),
            meta_calls=tuple(meta_calls),
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
        meta_calls=tuple(meta_calls),
        model_call_source=_SOURCE_LIVE,
    )
    if recorder is not None and record_dir is not None:
        write_recording(
            record_dir,
            recorder,
            snapshot_path=snapshot_path,
            impact_path=report_path,
            capture_name=capture_dir.name,
            services={
                "sam": services.sam,
                "labels": services.labels,
                "scene_note": services.scene_note,
            },
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
    *,
    max_depth_m: float | None = None,
    min_disparity_px: float | None = None,
) -> tuple[tuple[Vec3, ...], dict[int, Pose]]:
    """Feed the capture to the streaming backend and read its final map."""
    slam = open_live_map(
        calibration,
        max_depth_m=max_depth_m,
        min_disparity_px=min_disparity_px,
    )
    try:
        for frame in frames:
            slam.process_frame(frame)
        flushed = slam.flush()
        cloud = slam.map_snapshot()
    finally:
        slam.close()
    poses = {result.frame_id: result.pose for result in flushed if result.pose is not None}
    return cloud, poses


def _meta_muse_transport(
    recorder: CallRecorder | None, role: str
) -> UrllibMetaMuseTransport | RecordingMetaMuseTransport:
    inner = UrllibMetaMuseTransport()
    if recorder is None:
        return inner
    return RecordingMetaMuseTransport(inner, recorder, role=role)


def _live_labeller(
    kind: str, recorder: CallRecorder | None
) -> BasetenMuseLabelClient | MetaMuseLabelClient:
    if kind == "baseten":
        if recorder is None:
            return BasetenMuseLabelClient()
        return BasetenMuseLabelClient(
            transport=RecordingChatTransport(_UrllibChatTransport(120.0), recorder, role="label")
        )
    return MetaMuseLabelClient(transport=_meta_muse_transport(recorder, "label"))


def _propose_concepts(
    client: MetaMuseConceptClient,
    frame_jpeg: bytes,
    previous: tuple[str, ...],
    meta_calls: list[MetaCallRecord],
) -> tuple[str, ...]:
    """Muse Spark's concepts for this keyframe; the previous list if the reply is unusable."""
    started = time.perf_counter()
    try:
        chosen = client.propose(frame_jpeg)
    except MetaMuseSceneError:
        chosen = previous
    meta_calls.append(MetaCallRecord("concepts", client.model, time.perf_counter() - started))
    return chosen


def _live_segmenter(kind: str, *, recorder: CallRecorder | None = None) -> _LiveSegmenter:
    if kind == "meta":
        transport = (
            None
            if recorder is None
            else RecordingMetaResponsesTransport(UrllibMetaTransport(), recorder, role="sam")
        )
        meta_detectors: dict[str, MetaSamDetector] = {}

        def segment_meta(frame: RawFrame, concept: str) -> tuple[SamDetection, ...]:
            detector = meta_detectors.get(concept)
            if detector is None:
                detector = MetaSamDetector(prompt=concept, transport=transport)
                meta_detectors[concept] = detector
            return asyncio.run(detector.detect(frame))

        return _LiveSegmenter(MetaSamDetector(prompt=live_sam_prompt()).model, segment_meta)
    poster = None
    if recorder is not None:

        def send(url: str, body: bytes) -> bytes:
            return post_json(url, body, timeout_s=_MODAL_TIMEOUT_S)

        poster = recording_poster(send, recorder, role="sam", model="surmap-sam")
    modal_detectors: dict[str, ModalSamDetector] = {}

    def segment_modal(frame: RawFrame, concept: str) -> tuple[SamDetection, ...]:
        detector = modal_detectors.get(concept)
        if detector is None:
            detector = ModalSamDetector(prompt=concept, poster=poster)
            modal_detectors[concept] = detector
        return asyncio.run(detector.detect(frame))

    probe = ModalSamDetector(prompt=live_sam_prompt(), poster=poster)
    return _LiveSegmenter(probe._model, segment_modal)


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
    labeller: _FixtureLabeller | BasetenMuseLabelClient | MetaMuseLabelClient,
    raw: RawFrame,
    claimed: tuple[Vec3, ...],
    coarse_label: str,
    box: tuple[float, float, float, float] | None = None,
    meta_calls: list[MetaCallRecord] | None = None,
) -> None:
    centre = centroid(claimed)
    jpeg = raw.data if box is None else detection_crop_jpeg(_crop_source(raw), box)
    started = time.perf_counter()
    labelled = labeller.label(jpeg, coarse_label, centre)
    if meta_calls is not None:
        meta_calls.append(MetaCallRecord("label", labelled.model_id, time.perf_counter() - started))
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
    # The mission's own answer stays on the label match: it opens no socket
    # and adds no unrecorded Meta call to the report's ledger.
    answer = answer_map_question(
        _QUESTION, snapshot, snapshot_path=str(snapshot_path), allow_live=False
    )
    return MissionAsk(
        _QUESTION,
        answer.answer,
        answer.landmark_ids,
        answer.highlight_points,
    )


def _crop_source(frame: RawFrame) -> bytes:
    if frame.encoding != "raw_rgb":
        return frame.data
    image = Image.frombytes("RGB", (frame.width, frame.height), frame.data)
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


def _meta_call_json(call: MetaCallRecord, source: str) -> dict[str, object]:
    return {
        "role": call.role,
        "model_id": call.model_id,
        "elapsed_s": call.elapsed_s,
        "confidences": list(call.confidences),
        "source": source,
    }


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
    meta_calls: Sequence[MetaCallRecord],
    model_call_source: str,
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
        "model_call_source": model_call_source,
        "meta_calls": [_meta_call_json(call, model_call_source) for call in meta_calls],
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


DEFAULT_RECORDING = Path("demo") / "recordings" / "mission"


def default_recording_dir() -> Path | None:
    """The committed recording replayed by default, or ``None`` when absent."""
    root = _repo_root() / DEFAULT_RECORDING
    return root if has_recording(root) else None


@dataclass(frozen=True)
class ReplayedCall:
    """A recorded response after the production client parsed it again."""

    call: RecordedCall
    output: str

    def to_json(self) -> dict[str, object]:
        return {
            "role": self.call.role,
            "provider": self.call.provider,
            "model_id": self.call.model,
            "recorded_at": self.call.recorded_at,
            "elapsed_s": self.call.elapsed_s,
            "source": self.call.source,
            "output": self.output,
        }


def replay_model_calls(recording: Recording) -> tuple[ReplayedCall, ...]:
    """Feed every recorded response back through the client that made it.

    Nothing is sent: each client gets a replay transport. A response the
    client cannot parse raises ``RecordingError``.
    """
    queues: dict[tuple[str, str], ReplayQueue] = {}
    for call in recording.calls:
        key = (call.role, call.provider)
        if key not in queues:
            queues[key] = ReplayQueue(
                [item for item in recording.calls if item.provider == call.provider],
                call.role,
            )
    replayed: list[ReplayedCall] = []
    consumed: set[int] = set()
    for call in recording.calls:
        if call.seq in consumed:
            continue
        queue = queues[(call.role, call.provider)]
        before = len(queue.used)
        try:
            output = _replay_one(call, queue)
        except RecordingError:
            raise
        except Exception as exc:  # noqa: BLE001 - any client failure means a bad recording
            raise RecordingError(
                f"recorded call {call.seq} ({call.role}) did not parse: {exc}"
            ) from exc
        consumed.update(item.seq for item in queue.used[before:])
        replayed.append(ReplayedCall(call, output))
    return tuple(replayed)


def _replay_one(call: RecordedCall, queue: ReplayQueue) -> str:
    model = call.model or None
    if call.provider == "meta" and call.role == "scene_note":
        note = MetaMuseSceneClient(
            transport=ReplayMetaMuseTransport(queue), api_key=_REPLAY_KEY, model=model
        )
        return note.note(["recorded"], _FIXTURE_JPEG)
    if call.provider == "meta" and call.role == "concepts":
        proposer = MetaMuseConceptClient(
            transport=ReplayMetaMuseTransport(queue), api_key=_REPLAY_KEY, model=model
        )
        return ", ".join(proposer.propose(_FIXTURE_JPEG))
    if call.provider == "meta" and call.role == "label":
        labeller = MetaMuseLabelClient(
            transport=ReplayMetaMuseTransport(queue), api_key=_REPLAY_KEY, model=model
        )
        return labeller.label(_FIXTURE_JPEG, "object", _CAMERA_POINT).label
    if call.provider == "baseten" and call.role == "label":
        baseten = BasetenMuseLabelClient(
            api_key=_REPLAY_KEY,
            model_id=call.model or "meta-models/muse-spark-open-1026",
            transport=ReplayChatTransport(queue),
            ledger=UsageLedger(os.devnull),
        )
        return baseten.label(_FIXTURE_JPEG, "object", _CAMERA_POINT).label
    if call.provider == "meta" and call.role == "sam":
        concept = _recorded_prompt(call) or "object"
        sam = MetaSamDetector(
            api_key=_REPLAY_KEY,
            model=call.model or "sam-3.1",
            prompt=concept,
            transport=ReplayMetaResponsesTransport(queue),
        )
        frame = RawFrame(0, 0, 0, _FRAME_WIDTH, _FRAME_HEIGHT, "mjpeg", _FIXTURE_JPEG)
        found = asyncio.run(sam.detect(frame))
        return f"{len(found)} mask(s) for {concept!r}"
    if call.provider == "modal" and call.role == "sam":
        modal = ModalSamDetector(
            "https://recorded.invalid/sam",
            prompt=_recorded_prompt(call) or "person",
            poster=replay_poster(queue),
        )
        found_modal = modal.segment(_FIXTURE_JPEG)
        return f"{len(found_modal)} mask(s) for {modal.prompt!r}"
    queue.next()
    return ""


def _recorded_prompt(call: RecordedCall) -> str:
    """The concept a SAM request asked for, read from the recorded body."""
    body = call.request.get("body")
    if not isinstance(body, dict):
        return ""
    prompt = body.get("prompt")
    if isinstance(prompt, str):
        return prompt
    texts: list[str] = []
    _collect_input_text(body.get("input"), texts)
    return texts[0].strip() if texts else ""


def _collect_input_text(value: object, out: list[str]) -> None:
    if isinstance(value, list):
        for item in value:
            _collect_input_text(item, out)
    elif isinstance(value, dict):
        if value.get("type") == "input_text" and isinstance(value.get("text"), str):
            out.append(str(value["text"]))
        _collect_input_text(value.get("content"), out)


def run_recorded_mission(output_dir: Path, recording_dir: Path) -> MissionResult:
    """Show a recorded live run. Replays its model responses; sends nothing."""
    recording = load_recording(recording_dir)
    replayed = replay_model_calls(recording)
    output_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = output_dir / SNAPSHOT_FILE
    shutil.copyfile(recording.snapshot_path, snapshot_path)
    recorded = json.loads(recording.impact_path.read_text(encoding="utf-8"))
    if not isinstance(recorded, dict):
        raise RecordingError("recorded impact report is not a JSON object")
    metrics = _recorded_metrics(recorded)
    ask = _ask(snapshot_path)
    notes = [item.output for item in replayed if item.call.role == "scene_note"]
    scene_note = notes[-1] if notes else str(recorded.get("scene_note", ""))
    capture = recording.manifest.get("capture", "a SITL capture")
    body = dict(recorded)
    body.update(
        {
            "basis": _SOURCE_RECORDED,
            "basis_note": (
                f"Recorded live run of {capture} at {recording.recorded_at}. The map and "
                "metrics were computed during that run. Each model response below is "
                "replayed from the recording through the production client; nothing is sent."
            ),
            "recorded_at": recording.recorded_at,
            "recording": str(recording.root),
            "question": ask.question,
            "ask_answer": ask.answer,
            "landmark_ids": list(ask.landmark_ids),
            "highlight_points": [
                {"x": point.x, "y": point.y, "z": point.z} for point in ask.highlight_points
            ],
            "scene_note": scene_note,
            "model_call_source": _SOURCE_RECORDED,
            "model_calls": [item.to_json() for item in replayed],
        }
    )
    report_path = output_dir / "impact.json"
    report_path.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    return MissionResult(
        metrics=metrics,
        snapshot_path=snapshot_path,
        report_path=report_path,
        euroc_path=recording.root,
        ask=ask,
        map_backend=str(recorded.get("map_backend", _MAP_BACKEND_LIVE)),
        scene_note=scene_note,
    )


def _recorded_metrics(body: dict[str, object]) -> ImpactMetrics:
    def number(name: str) -> float | None:
        value = body.get(name)
        if isinstance(value, bool) or not isinstance(value, int | float):
            return None
        return float(value)

    def count(name: str) -> int:
        value = body.get(name)
        return value if isinstance(value, int) and not isinstance(value, bool) else 0

    def ids(name: str) -> tuple[str, ...]:
        value = body.get(name)
        return tuple(str(item) for item in value) if isinstance(value, list) else ()

    radius = number("match_radius_m")
    return ImpactMetrics(
        found=count("found"),
        total=count("total"),
        mean_position_error_m=number("mean_position_error_m"),
        time_to_first_detection_s=number("time_to_first_detection_s"),
        basis=_SOURCE_RECORDED,
        matched_ids=ids("matched_ids"),
        missed_ids=ids("missed_ids"),
        match_radius_m=radius if radius is not None else 3.0,
    )
