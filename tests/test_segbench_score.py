"""Frame scores, survivor recall at 3 m, and the price of a route."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from surmap.segbench.dataset import (
    BenchFrame,
    BenchIntrinsics,
    load_bench,
    select_dev_set,
    select_keyframes,
    write_label_image,
)
from surmap.segbench.fusion import BenchLandmark
from surmap.segbench.masks import rasterize_polygon
from surmap.segbench.routes import RouteObservation
from surmap.segbench.score import PriceRow, SurvivorTruth, percentile, score_bench
from surmap.survey.sam import SamDetection
from surmap.types import Pose, Vec3

_POLYGON = ((0.0, 0.0), (8.0, 0.0), (8.0, 8.0), (0.0, 8.0))


def test_percentile_is_the_linear_rank_of_the_sorted_latencies() -> None:
    # Given five latencies
    latencies = (1.0, 2.0, 3.0, 4.0, 100.0)

    # When the median and the 95th percentile are taken
    median = percentile(latencies, 0.5)
    high = percentile(latencies, 0.95)

    # Then the median is the middle value and p95 interpolates toward the tail
    assert median == 3.0
    assert high == pytest.approx(80.8)


def test_a_perfect_mask_and_a_close_survivor_score_recall_without_a_false_positive_on_the_match(
    tmp_path: Path,
) -> None:
    # Given two frames whose masks match the recorded polygons, and two person landmarks
    bench = _write_bench(tmp_path)
    dataset = load_bench(bench)
    observations = (
        _observation(1, 0, latency_s=0.1, tokens_in=1000, tokens_out=500, gpu_seconds=2.0),
        _observation(2, 1_000_000_000, latency_s=0.3),
    )
    landmarks = (
        BenchLandmark(
            landmark_id="lm-1",
            centroid=Vec3(0.0, 0.0, 2.0),
            map_frame="gazebo_enu",
            frame_ids=(1,),
            mask_ids=("1-0",),
            track_ids=(),
            label="person",
            description="",
            confidence=0.7,
            provider="",
            model_id="",
            prompt_version="unlabelled",
            first_seen_ns=2_000_000_000,
            last_seen_ns=2_000_000_000,
            observation_count=1,
        ),
        BenchLandmark(
            landmark_id="lm-2",
            centroid=Vec3(9.0, 0.0, 0.0),
            map_frame="gazebo_enu",
            frame_ids=(2,),
            mask_ids=("2-0",),
            track_ids=(),
            label="person",
            description="",
            confidence=0.4,
            provider="",
            model_id="",
            prompt_version="unlabelled",
            first_seen_ns=3_000_000_000,
            last_seen_ns=3_000_000_000,
            observation_count=1,
        ),
    )
    people = (SurvivorTruth("survivor_a", Vec3(0.0, 0.0, 2.0)),)
    prices = {"replay": PriceRow(2.0, 4.0, 0.5)}

    # When the bench is scored from those files
    report = score_bench(
        dataset,
        observations,
        landmarks,
        people,
        prices,
        route="replay",
        mission_start_ns=0,
    )

    # Then the masks match, one survivor is found, the other landmark is a false positive
    assert report.scoring.map_frame == "gazebo_enu"
    assert report.scoring.clock == "sim_time"
    assert report.scoring.pixel_space == "rectified"
    assert report.mean_iou == 1.0
    assert report.mean_boundary_f1 == 1.0
    assert report.mean_pixel_precision == 1.0
    assert report.mean_pixel_recall == 1.0
    assert report.survivor_instance_recall == 1.0
    assert report.false_positives_per_frame == 0.0
    assert report.found == 1
    assert report.total == 1
    assert report.mean_position_error_m == 0.0
    assert report.false_positive_landmarks == 1
    assert report.time_to_first_detection_s == 2.0
    assert report.latency_p50_s == pytest.approx(0.2)
    assert report.latency_p95_s == pytest.approx(0.29)
    assert report.cost_usd == pytest.approx(1.004)
    assert report.cost_per_frame_usd == pytest.approx(0.502)


def test_keyframes_keep_one_frame_per_second_and_the_dev_set_asks_for_hard_negatives() -> None:
    # Given frames a fifth of a second apart, three with a person and two with only clutter
    frames = (
        _flagged(1, 0, survivor=True, clutter=False),
        _flagged(2, 200_000_000, survivor=True, clutter=False),
        _flagged(3, 1_000_000_000, survivor=False, clutter=True),
        _flagged(4, 1_200_000_000, survivor=True, clutter=False),
        _flagged(5, 2_000_000_000, survivor=False, clutter=True),
    )

    # When keyframes are taken at 1 Hz and a tiny dev set is selected
    kept = select_keyframes(frames, hz=1.0)
    dev = select_dev_set(frames, survivor_count=2, negative_count=1)

    # Then the in-between frame is dropped, and the dev set is two survivors plus one hard negative
    assert [frame.frame_id for frame in kept] == [1, 3, 5]
    assert [frame.frame_id for frame in dev] == [1, 2, 3]


def _write_bench(root: Path) -> Path:
    bench = root / "bench"
    (bench / "images").mkdir(parents=True)
    (bench / "masks").mkdir()
    mask = rasterize_polygon(_POLYGON, 8, 8)
    labels = np.asarray(np.where(mask, 1, 0), dtype=np.int32)
    for frame_id in (1, 2):
        Image.new("RGB", (8, 8), (30, 30, 30)).save(bench / "images" / f"{frame_id}.png")
        write_label_image(bench / "masks" / f"{frame_id}_instance.png", labels)
        write_label_image(bench / "masks" / f"{frame_id}_class.png", labels)
    header = {
        "scoring": {
            "map_frame": "gazebo_enu",
            "pixel_space": "rectified",
            "clock": "sim_time",
            "match_radius_m": 3.0,
        },
        "intrinsics": {
            "width": 8,
            "height": 8,
            "fx": 10.0,
            "fy": 10.0,
            "cx": 4.0,
            "cy": 4.0,
            "baseline_m": 0.1,
        },
    }
    (bench / "bench.json").write_text(json.dumps(header), encoding="utf-8")
    (bench / "classes.json").write_text(json.dumps({"1": "person"}), encoding="utf-8")
    rows = []
    for frame_id, t_ns in ((1, 0), (2, 1_000_000_000)):
        rows.append(
            {
                "frame_id": frame_id,
                "t_ns": t_ns,
                "clock": "sim_time",
                "pixel_space": "rectified",
                "left_ref": f"images/{frame_id}.png",
                "instance_mask": f"masks/{frame_id}_instance.png",
                "class_mask": f"masks/{frame_id}_class.png",
                "pose": {
                    "position_m": {"x": 0.0, "y": 0.0, "z": 0.0},
                    "orientation_xyzw": [0.0, 0.0, 0.0, 1.0],
                    "frame": "gazebo_enu",
                },
            }
        )
    (bench / "frames.jsonl").write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )
    return bench


def _observation(
    frame_id: int,
    t_ns: int,
    *,
    latency_s: float,
    tokens_in: int = 0,
    tokens_out: int = 0,
    gpu_seconds: float = 0.0,
) -> RouteObservation:
    return RouteObservation(
        frame_id=frame_id,
        t_ns=t_ns,
        source="replay",
        model_id="recorded",
        latency_s=latency_s,
        input_tokens=tokens_in,
        output_tokens=tokens_out,
        gpu_seconds=gpu_seconds,
        detections=(SamDetection("person", 0.9, (0.0, 0.0, 8.0, 8.0), _POLYGON, None),),
        mask_ids=(f"{frame_id}-0",),
    )


def _flagged(frame_id: int, t_ns: int, *, survivor: bool, clutter: bool) -> BenchFrame:
    return BenchFrame(
        frame_id=frame_id,
        t_ns=t_ns,
        image_path=Path("image.png"),
        instance_mask_path=Path("instance.png"),
        class_mask_path=Path("class.png"),
        cloud_path=None,
        pose=Pose(Vec3(0.0, 0.0, 0.0)),
        pose_frame="gazebo_enu",
        clock="sim_time",
        pixel_space="rectified",
        has_survivor=survivor,
        has_clutter=clutter,
        intrinsics=BenchIntrinsics(8, 8, 1.0, 1.0, 4.0, 4.0, 0.1),
    )
