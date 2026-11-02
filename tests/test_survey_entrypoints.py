from collections.abc import AsyncIterable
from typing import cast

import pytest
from connectrpc.errors import ConnectError

from surmap.rpc.description import ServerDescription
from surmap.rpc.hosts.in_memory import InMemoryHost
from surmap.survey.cm5_main import build_description as build_cm5_description
from surmap.survey.cm5_main import build_parser as build_cm5_parser
from surmap.survey.station_main import build_description as build_station_description
from surmap.survey.v1 import survey_pb2


def test_the_cm5_entrypoint_serves_the_survey_service_and_health() -> None:
    # When the CM5 process builds its server description
    description = build_cm5_description()

    # Then it mounts the survey service and a health route
    assert isinstance(description, ServerDescription)
    assert [m.descriptor.full_name for m in description.services] == [
        "surmap.survey.v1.Cm5SurveyService"
    ]
    assert [(r.method, r.path) for r in description.http_routes] == [("GET", "/health/is_alive")]


def test_the_cm5_process_keeps_every_optional_computation_off_by_default() -> None:
    # When the CM5 process parses a bare command line
    args = build_cm5_parser().parse_args([])

    # Then only RTAB-Map and the Coral detector can be switched on:
    # every other computation stays off until its flag enables it
    assert args.object_tracking is False
    assert args.moving_areas is False
    assert args.region_points is False


def test_the_cm5_process_can_enable_each_optional_computation_by_flag() -> None:
    # When each optional computation is enabled on the command line
    args = build_cm5_parser().parse_args(["--object-tracking", "--moving-areas", "--region-points"])

    # Then exactly those computations are on
    assert args.object_tracking is True
    assert args.moving_areas is True
    assert args.region_points is True


async def _one_config() -> AsyncIterable[survey_pb2.Cm5Request]:
    yield survey_pb2.Cm5Request(config=survey_pb2.Cm5StreamConfig())


async def test_the_moving_areas_stream_is_rejected_when_not_enabled() -> None:
    # Given a CM5 server description built without moving areas
    host = InMemoryHost(build_cm5_description(moving_areas=False), None)
    client = host.client(survey_pb2.DESCRIPTOR.services_by_name["Cm5SurveyService"])

    # When a requester opens the moving-areas stream
    # Then it is refused by name, like a stream with no source configured
    with pytest.raises(ConnectError, match="moving areas are not enabled"):
        [
            cast("survey_pb2.MovingAreasResponse", message)
            async for message in client.bidi("StreamMovingAreas", _one_config())
        ]


def test_the_station_process_selects_sam31_torch_by_flag() -> None:
    from surmap.survey.station_main import build_parser as build_station_parser

    # When the station process parses its command line
    defaults = build_station_parser().parse_args([])
    torch_args = build_station_parser().parse_args(
        ["--detector", "sam31-torch", "--sam31-model", "/models/sam3.1", "--sam31-device", "cuda:0"]
    )

    # Then PyTorch SAM 3.1 is an explicit opt-in on the named GPU
    assert defaults.detector == "memory"
    assert torch_args.detector == "sam31-torch"
    assert torch_args.sam31_device == "cuda:0"
    assert str(torch_args.sam31_model) == "/models/sam3.1"


async def test_the_cm5_server_reports_the_capabilities_it_was_built_with() -> None:
    # Given a CM5 description with a detector, object tracking and
    # moving areas enabled (the defaults describe the bare server)
    host = InMemoryHost(build_cm5_description(), None)
    client = host.client(survey_pb2.DESCRIPTOR.services_by_name["Cm5SurveyService"])

    # When a client asks what this server can do
    reply = await client.unary("GetCapabilities", survey_pb2.CapabilitiesRequest())
    capabilities = survey_pb2.Capabilities.FromString(reply.SerializeToString())

    # Then it answers for the bare build: no detector, no object
    # points, no region points, in-memory SLAM
    assert capabilities.service == "cm5"
    assert capabilities.detections is False
    assert capabilities.object_points is False
    assert capabilities.region_points is False
    assert capabilities.slam == "inmemory"


async def test_the_station_server_reports_its_sam_capabilities() -> None:
    from surmap.survey.station_main import build_description as build_station_description

    # Given a station description with the default in-memory detector
    host = InMemoryHost(build_station_description(), None)
    client = host.client(survey_pb2.DESCRIPTOR.services_by_name["StationSamService"])

    # When a client asks what this server can do
    reply = await client.unary("GetCapabilities", survey_pb2.CapabilitiesRequest())
    capabilities = survey_pb2.Capabilities.FromString(reply.SerializeToString())

    # Then it reports no real SAM analysis, on CPU
    assert capabilities.service == "station"
    assert capabilities.sam_analysis is False
    assert capabilities.provider == "InMemorySamDetector"
    assert capabilities.device == "cpu"


def test_the_station_entrypoint_serves_the_sam_service_and_health() -> None:
    description = build_station_description()
    assert [m.descriptor.full_name for m in description.services] == [
        "surmap.survey.v1.StationSamService"
    ]
    assert [(r.method, r.path) for r in description.http_routes] == [("GET", "/health/is_alive")]
