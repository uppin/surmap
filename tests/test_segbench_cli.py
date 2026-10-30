"""CLI smoke: a synthetic bench renders a report, and live routes stay gated."""

from __future__ import annotations

import asyncio
import io
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from surmap.segbench.cli import main
from surmap.segbench.dataset import write_label_image
from surmap.segbench.masks import rasterize_polygon
from surmap.segbench.routes import (
    LiveRouteRefused,
    RouteObservation,
    UsageCapture,
    meta_route,
    write_detections_jsonl,
)
from surmap.survey.sam import RawFrame, SamDetection
from surmap.usage import BudgetExceeded, UsageLedger

_POLYGON = ((0.0, 0.0), (8.0, 0.0), (8.0, 8.0), (0.0, 8.0))


def test_the_offline_commands_render_a_comparison_from_a_synthetic_bench(
    tmp_path: Path,
) -> None:
    # Given a one-frame bench, a recorded person detection, and a person at that point
    bench = _write_bench(tmp_path / "bench")
    detections = tmp_path / "detections.jsonl"
    write_detections_jsonl(detections, (_observation(),))
    people = tmp_path / "people.json"
    people.write_text(
        json.dumps([{"id": "survivor_a", "x": 0.0, "y": 0.0, "z": 2.0}]),
        encoding="utf-8",
    )
    prices = tmp_path / "prices.json"
    prices.write_text(
        json.dumps(
            {
                "replay": {
                    "usd_per_million_input_tokens": 2.0,
                    "usd_per_million_output_tokens": 4.0,
                    "usd_per_gpu_second": 0.0,
                }
            }
        ),
        encoding="utf-8",
    )
    landmarks = tmp_path / "landmarks.json"
    report_a = tmp_path / "a.json"
    report_b = tmp_path / "b.json"
    comparison = tmp_path / "compare.md"

    # When fuse, score, and compare run offline
    fuse_code = main(
        ["fuse", "--bench", str(bench), "--detections", str(detections), "--out", str(landmarks)]
    )
    score_a = main(
        [
            "score",
            "--bench",
            str(bench),
            "--detections",
            str(detections),
            "--landmarks",
            str(landmarks),
            "--route",
            "replay",
            "--people",
            str(people),
            "--prices",
            str(prices),
            "--out",
            str(report_a),
            "--markdown",
            str(tmp_path / "a.md"),
        ]
    )
    score_b = main(
        [
            "score",
            "--bench",
            str(bench),
            "--detections",
            str(detections),
            "--landmarks",
            str(landmarks),
            "--route",
            "station-onnx",
            "--people",
            str(people),
            "--out",
            str(report_b),
        ]
    )
    compare_code = main(
        ["compare", "--reports", str(report_a), str(report_b), "--out", str(comparison)]
    )
    replay_code = main(
        [
            "run",
            "--route",
            "replay",
            "--detections",
            str(detections),
            "--out",
            str(tmp_path / "replay.jsonl"),
            "--usage",
            str(tmp_path / "usage.jsonl"),
        ]
    )

    # Then the report names the scoring frame and the comparison table lists both routes
    markdown = (tmp_path / "a.md").read_text(encoding="utf-8")
    table = comparison.read_text(encoding="utf-8")
    body = json.loads(report_a.read_text(encoding="utf-8"))
    assert fuse_code == 0
    assert score_a == 0
    assert score_b == 0
    assert compare_code == 0
    assert replay_code == 0
    assert "gazebo_enu" in markdown
    assert "sim_time" in markdown
    assert "rectified" in markdown
    assert body["found"] == 1
    assert "| route |" in table
    assert "replay" in table
    assert "station-onnx" in table
    assert (tmp_path / "usage.jsonl").is_file()


def test_meta_and_label_runs_refuse_without_their_live_flags(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given no live flags
    monkeypatch.delenv("SURMAP_LIVE_META", raising=False)
    monkeypatch.delenv("SURMAP_LIVE_BASETEN", raising=False)

    # When a Meta segmentation and a Muse label are requested
    meta_code = main(
        [
            "run",
            "--route",
            "meta",
            "--bench",
            str(tmp_path),
            "--out",
            str(tmp_path / "out.jsonl"),
            "--usage",
            str(tmp_path / "usage.jsonl"),
        ]
    )
    label_code = main(
        [
            "label",
            "--bench",
            str(tmp_path),
            "--landmarks",
            str(tmp_path / "landmarks.json"),
            "--out",
            str(tmp_path / "labelled.json"),
        ]
    )

    # Then both refuse before any request, and no output file is written
    assert meta_code == 2
    assert label_code == 2
    assert not (tmp_path / "out.jsonl").exists()
    assert not (tmp_path / "labelled.json").exists()


def test_station_route_requires_a_local_model_path(tmp_path: Path) -> None:
    # Given a station route with no ONNX path
    # When run is asked to start
    code = main(
        [
            "run",
            "--route",
            "station-onnx",
            "--bench",
            str(tmp_path),
            "--out",
            str(tmp_path / "out.jsonl"),
            "--usage",
            str(tmp_path / "usage.jsonl"),
        ]
    )

    # Then it refuses before loading a bench or a model
    assert code == 2


def test_meta_route_sends_raw_rgb_records_latency_and_honours_the_call_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given a PNG frame and a detector that only records what it was handed
    monkeypatch.setenv("SURMAP_LIVE_META", "1")
    seen: list[RawFrame] = []
    usage = UsageCapture()

    class _Recording:
        async def detect(self, frame: RawFrame) -> tuple[SamDetection, ...]:
            seen.append(frame)
            usage("meta", "sam-3.1", 10, 4, None)
            return (SamDetection("person", 0.8, (0.0, 0.0, 2.0, 2.0), _POLYGON, None),)

    ticks = iter((10.0, 10.25))
    route = meta_route(_Recording(), usage=usage, clock=lambda: next(ticks))
    image = Image.new("RGB", (4, 2), (9, 8, 7))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    frame = RawFrame(7, 100, 0, 4, 2, "png", buffer.getvalue())

    # When the route observes that frame
    observation = asyncio.run(route.observe(frame))

    # Then Meta receives raw RGB, the call is timed, and the tokens are counted
    assert len(seen) == 1
    assert seen[0].encoding == "raw_rgb"
    assert len(seen[0].data) == 4 * 2 * 3
    assert observation.latency_s == pytest.approx(0.25)
    assert observation.input_tokens == 10
    assert observation.output_tokens == 4

    # Given a spent call budget
    monkeypatch.setenv("SURMAP_BUDGET_META_CALLS", "0")
    ledger = UsageLedger(tmp_path / "usage.jsonl")
    blocked = meta_route(_Recording(), ledger=ledger, usage=UsageCapture(ledger))

    # When another frame is observed
    # Then the budget refuses it before the detector runs
    with pytest.raises(BudgetExceeded):
        asyncio.run(blocked.observe(frame))
    assert len(seen) == 1


def test_meta_route_refuses_before_the_detector_when_the_flag_is_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given the Meta flag is unset
    monkeypatch.delenv("SURMAP_LIVE_META", raising=False)
    seen: list[int] = []

    class _Recording:
        async def detect(self, frame: RawFrame) -> tuple[SamDetection, ...]:
            seen.append(frame.frame_id)
            return ()

    route = meta_route(_Recording())
    frame = RawFrame(1, 1, 0, 1, 1, "raw_rgb", bytes((1, 2, 3)))

    # When the route is asked to observe
    with pytest.raises(LiveRouteRefused, match="SURMAP_LIVE_META"):
        asyncio.run(route.observe(frame))

    # Then the detector was not called
    assert seen == []


def _write_bench(bench: Path) -> Path:
    (bench / "images").mkdir(parents=True)
    (bench / "masks").mkdir()
    (bench / "clouds").mkdir()
    mask = rasterize_polygon(_POLYGON, 8, 8)
    labels = np.asarray(np.where(mask, 1, 0), dtype=np.int32)
    Image.new("RGB", (8, 8), (40, 20, 10)).save(bench / "images" / "0000.png")
    write_label_image(bench / "masks" / "0000_instance.png", labels)
    write_label_image(bench / "masks" / "0000_class.png", labels)
    (bench / "clouds" / "0000.json").write_text(
        json.dumps({"space": "camera", "points": [[0.0, 0.0, 2.0]]}),
        encoding="utf-8",
    )
    (bench / "bench.json").write_text(
        json.dumps(
            {
                "intrinsics": {
                    "width": 8,
                    "height": 8,
                    "fx": 10.0,
                    "fy": 10.0,
                    "cx": 4.0,
                    "cy": 4.0,
                    "baseline_m": 0.1,
                }
            }
        ),
        encoding="utf-8",
    )
    (bench / "classes.json").write_text(json.dumps({"1": "person"}), encoding="utf-8")
    (bench / "frames.jsonl").write_text(
        json.dumps(
            {
                "frame_id": 1,
                "t_ns": 2_000_000_000,
                "left_ref": "images/0000.png",
                "instance_mask": "masks/0000_instance.png",
                "class_mask": "masks/0000_class.png",
                "cloud": "clouds/0000.json",
                "pose": {
                    "position_m": {"x": 0.0, "y": 0.0, "z": 0.0},
                    "orientation_xyzw": [0, 0, 0, 1],
                    "frame": "gazebo_enu",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return bench


def _observation() -> RouteObservation:
    return RouteObservation(
        frame_id=1,
        t_ns=2_000_000_000,
        source="replay",
        model_id="recorded",
        latency_s=0.2,
        input_tokens=1000,
        output_tokens=500,
        gpu_seconds=0.0,
        detections=(SamDetection("person", 0.9, (0.0, 0.0, 8.0, 8.0), _POLYGON, None),),
        mask_ids=("1-0",),
    )
