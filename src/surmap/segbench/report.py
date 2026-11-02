"""JSON and Markdown reports, including a route comparison table."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, is_dataclass
from pathlib import Path

from surmap.segbench.conventions import CLOCK_NOTE, MAP_FRAME_NOTE, PIXEL_SPACE_NOTE
from surmap.segbench.score import BenchReport


def write_json(report: BenchReport, path: Path) -> None:
    """Write one route report."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report_payload(report), indent=2) + "\n", encoding="utf-8")


def write_markdown(report: BenchReport, path: Path) -> None:
    """Write the human-readable form of one route report."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown(report), encoding="utf-8")


def report_payload(report: BenchReport) -> dict[str, object]:
    """JSON-ready report. Tuples become lists."""
    body = _jsonable(asdict(report))
    if not isinstance(body, dict):
        raise TypeError("report did not become an object")
    payload = {str(key): value for key, value in body.items()}
    payload["schema"] = "surmap.segbench_report.v1"
    scoring = payload.get("scoring")
    if isinstance(scoring, dict):
        payload["map_frame"] = scoring.get("map_frame")
        payload["pixel_space"] = scoring.get("pixel_space")
        payload["clock"] = scoring.get("clock")
    return payload


def render_markdown(report: BenchReport) -> str:
    """One route, with the scoring frame stated before the numbers."""
    scoring = report.scoring
    lines = [
        f"# Segmentation benchmark: {report.route}",
        "",
        f"- Map frame: `{scoring.map_frame}` — {MAP_FRAME_NOTE}",
        f"- Pixel space: `{scoring.pixel_space}` — {PIXEL_SPACE_NOTE}",
        f"- Clock: `{scoring.clock}` — {CLOCK_NOTE}",
        f"- Survivor match radius: {scoring.match_radius_m:.1f} m",
        "",
        "## Per frame",
        "",
        _frame_table(report),
        "",
        "## Summary",
        "",
        f"- Mean IoU: {_num(report.mean_iou)}",
        f"- Boundary F1: {_num(report.mean_boundary_f1)}",
        f"- Pixel precision / recall: "
        f"{_num(report.mean_pixel_precision)} / {_num(report.mean_pixel_recall)}",
        f"- Survivor instance recall: {_optional(report.survivor_instance_recall)}",
        f"- False positives per frame: {_num(report.false_positives_per_frame)}",
        f"- Survivor recall@3 m: {report.found} of {report.total}",
        f"- Mean position error: {_optional(report.mean_position_error_m)} m",
        f"- False-positive landmarks: {report.false_positive_landmarks}",
        f"- Time to first detection: {_optional(report.time_to_first_detection_s)} s",
        f"- Latency p50 / p95: {_optional(report.latency_p50_s)} s / "
        f"{_optional(report.latency_p95_s)} s",
        f"- Tokens in / out: {report.input_tokens} / {report.output_tokens}",
        f"- GPU seconds: {_num(report.gpu_seconds)}",
        f"- Cost: ${report.cost_usd:.6f} (${report.cost_per_frame_usd:.6f} per frame)",
        "",
    ]
    return "\n".join(lines)


def render_comparison(reports: Sequence[Mapping[str, object]]) -> str:
    """A Markdown table of route reports that share a scoring frame."""
    if not reports:
        return "# Route comparison\n\nNo reports.\n"
    frames = {_frame_key(item) for item in reports}
    note = ""
    if len(frames) > 1:
        note = "\nThese reports do not share a scoring frame, clock, and pixel space.\n"
    header = (
        "| route | frames | mean IoU | boundary F1 | pixel P | pixel R | "
        "survivor recall | FP/frame | recall@3m | mean error m | FP landmarks | "
        "t_first s | p50 s | p95 s | usd/frame |"
    )
    rule = "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
    rows = [header, rule]
    for item in reports:
        rows.append(_comparison_row(item))
    return "# Route comparison\n" + note + "\n" + "\n".join(rows) + "\n"


def load_report(path: Path) -> dict[str, object]:
    """Read a report JSON object."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} is not a report object")
    return {str(key): value for key, value in payload.items()}


def _frame_table(report: BenchReport) -> str:
    lines = [
        "| frame | mean IoU | boundary F1 | precision | recall | "
        "survivor recall | false positives |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for frame in report.frames:
        lines.append(
            f"| {frame.frame_id} | {_num(frame.mean_iou)} | {_num(frame.boundary_f1)} | "
            f"{_num(frame.pixel_precision)} | {_num(frame.pixel_recall)} | "
            f"{_optional(frame.survivor_recall)} | {frame.false_positives} |"
        )
    if len(lines) == 2:
        lines.append("| — | — | — | — | — | — | — |")
    return "\n".join(lines)


def _comparison_row(item: Mapping[str, object]) -> str:
    found = item.get("found")
    total = item.get("total")
    recall = f"{found}/{total}" if isinstance(found, int) and isinstance(total, int) else "n/a"
    frames = item.get("frames")
    frame_count = len(frames) if isinstance(frames, list) else 0
    return (
        f"| {item.get('route', '')} | {frame_count} | {_cell(item.get('mean_iou'))} | "
        f"{_cell(item.get('mean_boundary_f1'))} | {_cell(item.get('mean_pixel_precision'))} | "
        f"{_cell(item.get('mean_pixel_recall'))} | {_cell(item.get('survivor_instance_recall'))} | "
        f"{_cell(item.get('false_positives_per_frame'))} | {recall} | "
        f"{_cell(item.get('mean_position_error_m'))} | "
        f"{item.get('false_positive_landmarks', '')} | "
        f"{_cell(item.get('time_to_first_detection_s'))} | {_cell(item.get('latency_p50_s'))} | "
        f"{_cell(item.get('latency_p95_s'))} | {_cell(item.get('cost_per_frame_usd'))} |"
    )


def _frame_key(item: Mapping[str, object]) -> tuple[object, object, object]:
    return (item.get("map_frame"), item.get("pixel_space"), item.get("clock"))


def _jsonable(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_jsonable(item) for item in value]
    if isinstance(value, float | int | str | bool) or value is None:
        return value
    raise TypeError(f"cannot encode {type(value).__name__}")


def _num(value: float) -> str:
    return f"{value:.3f}"


def _optional(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.3f}"


def _cell(value: object) -> str:
    if isinstance(value, bool) or value is None:
        return "n/a"
    if isinstance(value, int | float):
        return f"{float(value):.3f}"
    return "n/a"
