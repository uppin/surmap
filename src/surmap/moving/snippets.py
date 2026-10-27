"""Snippet registry and oracle converters (design section 6.1/6.2)."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class SnippetSpec:
    """One recorded snippet fixture (manifest entry)."""

    snippet_id: str
    scene: str  # traffic | fire | swarm | stereo
    source_url: str
    license: str


@dataclass(frozen=True)
class OracleBox:
    """One annotated mover box on one frame."""

    frame_index: int
    track_id: int
    label: str
    left: float
    top: float
    width: float
    height: float


_SPECS: tuple[SnippetSpec, ...] = (
    SnippetSpec(
        snippet_id="visdrone-mot-traffic",
        scene="traffic",
        source_url="https://github.com/VisDrone/VisDrone-Dataset",
        license="VisDrone research-use terms (no redistribution)",
    ),
    SnippetSpec(
        snippet_id="commons-byrne-traffic-fallback",
        scene="traffic",
        source_url=(
            "https://upload.wikimedia.org/wikipedia/commons/9/90/"
            "Jane_M._Byrne_Interchange_Traffic.webm"
        ),
        license="CC BY-SA 4.0",
    ),
    SnippetSpec(
        snippet_id="boreal-forest-fire",
        scene="fire",
        source_url="https://doi.org/10.23729/fd-72c6cf74-b8eb-3687-860dbf93a1ab94c9",
        license="CC BY 4.0",
    ),
    SnippetSpec(
        snippet_id="commons-wennington-fire-fallback",
        scene="fire",
        source_url=(
            "https://upload.wikimedia.org/wikipedia/commons/6/60/"
            "Harri_Healey_-_Aerial_video_of_Wennington_wildfire%2C_2022.webm"
        ),
        license="CC BY 3.0",
    ),
    SnippetSpec(
        snippet_id="purdue-uav-swarm",
        scene="swarm",
        source_url="https://engineering.purdue.edu/~bouman/UAV_Dataset/Videos.zip",
        license="BSD 3-Clause",
    ),
    SnippetSpec(
        snippet_id="kitti-tracking-stereo",
        scene="stereo",
        source_url="https://s3.eu-central-1.amazonaws.com/avg-kitti/data_tracking_image_2.zip",
        license="CC BY-NC-SA 3.0",
    ),
)


def snippet_specs() -> tuple[SnippetSpec, ...]:
    """All registered snippets (traffic, fire, swarm, KITTI stereo)."""
    return _SPECS


_VISDRONE_LABELS = {
    1: "pedestrian",
    2: "people",
    3: "bicycle",
    4: "car",
    5: "van",
    6: "truck",
    7: "tricycle",
    8: "awning-tricycle",
    9: "bus",
    10: "motor",
}


def parse_visdrone_mot(text: str) -> tuple[OracleBox, ...]:
    """Parse VisDrone MOT annotations into oracle boxes."""
    boxes: list[OracleBox] = []
    for line in text.splitlines():
        parts = [part.strip() for part in line.split(",") if part.strip()]
        if len(parts) < 8:
            continue
        frame, track = int(parts[0]), int(parts[1])
        left, top, width, height = (float(parts[i]) for i in range(2, 6))
        category = int(float(parts[7]))
        boxes.append(
            OracleBox(
                frame,
                track,
                _VISDRONE_LABELS.get(category, str(category)),
                left,
                top,
                width,
                height,
            )
        )
    return tuple(boxes)


def parse_purdue_refined_gt(text: str) -> tuple[OracleBox, ...]:
    """Parse Purdue UAV_Dataset refined_gt annotations into oracle boxes."""
    boxes: list[OracleBox] = []
    for line in text.splitlines():
        parts = line.replace(",", " ").split()
        if len(parts) < 6:
            continue
        frame, track = int(float(parts[0])), int(float(parts[1]))
        left, top, width, height = (float(parts[i]) for i in range(2, 6))
        boxes.append(OracleBox(frame, track, "uav", left, top, width, height))
    return tuple(boxes)


def _projection(calib_text: str, name: str) -> tuple[float, ...]:
    match = re.search(rf"{name}:\s*([-\d.eE+ ]+)", calib_text)
    if match is None:
        raise ValueError(f"calib is missing {name}")
    return tuple(float(value) for value in match.group(1).split())


def kitti_baseline_m(calib_text: str) -> float:
    """Stereo baseline (m) from KITTI P2/P3: (Tx2 - Tx3) / fx."""
    p2 = _projection(calib_text, "P2")
    p3 = _projection(calib_text, "P3")
    return abs((p3[3] - p2[3]) / p2[0])


def kitti_sensor_yaml(calib_text: str, width: int, height: int) -> str:
    """Derive a EuRoC cam sensor.yaml (left camera) from a KITTI calib file."""
    p2 = _projection(calib_text, "P2")
    fx, cx, fy, cy = p2[0], p2[2], p2[5], p2[6]
    return (
        "# KITTI tracking calibration, converted to EuRoC layout (design 6.2).\n"
        "sensor_type: camera\n"
        "comment: KITTI image_02 (rectified)\n\n"
        "T_BS:\n"
        "  cols: 4\n"
        "  rows: 4\n"
        "  data: [1.0, 0.0, 0.0, 0.0,\n"
        "         0.0, 1.0, 0.0, 0.0,\n"
        "         0.0, 0.0, 1.0, 0.0,\n"
        "         0.0, 0.0, 0.0, 1.0]\n\n"
        "rate_hz: 10\n"
        f"resolution: [{width}, {height}]\n"
        "camera_model: pinhole\n"
        f"intrinsics: [{fx}, {fy}, {cx}, {cy}] #fu, fv, cu, cv\n"
        "distortion_model: radial-tangential\n"
        "distortion_coefficients: [0.0, 0.0, 0.0, 0.0]\n"
    )
