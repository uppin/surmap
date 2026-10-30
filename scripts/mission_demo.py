#!/usr/bin/env python3
"""One-command civilian disaster mission.

Offline (the default) uses the recorded SITL fixture and fakes. It does
not launch Gazebo and it does not call Meta, Baseten, or Modal.

    uv run python scripts/mission_demo.py
    uv run python scripts/mission_demo.py --no-viewer

Live calls the services whose flags are already set
(``SURMAP_LIVE_META``, ``SURMAP_LIVE_BASETEN``, ``SURMAP_LIVE_MODAL``)
and reads keys only inside those clients. Pass a capture directory.
This process does not arm PX4.

    uv run python scripts/mission_demo.py --live --capture ~/sitl-runs/disaster-01

The viewer listens on http://127.0.0.1:8770/ . See docs/mission-demo.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from surmap.mission.demo import (
    MissionConfigError,
    run_live_mission,
    run_offline_mission,
)
from surmap.mission.replay import MissionReplay
from surmap.viewer.server import make_viewer_server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="use flagged live services")
    parser.add_argument("--offline", action="store_true", help="recorded fixtures (the default)")
    parser.add_argument("--capture", type=Path, default=None, help="SITL capture directory")
    parser.add_argument("--output", type=Path, default=Path("mission-demo-out"))
    parser.add_argument("--report", type=Path, default=None, help="copy of the impact JSON")
    parser.add_argument("--no-viewer", action="store_true")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8770)
    args = parser.parse_args(argv)
    if args.live and args.offline:
        print("Pass only one of --live and --offline.", file=sys.stderr)
        return 2
    try:
        if args.live:
            capture = args.capture
            if capture is None:
                from surmap.mission.demo import resolve_live_session

                resolve_live_session(None)
                return 2
            result = run_live_mission(args.output, capture)
        else:
            result = run_offline_mission(args.output)
    except MissionConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.report is not None and args.report.resolve() != result.report_path.resolve():
        args.report.write_text(result.report_path.read_text(encoding="utf-8"), encoding="utf-8")
    _print_summary(result.report_path)
    if args.no_viewer:
        return 0
    return _serve(result.snapshot_path, result.report_path, args.host, args.port)


def _print_summary(report_path: Path) -> None:
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        print(f"Impact report: {report_path}")
        return
    basis = payload.get("basis")
    label = "computed from fixtures" if basis == "fixtures" else basis
    error_text = _number(payload.get("mean_position_error_m"), "m")
    first_text = _number(payload.get("time_to_first_detection_s"), "s")
    print(
        f"Impact ({label}): {payload.get('found')} of {payload.get('total')} "
        f"from the ground-truth people array, mean position error {error_text}, "
        f"time to first detection {first_text}."
    )
    print(f"Report: {report_path}")
    answer = payload.get("ask_answer")
    if isinstance(answer, str):
        print(answer)


def _number(value: object, unit: str) -> str:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return "n/a"
    return f"{float(value):.3f} {unit}"


def _serve(snapshot_path: Path, report_path: Path, host: str, port: int) -> int:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    impact = report if isinstance(report, dict) else None
    try:
        server = make_viewer_server(
        lambda: MissionReplay(snapshot_path),
        host=host,
        port=port,
        fps=1.0,
        impact=impact,
    )
    except OSError as exc:
        print(
            f"Viewer cannot listen on {host}:{port} ({exc}). "
            "Stop the other viewer or pass --port.",
            file=sys.stderr,
        )
        return 1
    bound_host, bound_port = server.server_address[:2]
    shown = "127.0.0.1" if bound_host in ("0.0.0.0", "") else bound_host
    print(f"Viewer: http://{shown}:{bound_port}/  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
