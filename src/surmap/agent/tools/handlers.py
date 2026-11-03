"""The `surmap.agent.v1.SurveyTools` handlers: proto request in, proto response out.

One async function per rpc, each taking its decoded request and a `SurveyWorkspace`, so they
test with no model and no server. `survey_tool_handlers(workspace)` binds them by rpc name in
connect-python's `(request, ctx)` shape, ready for `surmap.agent.services.survey_tools_module`.

Failures are `ConnectError`s: `NOT_FOUND` for a run, scene, frame or object the workspace does
not have, `INVALID_ARGUMENT` for a request that contradicts itself (`near` without `radius_m`).
Object coordinates are in the run's map frame (`frame="map"`, up axis `-y`).
"""

from __future__ import annotations

from collections.abc import Mapping

from surmap.agent.proto import survey_tools_pb2 as pb
from surmap.agent.services import Handler
from surmap.agent.tools.workspace import SurveyWorkspace
from surmap.objects3d import ObjectSummary

__all__ = [
    "MAX_SAM_FRAMES",
    "OBJECT_CROP_PAD_PX",
    "find_objects",
    "get_frame",
    "get_object",
    "get_object_geometry",
    "get_run",
    "list_demos",
    "object_summary_message",
    "prompt_sam",
    "run_demo",
    "survey_tool_handlers",
]

MAX_SAM_FRAMES = 8
"""The most frames one `prompt_sam` call segments."""

OBJECT_CROP_PAD_PX = 16
"""Padding around an object's mask box when `get_frame` crops to an object without `pad_px`."""


def survey_tool_handlers(workspace: SurveyWorkspace) -> Mapping[str, Handler]:
    """Every `SurveyTools` rpc, by rpc name, as a `(request, ctx)` handler over `workspace`."""
    raise NotImplementedError  # TODO(pr-7): implement


async def list_demos(
    request: pb.ListDemosRequest, workspace: SurveyWorkspace
) -> pb.ListDemosResponse:
    """`ListDemos`: every scene, its default prompt, whether it is prepared, its cached run."""
    raise NotImplementedError  # TODO(pr-7): implement


async def run_demo(request: pb.RunDemoRequest, workspace: SurveyWorkspace) -> pb.RunDemoResponse:
    """`RunDemo`: run a scene headlessly and answer when it ends; cancelling stops the run."""
    raise NotImplementedError  # TODO(pr-7): implement


async def get_run(request: pb.GetRunRequest, workspace: SurveyWorkspace) -> pb.GetRunResponse:
    """`GetRun`: one recorded run's scene, prompt, frame and object counts and status."""
    raise NotImplementedError  # TODO(pr-7): implement


async def prompt_sam(
    request: pb.PromptSamRequest, workspace: SurveyWorkspace
) -> pb.PromptSamResponse:
    """`PromptSam`: SAM on chosen frames of a recorded run, or on up to `MAX_SAM_FRAMES`
    evenly spaced ones (first and last included) when none are chosen."""
    raise NotImplementedError  # TODO(pr-7): implement


async def find_objects(
    request: pb.FindObjectsRequest, workspace: SurveyWorkspace
) -> pb.FindObjectsResponse:
    """`FindObjects`: the run's object summaries matching label, `near`/`radius_m` and `moving`.

    With `near`, nearest first by the distance from the point to each object's axis-aligned
    box; otherwise largest (most points) first. `limit` caps the count.
    """
    raise NotImplementedError  # TODO(pr-7): implement


async def get_object(
    request: pb.GetObjectRequest, workspace: SurveyWorkspace
) -> pb.GetObjectResponse:
    """`GetObject`: one object's summary with its nearest neighbours filled in."""
    raise NotImplementedError  # TODO(pr-7): implement


async def get_object_geometry(
    request: pb.GetObjectGeometryRequest, workspace: SurveyWorkspace
) -> pb.GetObjectGeometryResponse:
    """`GetObjectGeometry`: `surmap-obj v1` text within `max_points` / `voxel_m`, and the
    object's GLB URI."""
    raise NotImplementedError  # TODO(pr-7): implement


async def get_frame(request: pb.GetFrameRequest, workspace: SurveyWorkspace) -> pb.GetFrameResponse:
    """`GetFrame`: one frame as a JPEG, picked by index, id or nearest timestamp, whole or
    cropped to a pixel box or to an object's mask box (padded by `OBJECT_CROP_PAD_PX` unless
    `pad_px` is given), then downscaled to `max_side`.

    Cropping to an object with no frame chosen picks the object's first frame with a mask box.
    """
    raise NotImplementedError  # TODO(pr-7): implement


def object_summary_message(summary: ObjectSummary, *, moving: bool) -> pb.ObjectSummary:
    """`surmap.objects3d.ObjectSummary` as its proto twin.

    `Obb` becomes `OrientedBox` (rotation flattened row-major to 9 values), `ShapeClass` and
    `Relation` become the proto enums, and the `None`-able `confidence`, times and
    `geometry_uri` become `0` / `""`. `moving` is not part of the 3D summary, so it is given.
    """
    raise NotImplementedError  # TODO(pr-7): implement
