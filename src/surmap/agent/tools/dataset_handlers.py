"""The dataset `SurveyTools` handlers: gallery catalogue, prepare, RTAB-Map-only and SAM-only runs.

Split from `handlers.py` at wrap so neither file crosses the 500-line gate;
`handlers` re-exports these names, so callers import from either.
"""

from __future__ import annotations

from connectrpc.code import Code
from connectrpc.errors import ConnectError

from surmap.agent.proto import survey_tools_pb2 as pb
from surmap.agent.tools.onboard import OnboardUnavailable
from surmap.agent.tools.workspace import (
    FrameDetections,
    RunBusy,
    RunInfo,
    RunStatus,
    SurveyWorkspace,
)
from surmap.demo.datasets import GeoPoint, ImageModality, LicenseInfo
from surmap.demo.gallery import GalleryEntry
from surmap.survey.sam import SamDetection

__all__ = [
    "get_dataset",
    "list_datasets",
    "prepare_dataset",
    "run_rtabmap",
    "run_sam_on_dataset",
]

_RUN_STATUS: dict[RunStatus, pb.RunInfo.Status] = {
    RunStatus.RUNNING: pb.RunInfo.RUNNING,
    RunStatus.FINISHED: pb.RunInfo.FINISHED,
    RunStatus.CANCELLED: pb.RunInfo.CANCELLED,
    RunStatus.FAILED: pb.RunInfo.FAILED,
}


_MODALITIES: dict[ImageModality, pb.DatasetModality] = {
    ImageModality.GREY: pb.GREY,
    ImageModality.COLOR: pb.COLOR,
}


def _geo_point(point: GeoPoint) -> pb.DatasetGeoPoint:
    message = pb.DatasetGeoPoint(lon=point.lon, lat=point.lat)
    if point.alt_m is not None:
        message.alt_m = point.alt_m
    return message


def _dataset_message(entry: GalleryEntry) -> pb.DatasetEntry:
    licence: LicenseInfo = entry.license or LicenseInfo(
        name="Not specified", url="", attribution=entry.credit or "Not specified"
    )
    message = pb.DatasetEntry(
        id=entry.dataset_id,
        title=entry.title,
        description=entry.description,
        provider=entry.provider,
        license=pb.DatasetLicense(
            name=licence.name, url=licence.url, attribution=licence.attribution
        ),
        modality=_MODALITIES[entry.modality],
        official_url=entry.official_url,
        default_prompt=entry.default_prompt,
        prepared=entry.prepared,
        frame_count=entry.frame_count,
        thumbnail_available=entry.thumbnail_available,
        location_label=entry.location_label,
        gps_track=[_geo_point(point) for point in entry.gps_track],
        credit=entry.credit,
    )
    if entry.gps_centre is not None:
        message.gps_centre.CopyFrom(_geo_point(entry.gps_centre))
    return message


def _dataset_or_refuse(workspace: SurveyWorkspace, dataset_id: str) -> GalleryEntry:
    entry = workspace.dataset(dataset_id)
    if entry is None:
        raise ConnectError(Code.NOT_FOUND, f"no dataset {dataset_id!r} in the catalogue")
    return entry


async def list_datasets(
    request: pb.ListDatasetsRequest, workspace: SurveyWorkspace
) -> pb.ListDatasetsResponse:
    """`ListDatasets`: every gallery dataset with licence, modality and GPS preview data."""
    return pb.ListDatasetsResponse(
        datasets=[_dataset_message(entry) for entry in workspace.datasets()]
    )


async def get_dataset(
    request: pb.GetDatasetRequest, workspace: SurveyWorkspace
) -> pb.DatasetResponse:
    """`GetDataset`: one gallery dataset by id."""
    return pb.DatasetResponse(
        dataset=_dataset_message(_dataset_or_refuse(workspace, request.dataset_id))
    )


async def prepare_dataset(
    request: pb.PrepareDatasetRequest, workspace: SurveyWorkspace
) -> pb.DatasetResponse:
    """`PrepareDataset`: download and prepare one dataset, then describe it."""
    _dataset_or_refuse(workspace, request.dataset_id)
    try:
        entry = await workspace.prepare_dataset(request.dataset_id)
    except KeyError as missing:
        raise _not_found(missing) from missing
    return pb.DatasetResponse(dataset=_dataset_message(entry))


async def run_rtabmap(
    request: pb.RunRtabmapRequest, workspace: SurveyWorkspace
) -> pb.RunRtabmapResponse:
    """`RunRtabmap`: RTAB-Map alone on a dataset; the recorded run when it ends."""
    _dataset_or_refuse(workspace, request.dataset)
    try:
        run = await workspace.run_rtabmap(
            request.dataset,
            max_frames=request.max_frames if request.HasField("max_frames") else None,
            fps=request.fps if request.HasField("fps") else None,
            onboard_model=request.onboard_model if request.HasField("onboard_model") else None,
        )
    except KeyError as missing:
        raise _not_found(missing) from missing
    except ValueError as bad:
        raise ConnectError(Code.INVALID_ARGUMENT, str(bad)) from bad
    except OnboardUnavailable as unavailable:
        raise ConnectError(Code.FAILED_PRECONDITION, str(unavailable)) from unavailable
    except RunBusy as busy:
        raise ConnectError(Code.UNAVAILABLE, str(busy)) from busy
    return pb.RunRtabmapResponse(run=_run_message(run))


async def run_sam_on_dataset(
    request: pb.RunSamOnDatasetRequest, workspace: SurveyWorkspace
) -> pb.RunSamOnDatasetResponse:
    """`RunSamOnDataset`: SAM alone on evenly spaced frames of a dataset, no run."""
    _dataset_or_refuse(workspace, request.dataset)
    if request.HasField("max_frames") and request.max_frames < 1:
        raise ConnectError(Code.INVALID_ARGUMENT, "max_frames must be at least 1")
    try:
        results = await workspace.run_sam_on_dataset(
            request.dataset,
            request.concept if request.HasField("concept") else None,
            max_frames=request.max_frames if request.HasField("max_frames") else None,
        )
    except KeyError as missing:
        raise _not_found(missing) from missing
    return pb.RunSamOnDatasetResponse(
        dataset_id=request.dataset,
        frames=[_frame_detections(result) for result in results],
    )


def _not_found(missing: KeyError) -> ConnectError:
    detail = missing.args[0] if missing.args else "not found"
    return ConnectError(Code.NOT_FOUND, str(detail))


def _run_message(run: RunInfo) -> pb.RunInfo:
    return pb.RunInfo(
        run_id=run.run_id,
        dataset=run.dataset,
        prompt=run.prompt,
        frames=run.frames,
        objects=run.objects,
        status=_RUN_STATUS[run.status],
        onboard_model=run.onboard_model,
    )


def _frame_detections(result: FrameDetections) -> pb.SamFrameDetections:
    return pb.SamFrameDetections(
        frame_id=result.frame_id,
        t_ns=result.t_ns,
        detections=[
            _detection(f"d{result.frame_id}-{index}", detection)
            for index, detection in enumerate(result.detections)
        ],
    )


def _detection(detection_id: str, detection: SamDetection) -> pb.SamDetection:
    x0, y0, x1, y1 = detection.box_xyxy
    return pb.SamDetection(
        detection_id=detection_id,
        label=detection.label,
        score=0.0 if detection.score is None else detection.score,
        box_xyxy=pb.PixelBox(x0=x0, y0=y0, x1=x1, y1=y1),
        mask_polygon=[pb.PixelPoint(x=x, y=y) for x, y in detection.mask_polygon],
    )
