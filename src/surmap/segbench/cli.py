"""Command line for the offline segmentation benchmark.

`run` and `label` are the only commands that can call a hosted model, and
both refuse unless the matching ``SURMAP_LIVE_*`` flag is set. `fuse`,
`score`, and `compare` read files only.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from surmap.labelling.baseten_muse import LabelClient, ObjectLabel
from surmap.segbench.dataset import BenchDataset, BenchFrame, FrameCloud, load_bench, load_cloud
from surmap.segbench.fusion import (
    BenchLandmark,
    FusionFrame,
    MaskEvidence,
    fuse,
    label_landmarks,
)
from surmap.segbench.report import load_report, render_comparison, write_json, write_markdown
from surmap.segbench.routes import (
    BenchRoute,
    LiveRouteRefused,
    RouteObservation,
    UsageCapture,
    meta_route,
    modal_route,
    read_detections_jsonl,
    require_live,
    station_route,
    write_detections_jsonl,
)
from surmap.segbench.score import (
    load_people,
    load_prices,
    people_from_disaster,
    score_bench,
)
from surmap.simulation.disaster_world import load_disaster_ground_truth
from surmap.survey.sam import RawFrame
from surmap.survey.stereo import StereoRig
from surmap.types import Vec3
from surmap.usage import BudgetExceeded, UsageLedger

LABEL_FLAGS = {
    "baseten": "SURMAP_LIVE_BASETEN",
    "meta": "SURMAP_LIVE_META",
    "modal": "SURMAP_LIVE_MODAL",
}


def main(argv: Sequence[str] | None = None) -> int:
    """Run one subcommand. Returns 0 on success and 2 on a refused or bad request."""
    parser = argparse.ArgumentParser(prog="seg_bench", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="segment a bench, or replay a JSONL")
    run.add_argument("--route", required=True, choices=("meta", "modal", "station-onnx", "replay"))
    run.add_argument("--bench", type=Path)
    run.add_argument("--detections", type=Path, help="replay JSONL, or ignored by live routes")
    run.add_argument("--out", type=Path, required=True)
    run.add_argument("--usage", type=Path, required=True)
    run.add_argument("--model", help="ONNX path for station-onnx")

    fuse_cmd = sub.add_parser("fuse", help="fuse recorded detections into landmarks")
    fuse_cmd.add_argument("--bench", type=Path, required=True)
    fuse_cmd.add_argument("--detections", type=Path, required=True)
    fuse_cmd.add_argument("--out", type=Path, required=True)

    label = sub.add_parser("label", help="Muse once per landmark (live-gated)")
    label.add_argument("--bench", type=Path, required=True)
    label.add_argument("--landmarks", type=Path, required=True)
    label.add_argument("--out", type=Path, required=True)
    label.add_argument("--provider", default="baseten", choices=tuple(LABEL_FLAGS))

    score = sub.add_parser("score", help="score detections and landmarks offline")
    score.add_argument("--bench", type=Path, required=True)
    score.add_argument("--detections", type=Path, required=True)
    score.add_argument("--landmarks", type=Path, required=True)
    score.add_argument("--route", required=True)
    score.add_argument("--out", type=Path, required=True)
    score.add_argument("--markdown", type=Path)
    score.add_argument("--prices", type=Path)
    score.add_argument("--people", type=Path)

    compare = sub.add_parser("compare", help="markdown table of report JSON files")
    compare.add_argument("--reports", type=Path, nargs="+", required=True)
    compare.add_argument("--out", type=Path, required=True)

    args = parser.parse_args(list(argv) if argv is not None else None)
    command = args.command
    if not isinstance(command, str):
        print("missing command", file=sys.stderr)
        return 2
    try:
        if command == "run":
            return _run(args)
        if command == "fuse":
            return _fuse(args)
        if command == "label":
            return _label(args)
        if command == "score":
            return _score(args)
        if command == "compare":
            return _compare(args)
    except (LiveRouteRefused, BudgetExceeded, ValueError, FileNotFoundError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(f"unknown command {command}", file=sys.stderr)
    return 2


def _run(args: argparse.Namespace) -> int:
    route = _text(args.route, "route")
    out = _path(args.out, "out")
    usage_path = _path(args.usage, "usage")
    if route == "replay":
        detections = _path(args.detections, "detections")
        recorded = read_detections_jsonl(detections)
        write_detections_jsonl(out, recorded)
        usage_path.parent.mkdir(parents=True, exist_ok=True)
        usage_path.write_text("", encoding="utf-8")
        return 0
    require_live(route)
    if route == "station-onnx" and not isinstance(args.model, str):
        raise ValueError("station-onnx requires --model")
    bench = load_bench(_path(args.bench, "bench"))
    ledger = UsageLedger(usage_path)
    usage = UsageCapture(ledger)
    wrapped = _live_route(route, ledger, usage, args.model)
    observations: list[RouteObservation] = []
    for frame in bench.frames:
        observations.append(asyncio.run(wrapped.observe(_raw_frame(frame))))
    write_detections_jsonl(out, observations)
    return 0


def _fuse(args: argparse.Namespace) -> int:
    dataset = load_bench(_path(args.bench, "bench"))
    observations = read_detections_jsonl(_path(args.detections, "detections"))
    landmarks = fuse_dataset(dataset, observations)
    _write_landmarks(_path(args.out, "out"), landmarks)
    return 0


def _label(args: argparse.Namespace) -> int:
    provider = _text(args.provider, "provider")
    flag = LABEL_FLAGS[provider]
    if os.environ.get(flag) != "1":
        raise LiveRouteRefused(f"Refusing to label. Set {flag}=1. No request was sent.")
    dataset = load_bench(_path(args.bench, "bench"))
    landmarks = load_landmarks(_path(args.landmarks, "landmarks"))
    images = {frame.frame_id: frame.image_path.read_bytes() for frame in dataset.frames}
    labeller = _labeller(provider)
    labelled = label_landmarks(landmarks, images, labeller, provider=provider)
    _write_landmarks(_path(args.out, "out"), labelled)
    return 0


def _score(args: argparse.Namespace) -> int:
    dataset = load_bench(_path(args.bench, "bench"))
    observations = read_detections_jsonl(_path(args.detections, "detections"))
    landmarks = load_landmarks(_path(args.landmarks, "landmarks"))
    if args.people is None:
        people = people_from_disaster(load_disaster_ground_truth())
    else:
        people = load_people(_path(args.people, "people"))
    prices_path = args.prices if isinstance(args.prices, Path) else None
    report = score_bench(
        dataset,
        observations,
        landmarks,
        people,
        load_prices(prices_path),
        route=_text(args.route, "route"),
    )
    out = _path(args.out, "out")
    write_json(report, out)
    markdown = args.markdown if isinstance(args.markdown, Path) else out.with_suffix(".md")
    write_markdown(report, markdown)
    return 0


def _compare(args: argparse.Namespace) -> int:
    reports = args.reports
    if not isinstance(reports, list) or not reports:
        raise ValueError("compare needs at least one report")
    loaded = [load_report(path) for path in reports if isinstance(path, Path)]
    if len(loaded) != len(reports):
        raise ValueError("compare reports must be paths")
    _path(args.out, "out").write_text(render_comparison(loaded), encoding="utf-8")
    return 0


def fuse_dataset(
    dataset: BenchDataset,
    observations: Sequence[RouteObservation],
) -> tuple[BenchLandmark, ...]:
    """Build fusion frames from a bench and recorded detections."""
    by_frame = {item.frame_id: item for item in observations}
    frames: list[FusionFrame] = []
    for frame in dataset.frames:
        cloud = _cloud(frame)
        observation = by_frame.get(frame.frame_id)
        detections: list[MaskEvidence] = []
        if observation is not None:
            for index, detection in enumerate(observation.detections):
                mask_id = (
                    observation.mask_ids[index]
                    if index < len(observation.mask_ids)
                    else f"{frame.frame_id}-{index}"
                )
                detections.append(
                    MaskEvidence(
                        mask_id=mask_id,
                        polygon=detection.mask_polygon,
                        score=detection.score,
                        label=detection.label,
                        box_xyxy=detection.box_xyxy,
                        track_id=detection.track_id,
                    )
                )
        rig = StereoRig(
            frame.intrinsics.fx,
            frame.intrinsics.fy,
            frame.intrinsics.cx,
            frame.intrinsics.cy,
            frame.intrinsics.baseline_m,
        )
        frames.append(
            FusionFrame(
                frame_id=frame.frame_id,
                t_ns=frame.t_ns,
                pose=frame.pose,
                rig=rig,
                width=frame.intrinsics.width,
                height=frame.intrinsics.height,
                points=cloud.points,
                detections=tuple(detections),
                points_are_map=cloud.space == "map",
                source="" if observation is None else observation.source,
                model_id="" if observation is None else observation.model_id,
            )
        )
    return fuse(frames, scoring=dataset.scoring)


def _cloud(frame: BenchFrame) -> FrameCloud:
    if frame.cloud_path is None:
        return FrameCloud("camera", ())
    return load_cloud(frame.cloud_path)


def _live_route(
    route: str,
    ledger: UsageLedger,
    usage: UsageCapture,
    model: object,
) -> BenchRoute:
    if route == "meta":
        from surmap.survey.meta_sam import MetaSamDetector

        meta = MetaSamDetector(on_usage=usage, before_call=ledger.check)
        return meta_route(meta, ledger=ledger, usage=usage)
    if route == "modal":
        from surmap.survey.modal_sam import ModalSamDetector

        modal = ModalSamDetector(on_usage=usage, before_call=ledger)
        return modal_route(modal, ledger=ledger, usage=usage)
    if route == "station-onnx":
        if not isinstance(model, str) or not model.strip():
            raise ValueError("station-onnx requires --model")
        from surmap.survey.sam3 import sam3_detector

        station = sam3_detector(Path(model))
        return station_route(station, model_id=model)
    if route == "replay":
        raise ValueError("replay is handled before a detector is built")
    raise ValueError(f"unknown route {route}")


def _labeller(provider: str) -> LabelClient:
    if provider == "baseten":
        from surmap.labelling.baseten_muse import BasetenMuseLabelClient

        return BasetenMuseLabelClient()
    if provider == "modal":
        from surmap.labelling.modal_muse import ModalMuseClient

        client = ModalMuseClient()

        class _ModalLabel:
            def label(self, jpeg: bytes, coarse_label: str, xyz: Vec3) -> ObjectLabel:
                text = client.label(jpeg, coarse_label)
                return ObjectLabel(text, text, None, "modal-muse", text, map_point=xyz)

        return _ModalLabel()
    if provider == "meta":
        raise LiveRouteRefused(
            "Meta Muse in this tree writes a scene note, not a per-landmark label. "
            "Use --provider baseten or --provider modal."
        )
    raise ValueError(f"unknown label provider {provider}")


def _raw_frame(frame: BenchFrame) -> RawFrame:
    data = frame.image_path.read_bytes()
    encoding = "png" if data.startswith(b"\x89PNG\r\n\x1a\n") else "mjpeg"
    return RawFrame(
        frame.frame_id,
        frame.t_ns,
        0,
        frame.intrinsics.width,
        frame.intrinsics.height,
        encoding,
        data,
    )


def _write_landmarks(path: Path, landmarks: Sequence[BenchLandmark]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [_landmark_json(item) for item in landmarks]
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def load_landmarks(path: Path) -> tuple[BenchLandmark, ...]:
    """Read the landmark JSON written by `fuse`."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("landmarks file must be a list")
    return tuple(_landmark(item, index) for index, item in enumerate(raw))


def _landmark_json(item: BenchLandmark) -> dict[str, object]:
    return {
        "landmark_id": item.landmark_id,
        "centroid": {"x": item.centroid.x, "y": item.centroid.y, "z": item.centroid.z},
        "map_frame": item.map_frame,
        "frame_ids": list(item.frame_ids),
        "mask_ids": list(item.mask_ids),
        "track_ids": list(item.track_ids),
        "label": item.label,
        "description": item.description,
        "confidence": item.confidence,
        "provider": item.provider,
        "model_id": item.model_id,
        "prompt_version": item.prompt_version,
        "first_seen_ns": item.first_seen_ns,
        "last_seen_ns": item.last_seen_ns,
        "observation_count": item.observation_count,
        "latitude_deg": item.latitude_deg,
        "longitude_deg": item.longitude_deg,
        "altitude_m": item.altitude_m,
        "best_frame_id": item.best_frame_id,
        "best_box_xyxy": list(item.best_box_xyxy),
        "sam_source": item.sam_source,
        "sam_model_id": item.sam_model_id,
    }


def _landmark(raw: object, index: int) -> BenchLandmark:
    if not isinstance(raw, dict):
        raise ValueError(f"landmark {index} must be an object")
    body = {str(key): value for key, value in raw.items()}
    centroid = body.get("centroid")
    if not isinstance(centroid, dict):
        raise ValueError(f"landmark {index} centroid must be an object")
    point = {str(key): value for key, value in centroid.items()}
    box = body.get("best_box_xyxy", [0, 0, 0, 0])
    if not isinstance(box, list) or len(box) != 4:
        raise ValueError(f"landmark {index} best_box_xyxy must have 4 numbers")
    return BenchLandmark(
        landmark_id=_required_text(body, "landmark_id"),
        centroid=Vec3(
            _required_float(point, "x"), _required_float(point, "y"), _required_float(point, "z")
        ),
        map_frame=_required_text(body, "map_frame"),
        frame_ids=_ints(body.get("frame_ids"), "frame_ids"),
        mask_ids=_texts(body.get("mask_ids"), "mask_ids"),
        track_ids=_ints(body.get("track_ids"), "track_ids"),
        label=_required_text(body, "label"),
        description=_required_text(body, "description") if "description" in body else "",
        confidence=_required_float(body, "confidence"),
        provider=body["provider"] if isinstance(body.get("provider"), str) else "",
        model_id=body["model_id"] if isinstance(body.get("model_id"), str) else "",
        prompt_version=body["prompt_version"]
        if isinstance(body.get("prompt_version"), str)
        else "",
        first_seen_ns=_required_int(body, "first_seen_ns"),
        last_seen_ns=_required_int(body, "last_seen_ns"),
        observation_count=_required_int(body, "observation_count"),
        best_frame_id=_required_int(body, "best_frame_id"),
        best_box_xyxy=(float(box[0]), float(box[1]), float(box[2]), float(box[3])),
        sam_source=body["sam_source"] if isinstance(body.get("sam_source"), str) else "",
        sam_model_id=body["sam_model_id"] if isinstance(body.get("sam_model_id"), str) else "",
    )


def _text(raw: object, where: str) -> str:
    if not isinstance(raw, str) or not raw:
        raise ValueError(f"{where} must be text")
    return raw


def _path(raw: object, where: str) -> Path:
    if not isinstance(raw, Path):
        raise ValueError(f"--{where} is required")
    return raw


def _required_text(body: dict[str, object], key: str) -> str:
    value = body.get(key)
    if not isinstance(value, str):
        raise ValueError(f"{key} must be text")
    return value


def _required_float(body: dict[str, object], key: str) -> float:
    value = body.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{key} must be a number")
    return float(value)


def _required_int(body: dict[str, object], key: str) -> int:
    value = body.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value


def _ints(raw: object, where: str) -> tuple[int, ...]:
    if not isinstance(raw, list):
        raise ValueError(f"{where} must be a list")
    values: list[int] = []
    for item in raw:
        if isinstance(item, bool) or not isinstance(item, int):
            raise ValueError(f"{where} must be integers")
        values.append(item)
    return tuple(values)


def _texts(raw: object, where: str) -> tuple[str, ...]:
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise ValueError(f"{where} must be a list of strings")
    return tuple(str(item) for item in raw)
