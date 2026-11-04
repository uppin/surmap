"""The `surmap.agent.v1.SurveyTools` handlers: proto request in, proto response out.

One async function per rpc, each taking its decoded request and a `SurveyWorkspace`, so they
test with no model and no server. `survey_tool_handlers(workspace)` binds them by rpc name in
connect-python's `(request, ctx)` shape, ready for `surmap.agent.services.survey_tools_module`.

Failures are `ConnectError`s: `NOT_FOUND` for a run, scene, frame or object the workspace does
not have, `INVALID_ARGUMENT` for a request that contradicts itself (`near` without `radius_m`)
or names no on-board model, `FAILED_PRECONDITION` for an on-board model the station lacks.
Object coordinates are in the run's map frame (`frame="map"`, up axis `-y`).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import replace
from typing import Any

import numpy as np
from connectrpc.code import Code
from connectrpc.errors import ConnectError
from numpy.typing import NDArray

from surmap.agent.proto import survey_tools_pb2 as pb
from surmap.agent.services import Handler
from surmap.agent.tools.dataset_handlers import (
    _RUN_STATUS,
    _frame_detections,
    _not_found,
    _run_message,
    get_dataset,
    list_datasets,
    list_runs,
    prepare_dataset,
    run_cached,
    run_rtabmap,
    run_sam_on_dataset,
)
from surmap.agent.tools.frames import crop_box_for_object, frame_image
from surmap.agent.tools.onboard import ONBOARD_OFF, OnboardUnavailable
from surmap.agent.tools.workspace import (
    OBJECT_FRAME,
    OBJECT_UP_AXIS,
    BoxXYXY,
    FrameRecord,
    FrameSource,
    RunBusy,
    RunInfo,
    StoredObject,
    SurveyWorkspace,
)
from surmap.objects3d import (
    ObjectSummary,
    ObjTextLimits,
    Relation,
    ShapeClass,
    encode_obj_text,
    neighbours,
    summarize,
)

__all__ = [
    "MAX_SAM_FRAMES",
    "OBJECT_CROP_PAD_PX",
    "find_objects",
    "get_frame",
    "get_object",
    "get_object_geometry",
    "get_dataset",
    "get_run",
    "list_datasets",
    "list_demos",
    "list_onboard_models",
    "list_runs",
    "prepare_dataset",
    "run_cached",
    "run_rtabmap",
    "run_sam_on_dataset",
    "object_summary_message",
    "prompt_sam",
    "run_demo",
    "survey_tool_handlers",
]

MAX_SAM_FRAMES = 8
"""The most frames one `prompt_sam` call segments."""

OBJECT_CROP_PAD_PX = 16
"""Padding around an object's mask box when `get_frame` crops to an object without `pad_px`."""

_SHAPES: dict[ShapeClass, pb.Shape] = {
    ShapeClass.LINEAR: pb.LINEAR,
    ShapeClass.PLANAR: pb.PLANAR,
    ShapeClass.VOLUMETRIC: pb.VOLUMETRIC,
}
_RELATIONS: dict[Relation, pb.Relation] = {
    Relation.ABOVE: pb.ABOVE,
    Relation.BELOW: pb.BELOW,
    Relation.NEXT_TO: pb.NEXT_TO,
    Relation.OVERLAPS: pb.OVERLAPS,
}
_SOURCES: dict[FrameSource, pb.FrameSource] = {
    FrameSource.FULL: pb.FULL,
    FrameSource.DISPLAY: pb.DISPLAY,
}


def survey_tool_handlers(workspace: SurveyWorkspace) -> Mapping[str, Handler]:
    """Every `SurveyTools` rpc, by rpc name, as a `(request, ctx)` handler over `workspace`."""

    def bind(tool: Callable[[Any, SurveyWorkspace], Awaitable[Any]]) -> Handler:
        async def serve(request: object, _ctx: object) -> Any:
            return await tool(request, workspace)

        return serve

    return {
        "ListDemos": bind(list_demos),
        "ListOnboardModels": bind(list_onboard_models),
        "RunDemo": bind(run_demo),
        "GetRun": bind(get_run),
        "PromptSam": bind(prompt_sam),
        "FindObjects": bind(find_objects),
        "GetObject": bind(get_object),
        "GetObjectGeometry": bind(get_object_geometry),
        "GetFrame": bind(get_frame),
        "ListDatasets": bind(list_datasets),
        "GetDataset": bind(get_dataset),
        "PrepareDataset": bind(prepare_dataset),
        "RunRtabmap": bind(run_rtabmap),
        "RunSamOnDataset": bind(run_sam_on_dataset),
        "ListRuns": bind(list_runs),
        "RunCached": bind(run_cached),
    }


async def list_demos(
    request: pb.ListDemosRequest, workspace: SurveyWorkspace
) -> pb.ListDemosResponse:
    """`ListDemos`: every scene, its default prompt, whether it is prepared, its cached run."""
    scenes: list[pb.DemoScene] = []
    for scene in workspace.scenes():
        message = pb.DemoScene(
            id=scene.id,
            title=scene.title,
            default_prompt=scene.default_prompt,
            prepared=scene.prepared,
        )
        if scene.cached_run_id is not None:
            message.cached_run_id = scene.cached_run_id
        scenes.append(message)
    return pb.ListDemosResponse(scenes=scenes)


async def list_onboard_models(
    request: pb.ListOnboardModelsRequest, workspace: SurveyWorkspace
) -> pb.ListOnboardModelsResponse:
    """`ListOnboardModels`: every on-board model, whether the station has it, the default."""
    models = workspace.onboard_models()
    default = next((model.name for model in models if model.is_default), ONBOARD_OFF)
    return pb.ListOnboardModelsResponse(
        models=[
            pb.OnboardModel(
                name=model.name,
                title=model.title,
                note=model.note,
                available=model.available,
                is_default=model.is_default,
                classes=model.classes,
            )
            for model in models
        ],
        default_model=default,
    )


async def run_demo(request: pb.RunDemoRequest, workspace: SurveyWorkspace) -> pb.RunDemoResponse:
    """`RunDemo`: run a scene headlessly and answer when it ends; cancelling stops the run."""
    try:
        run = await workspace.run_demo(
            request.dataset,
            request.prompt if request.HasField("prompt") else None,
            max_frames=request.max_frames if request.HasField("max_frames") else None,
            fps=request.fps if request.HasField("fps") else None,
            onboard_model=request.onboard_model if request.HasField("onboard_model") else None,
            rebuild=request.rebuild,
        )
    except KeyError as missing:
        raise _not_found(missing) from missing
    except ValueError as bad:
        raise ConnectError(Code.INVALID_ARGUMENT, str(bad)) from bad
    except OnboardUnavailable as unavailable:
        raise ConnectError(Code.FAILED_PRECONDITION, str(unavailable)) from unavailable
    except RunBusy as busy:
        raise ConnectError(Code.UNAVAILABLE, str(busy)) from busy
    response = pb.RunDemoResponse(
        run_id=run.run_id,
        frames=run.frames,
        objects=run.objects,
        status=_RUN_STATUS[run.status],
        onboard_model=run.onboard_model,
        cached=run.cached,
    )
    onboard = next((m for m in workspace.onboard_models() if m.name == run.onboard_model), None)
    if onboard is not None and run.prompt:
        response.onboard_recognises_prompt = onboard.recognises(run.prompt)
    return response


async def get_run(request: pb.GetRunRequest, workspace: SurveyWorkspace) -> pb.GetRunResponse:
    """`GetRun`: one recorded run's scene, prompt, frame and object counts and status."""
    return pb.GetRunResponse(run=_run_message(_run_or_refuse(workspace, request.run_id)))


async def prompt_sam(
    request: pb.PromptSamRequest, workspace: SurveyWorkspace
) -> pb.PromptSamResponse:
    """`PromptSam`: SAM on chosen frames of a recorded run, or on up to `MAX_SAM_FRAMES`
    evenly spaced ones (first and last included) when none are chosen."""
    _run_or_refuse(workspace, request.run_id)
    if request.frame_ids:
        frame_ids = sorted(set(request.frame_ids))[:MAX_SAM_FRAMES]
    else:
        frame_ids = _evenly_spaced(workspace.timeline(request.run_id), _sam_budget(request))
    try:
        results = await workspace.detect(request.run_id, request.concept, frame_ids)
    except KeyError as missing:
        raise _not_found(missing) from missing
    return pb.PromptSamResponse(frames=[_frame_detections(result) for result in results])


async def find_objects(
    request: pb.FindObjectsRequest, workspace: SurveyWorkspace
) -> pb.FindObjectsResponse:
    """`FindObjects`: the run's object summaries matching label, `near`/`radius_m` and `moving`.

    With `near`, nearest first by the distance from the point to each object's axis-aligned
    box; otherwise largest (most points) first. `limit` caps the count.
    """
    if request.HasField("near") and not request.HasField("radius_m"):
        raise ConnectError(Code.INVALID_ARGUMENT, "near needs radius_m: how far to look")
    run_id = request.run_id
    found = list(_objects_of(workspace, run_id))
    if request.HasField("label"):
        found = [obj for obj in found if obj.label == request.label]
    if request.HasField("moving"):
        found = [obj for obj in found if obj.moving == request.moving]
    if request.HasField("near"):
        point = np.array([request.near.x, request.near.y, request.near.z], dtype=np.float64)
        distance = {obj.object_id: _distance_to_box(point, obj.points) for obj in found}
        found = sorted(
            (obj for obj in found if distance[obj.object_id] <= request.radius_m),
            key=lambda obj: distance[obj.object_id],
        )
    else:
        found = sorted(found, key=lambda obj: -len(obj.points))
    if request.HasField("limit"):
        found = found[: request.limit]
    return pb.FindObjectsResponse(
        objects=[
            object_summary_message(
                _summarise(obj, geometry_uri=workspace.publish_geometry(run_id, obj)),
                moving=obj.moving,
            )
            for obj in found
        ]
    )


async def get_object(
    request: pb.GetObjectRequest, workspace: SurveyWorkspace
) -> pb.GetObjectResponse:
    """`GetObject`: one object's summary with its nearest neighbours filled in."""
    objects = _objects_of(workspace, request.run_id)
    target = _object_or_refuse(objects, request.object_id)
    summaries = {obj.object_id: _summarise(obj) for obj in objects}
    own = summaries[target.object_id]
    summary = replace(
        own,
        neighbours=neighbours(own, list(summaries.values())),
        geometry_uri=workspace.publish_geometry(request.run_id, target),
    )
    return pb.GetObjectResponse(object=object_summary_message(summary, moving=target.moving))


async def get_object_geometry(
    request: pb.GetObjectGeometryRequest, workspace: SurveyWorkspace
) -> pb.GetObjectGeometryResponse:
    """`GetObjectGeometry`: `surmap-obj v1` text within `max_points` / `voxel_m`, and the
    object's GLB URI."""
    target = _object_or_refuse(_objects_of(workspace, request.run_id), request.object_id)
    defaults = ObjTextLimits()
    limits = ObjTextLimits(
        voxel_m=request.voxel_m if request.HasField("voxel_m") else defaults.voxel_m,
        max_points=request.max_points if request.HasField("max_points") else defaults.max_points,
    )
    try:
        text = encode_obj_text(_summarise(target), target.points, limits=limits)
    except ValueError as bad:
        raise ConnectError(Code.INVALID_ARGUMENT, str(bad)) from bad
    return pb.GetObjectGeometryResponse(
        obj_text=text,
        geometry_uri=workspace.publish_geometry(request.run_id, target),
        decimated_from=len(target.points),
    )


async def get_frame(request: pb.GetFrameRequest, workspace: SurveyWorkspace) -> pb.GetFrameResponse:
    """`GetFrame`: one frame as a JPEG, picked by index, id or nearest timestamp, whole or
    cropped to a pixel box or to an object's mask box (padded by `OBJECT_CROP_PAD_PX` unless
    `pad_px` is given), then downscaled to `max_side`.

    Cropping to an object with no frame chosen picks the object's first frame with a mask box.
    """
    run_id = request.run_id
    _run_or_refuse(workspace, run_id)
    at = request.WhichOneof("at")
    crop_kind = request.WhichOneof("crop")
    target = (
        _object_or_refuse(_objects_of(workspace, run_id), request.crop_object_id)
        if crop_kind == "crop_object_id"
        else None
    )
    if target is not None and at is None:
        frame_id = _first_frame_with_box(workspace, run_id, target)
    else:
        frame_id = _pick_frame(request, workspace.timeline(run_id), at).frame_id
    image = workspace.frame(run_id, frame_id)
    if image is None:
        raise ConnectError(Code.NOT_FOUND, f"run {run_id!r} has no frame {frame_id}")

    crop: BoxXYXY | None = None
    pad_px = request.pad_px if request.HasField("pad_px") else 0
    if crop_kind == "crop_box":
        box = request.crop_box
        crop = (box.x0, box.y0, box.x1, box.y1)
    elif target is not None:
        mask = workspace.object_box(run_id, target.object_id, frame_id)
        if mask is None:
            raise ConnectError(
                Code.NOT_FOUND, f"{target.object_id} has no mask box on frame {frame_id}"
            )
        crop = crop_box_for_object(
            mask.box_xyxy,
            measured_on=mask.measured_on,
            image_size=(image.width, image.height),
        )
        if not request.HasField("pad_px"):
            pad_px = OBJECT_CROP_PAD_PX
    try:
        encoded = frame_image(
            image.data,
            crop=crop,
            pad_px=pad_px,
            max_side=request.max_side if request.HasField("max_side") else None,
        )
    except ValueError as bad:
        raise ConnectError(Code.INVALID_ARGUMENT, str(bad)) from bad
    return pb.GetFrameResponse(
        frame_id=image.frame_id,
        t_ns=image.t_ns,
        width=encoded.width,
        height=encoded.height,
        source=_SOURCES[image.source],
        image=encoded.data,
        media_type=encoded.media_type,
    )


def object_summary_message(summary: ObjectSummary, *, moving: bool) -> pb.ObjectSummary:
    """`surmap.objects3d.ObjectSummary` as its proto twin.

    `Obb` becomes `OrientedBox` (rotation flattened row-major to 9 values), `ShapeClass` and
    `Relation` become the proto enums, and the `None`-able `confidence`, times and
    `geometry_uri` become `0` / `""`. `moving` is not part of the 3D summary, so it is given.
    """
    return pb.ObjectSummary(
        id=summary.id,
        label=summary.label,
        confidence=0.0 if summary.confidence is None else summary.confidence,
        frame=summary.frame,
        up_axis=summary.up_axis,
        units=summary.units,
        n_points=summary.n_points,
        n_faces=summary.n_faces,
        centroid=_vec3(summary.centroid),
        aabb_min=_vec3(summary.aabb_min),
        aabb_max=_vec3(summary.aabb_max),
        obb=pb.OrientedBox(
            centre=_vec3(summary.obb.centre),
            extents=_vec3(summary.obb.extents),
            rotation=[value for row in summary.obb.rotation for value in row],
        ),
        height_m=summary.height_m,
        footprint_m2=summary.footprint_m2,
        shape=_SHAPES[summary.shape],
        observed_frames=summary.observed_frames,
        t_first_ns=0 if summary.t_first_ns is None else summary.t_first_ns,
        t_last_ns=0 if summary.t_last_ns is None else summary.t_last_ns,
        neighbours=[
            pb.Neighbour(id=near.id, distance_m=near.distance_m, relation=_RELATIONS[near.relation])
            for near in summary.neighbours
        ],
        geometry_uri="" if summary.geometry_uri is None else summary.geometry_uri,
        moving=moving,
    )


def _run_or_refuse(workspace: SurveyWorkspace, run_id: str) -> RunInfo:
    run = workspace.run(run_id)
    if run is None:
        raise ConnectError(Code.NOT_FOUND, f"no run {run_id!r} in the history")
    return run


def _objects_of(workspace: SurveyWorkspace, run_id: str) -> Sequence[StoredObject]:
    _run_or_refuse(workspace, run_id)
    return workspace.objects(run_id)


def _object_or_refuse(objects: Sequence[StoredObject], object_id: str) -> StoredObject:
    found = next((obj for obj in objects if obj.object_id == object_id), None)
    if found is None:
        raise ConnectError(Code.NOT_FOUND, f"no object {object_id!r} in this run")
    return found


def _sam_budget(request: pb.PromptSamRequest) -> int:
    if not request.HasField("max_frames"):
        return MAX_SAM_FRAMES
    if request.max_frames < 1:
        raise ConnectError(Code.INVALID_ARGUMENT, "max_frames must be at least 1")
    return min(request.max_frames, MAX_SAM_FRAMES)


def _evenly_spaced(timeline: Sequence[FrameRecord], count: int) -> list[int]:
    """Up to `count` frame ids spread across the timeline, its first and last included."""
    if not timeline:
        return []
    count = min(count, len(timeline))
    if count == 1:
        return [timeline[0].frame_id]
    last = len(timeline) - 1
    positions = sorted({round(step * last / (count - 1)) for step in range(count)})
    return [timeline[position].frame_id for position in positions]


def _distance_to_box(point: NDArray[np.float64], points: NDArray[np.float32]) -> float:
    """Distance from `point` to the axis-aligned box around `points`; 0 inside it."""
    low = points.min(axis=0).astype(np.float64)
    high = points.max(axis=0).astype(np.float64)
    gaps = np.maximum(np.maximum(low - point, point - high), 0.0)
    return float(np.sqrt(np.sum(gaps * gaps)))


def _summarise(obj: StoredObject, *, geometry_uri: str | None = None) -> ObjectSummary:
    return summarize(
        obj.object_id,
        obj.label,
        obj.points,
        frame=OBJECT_FRAME,
        up_axis=OBJECT_UP_AXIS,
        confidence=obj.confidence,
        observed_frames=len(obj.frame_ids),
        t_first_ns=obj.t_first_ns,
        t_last_ns=obj.t_last_ns,
        geometry_uri=geometry_uri,
    )


def _first_frame_with_box(workspace: SurveyWorkspace, run_id: str, target: StoredObject) -> int:
    for frame_id in target.frame_ids:
        if workspace.object_box(run_id, target.object_id, frame_id) is not None:
            return frame_id
    raise ConnectError(Code.NOT_FOUND, f"{target.object_id} has no mask box on any frame")


def _pick_frame(
    request: pb.GetFrameRequest, timeline: Sequence[FrameRecord], at: str | None
) -> FrameRecord:
    """The frame `GetFrame` names by index, id or nearest timestamp; the run's first when none."""
    if not timeline:
        raise ConnectError(Code.NOT_FOUND, f"run {request.run_id!r} has no frames")
    if at == "frame_index":
        if request.frame_index >= len(timeline):
            raise ConnectError(
                Code.NOT_FOUND,
                f"frame index {request.frame_index} is past the run's {len(timeline)} frames",
            )
        return timeline[request.frame_index]
    if at == "frame_id":
        found = next((record for record in timeline if record.frame_id == request.frame_id), None)
        if found is None:
            raise ConnectError(
                Code.NOT_FOUND, f"run {request.run_id!r} has no frame {request.frame_id}"
            )
        return found
    if at == "t_ns":
        return min(timeline, key=lambda record: abs(record.t_ns - request.t_ns))
    return timeline[0]


def _vec3(values: tuple[float, float, float]) -> pb.Vec3:
    x, y, z = values
    return pb.Vec3(x=x, y=y, z=z)
