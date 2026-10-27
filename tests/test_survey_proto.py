from typing import cast

from google.protobuf import descriptor_pool
from google.protobuf.descriptor import Descriptor
from google.protobuf.message_factory import GetMessageClass

from surmap.survey.v1 import survey_pb2


def test_both_survey_services_are_bidirectional_streams() -> None:
    # Given the generated bindings for surmap.survey.v1
    pool = descriptor_pool.Default()

    # Then both services exist and stream in both directions; the CM5
    # service carries the survey stream plus the separate detections
    # stream (detections are keyed by frame_id, never attached to
    # survey output frames)
    for name in ("surmap.survey.v1.Cm5SurveyService", "surmap.survey.v1.StationSamService"):
        service = pool.FindServiceByName(name)
        for method in service.methods:
            assert method.client_streaming
            assert method.server_streaming
    cm5 = pool.FindServiceByName("surmap.survey.v1.Cm5SurveyService")
    assert [method.name for method in cm5.methods] == ["StreamSurvey", "StreamDetections"]


def test_cm5_request_opens_with_config_then_carries_frames() -> None:
    # When a requester opens a CM5 stream
    request = survey_pb2.Cm5Request(
        config=survey_pb2.Cm5StreamConfig(
            calibration=survey_pb2.StereoCalibration(calibration_id="cal-1", baseline_m=0.12),
            video_channels=[0],
        )
    )

    # Then the oneof records the config, and a frame records its channel
    assert request.WhichOneof("kind") == "config"
    frame = survey_pb2.Cm5Request(
        frame=survey_pb2.RawVideoFrame(
            frame_id=42, channel=1, encoding=survey_pb2.FRAME_ENCODING_MJPEG
        )
    )
    assert frame.frame.frame_id == 42
    assert frame.frame.channel == 1


def test_a_point_batch_round_trips_with_its_designation() -> None:
    # Given newly spawned RTAB-Map points for one frame
    batch = survey_pb2.PointBatch(
        designation=1,
        frame_id=42,
        t_ns=1_000_000,
        points=[survey_pb2.Point3(x=1.0, y=2.0, z=3.0)],
    )

    # When the batch crosses the wire
    parsed = cast(survey_pb2.PointBatch, GetMessageClass(cast(Descriptor, batch.DESCRIPTOR))())
    parsed.ParseFromString(batch.SerializeToString())

    # Then the designation and points survive intact
    assert parsed.designation == 1
    assert [(p.x, p.y, p.z) for p in parsed.points] == [(1.0, 2.0, 3.0)]


def test_station_detections_are_keyed_by_the_assigned_frame_id() -> None:
    # Given SAM detections for frame 42, one tied to on-board track 7
    detections = survey_pb2.SamFrameDetections(
        frame_id=42,
        detections=[
            survey_pb2.SamDetection(
                label="car",
                score=0.9,
                box=survey_pb2.Box(x_min=0.0, y_min=0.0, x_max=10.0, y_max=10.0),
                mask_polygon=[survey_pb2.Point2(x=1.0, y=1.0)],
                track_id=7,
            )
        ],
    )

    # Then the vector repeats the frame id and keeps the polygon and track
    (detection,) = detections.detections
    assert detections.frame_id == 42
    assert detection.label == "car"
    assert detection.track_id == 7
    assert [(p.x, p.y) for p in detection.mask_polygon] == [(1.0, 1.0)]


def test_cm5_detections_are_keyed_by_frame_id_with_tracks() -> None:
    message = survey_pb2.FrameDetections(
        frame_id=9,
        t_ns=123,
        detections=[
            survey_pb2.ObjectDetection(
                label="chair",
                score=0.5,
                box=survey_pb2.Box(x_min=1.0, y_min=2.0, x_max=30.0, y_max=40.0),
                track_id=4,
            )
        ],
    )
    (detection,) = message.detections
    assert message.frame_id == 9
    assert detection.track_id == 4
    assert detection.box.x_max == 30.0


def test_analysis_modes_cover_every_frame_and_best_effort_drop() -> None:
    assert survey_pb2.ANALYSIS_MODE_EVERY_FRAME == 1
    assert survey_pb2.ANALYSIS_MODE_BEST_EFFORT_DROP == 2
