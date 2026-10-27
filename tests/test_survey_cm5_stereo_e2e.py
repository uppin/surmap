"""Real-data CM5 e2e: ten ETH3D stereo pairs through the real server.

Offline and hardware-free: frames are the committed fixture, the
server is the real socket server, pose is the in-memory backend, and
the scene points are the real stereo reconstruction.
"""

import asyncio
import json
import pathlib

from surmap.survey.cm5_main import build_description as build_cm5_description
from surmap.survey.stereo import StereoReconstructor
from surmap.survey.v1 import survey_pb2
from tests.test_survey_server_e2e import _connect_bidi, running_server

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "eth3d_cables2"


def _requests() -> list[survey_pb2.Cm5Request]:
    cal = json.loads((FIXTURE / "calibration.json").read_text(encoding="utf-8"))
    requests: list[survey_pb2.Cm5Request] = [
        survey_pb2.Cm5Request(
            config=survey_pb2.Cm5StreamConfig(
                calibration=survey_pb2.StereoCalibration(
                    calibration_id="eth3d-cables2",
                    focal_length_px=cal["fx"],
                    baseline_m=cal["baseline_m"],
                    cx=cal["cx"],
                    cy=cal["cy"],
                    width=cal["image_width"],
                    height=397,
                ),
                video_channels=[],
            )
        )
    ]
    for frame_info in cal["frames"]:
        index = int(frame_info["index"])
        for channel, side in ((0, "left"), (1, "right")):
            data = (FIXTURE / f"{side}_{index:03d}.jpg").read_bytes()
            requests.append(
                survey_pb2.Cm5Request(
                    frame=survey_pb2.RawVideoFrame(
                        frame_id=index + 1,
                        t_ns=(index + 1) * 1_000_000,
                        channel=channel,
                        width=640,
                        height=397 if channel == 0 else 400,
                        encoding=survey_pb2.FRAME_ENCODING_MJPEG,
                        data=data,
                    )
                )
            )
    return requests


async def test_ten_real_stereo_pairs_stream_detected_scene_points() -> None:
    # Given the real CM5 server, its reconstructor aligned for this rig
    cal = json.loads((FIXTURE / "calibration.json").read_text(encoding="utf-8"))
    stereo = StereoReconstructor(
        alignment_offset=(cal["right_cx"] - cal["cx"], cal["right_cy"] - cal["cy"])
    )
    async with running_server(build_cm5_description(stereo=stereo)) as address:
        # When the ten real pairs stream through over the wire
        payloads = await asyncio.to_thread(
            _connect_bidi,
            address,
            "/surmap.survey.v1.Cm5SurveyService/StreamSurvey",
            _requests(),
        )

    responses = [survey_pb2.Cm5Response.FromString(p) for p in payloads]
    batches = [r.points for r in responses if r.WhichOneof("kind") == "points"]

    # Then detections are there: scene batches for the real frames,
    # designated as RTAB-Map scene, with many points at sane depths
    assert batches, "no point batches streamed for real frames"
    assert all(batch.designation == 1 for batch in batches)
    by_frame = {batch.frame_id for batch in batches}
    assert len(by_frame) >= 8
    total_points = sum(len(batch.points) for batch in batches)
    assert total_points > 2_000
    assert all(0.05 < point.z < 20.0 for batch in batches for point in batch.points)
