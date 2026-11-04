#!/usr/bin/env python3
"""Score the Coral COCO profiles on a recorded Bevy simulation capture.

Each profile's CPU twin (fetched by `scripts/fetch_coral_model.py`) runs over the capture's
left frames — the colour ones when the capture was recorded with `--colour` — and every
ground-truth `car` / `person` box is projected into each frame
(`surmap.simulation.detection_eval`). Printed per profile: object-frames each kind was in view
vs. found, and false positives by label.

    uv run python scripts/fetch_coral_model.py
    uv run python scripts/score_sim_detections.py tests/fixtures/bevy_sim_detector_capture
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from surmap.detection import MODEL_PROFILES, CoralDetector
from surmap.simulation.bevy_capture import load_bevy_capture
from surmap.simulation.detection_eval import DetectionReport, detect_capture, score_capture

REPO_ROOT = Path(__file__).resolve().parent.parent
MODEL_DIR = REPO_ROOT / "tests" / "fixtures" / "coral_model"


def _row(name: str, report: DetectionReport) -> str:
    kinds = " | ".join(
        f"{score.found}/{score.visible} ({score.hit_rate:.0%})" for score in report.kinds.values()
    )
    fps = sum(report.false_positives.values())
    labels = ", ".join(
        f"{label} {count}"
        for label, count in sorted(report.false_positives.items(), key=lambda kv: -kv[1])
    )
    return f"| {name} | {kinds} | {fps} ({labels or '-'}) |"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path, help="a recorded capture directory")
    parser.add_argument("--threshold", type=float, default=0.3, help="detector score threshold")
    parser.add_argument("--grey", action="store_true", help="score the grey eye even if colour")
    parser.add_argument("--json", type=Path, help="also write the reports here")
    args = parser.parse_args()
    capture = load_bevy_capture(args.capture)
    if args.grey:
        capture = type(capture)(
            calibration=capture.calibration,
            objects=capture.objects,
            frames=tuple(type(f)(pair=f.pair, pose_enu=f.pose_enu) for f in capture.frames),
            object_tracks=capture.object_tracks,
        )
    colour = any(frame.left_rgb_ref for frame in capture.frames)
    print(f"{args.capture}: {len(capture.frames)} frames, {'colour' if colour else 'grey'}")
    print("| profile | " + " | ".join(f"{k} found/in view" for k in ("car", "person")) + " | FP |")
    print("|---|---|---|---|")
    out: dict[str, object] = {}
    for name, profile in MODEL_PROFILES.items():
        detector = CoralDetector(
            MODEL_DIR / profile.cpu_file,
            MODEL_DIR / "coco_labels.txt",
            score_threshold=args.threshold,
        )
        report = score_capture(capture, detect_capture(capture, detector))
        print(_row(name, report))
        out[name] = {
            "kinds": {k: [s.found, s.visible] for k, s in report.kinds.items()},
            "objects": report.objects,
            "false_positives": report.false_positives,
        }
    if args.json:
        args.json.write_text(json.dumps(out, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
