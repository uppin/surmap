"""RTAB-Map as a Docker sidecar, behind the `SlamBackend` port.

No RTAB-Map (or any native build) is installed on the host: the
backend stages the streamed stereo pairs as a EuRoC-style dataset,
then runs the pinned RTAB-Map container image over it
(`rtabmap-euroc_dataset` followed by `rtabmap-export`), and parses
the exported optimized poses and assembled cloud back into
`FrameResult`s. Project tooling fetches the pinned image
(`scripts/fetch_rtabmap_fixture.py`); the backend only ever invokes
`docker`, never a host `rtabmap` binary.

Semantics are batch, honestly: RTAB-Map's dataset tools optimize a
whole run, so `process_frame` only stages a pair (pose `None`, no
points) and the real poses/cloud arrive from `flush()`, called once
the stream ends. The assembled cloud is attached to the last posed
result; earlier posed results carry their pose only.
"""

from __future__ import annotations

import io
import math
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Protocol

from PIL import Image

from surmap.slam.base import FrameResult
from surmap.types import Pose, StereoFramePair, Vec3

# Pinned by digest so local and CI runs use exactly the investigated
# image (RTAB-Map 0.24.2, OpenCV 4.6.0), whatever tags move upstream.
PINNED_RTABMAP_IMAGE = (
    "introlab3it/rtabmap@sha256:14a58ac31565f0a0ab2421fa861f6fc43010e54345e13a6a1ccde32d3b0ffdb8"
)


class SidecarError(RuntimeError):
    """Raised when the RTAB-Map sidecar cannot run or its output is bad."""


class CommandRunner(Protocol):
    """Runs one argv to completion, raising on a non-zero exit."""

    def __call__(self, argv: list[str]) -> None: ...


def _subprocess_runner(argv: list[str]) -> None:
    try:
        subprocess.run(argv, check=True, capture_output=True, text=True, timeout=900)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        detail = ""
        if isinstance(exc, subprocess.CalledProcessError):
            detail = f": {(exc.stderr or exc.stdout or '')[-2000:]}"
        raise SidecarError(f"sidecar command failed: {argv[0]} {argv[1:3]}{detail}") from exc


def parse_ply_points(text: str) -> tuple[Vec3, ...]:
    """Vertex `(x, y, z)` points from an ASCII PLY cloud export."""
    lines = text.splitlines()
    try:
        header_end = lines.index("end_header")
        vertex_line = next(line for line in lines[:header_end] if line.startswith("element vertex"))
        count = int(vertex_line.split()[-1])
    except (ValueError, StopIteration) as exc:
        raise SidecarError("PLY export has no readable vertex header") from exc
    points = []
    for line in lines[header_end + 1 : header_end + 1 + count]:
        fields = line.split()
        if len(fields) < 3:
            raise SidecarError(f"PLY vertex line is too short: {line!r}")
        try:
            point = Vec3(float(fields[0]), float(fields[1]), float(fields[2]))
        except ValueError as exc:
            raise SidecarError(f"PLY vertex line is not numeric: {line!r}") from exc
        if all(math.isfinite(component) for component in (point.x, point.y, point.z)):
            points.append(point)
    return tuple(points)


def parse_exported_poses(text: str) -> list[tuple[int, Pose]]:
    """`(t_ns, Pose)` pairs from a `--poses_format 11` pose export.

    Lines are `timestamp x y z qx qy qz qw id` (timestamp in seconds);
    the RTAB-Map node id is not a SurMap frame id, so poses are keyed
    by timestamp and matched to frames by the caller.
    """
    poses: list[tuple[int, Pose]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        if len(fields) < 9:
            raise SidecarError(f"pose export line is too short: {line!r}")
        try:
            values = [float(field) for field in fields[:8]]
        except ValueError as exc:
            raise SidecarError(f"pose export line is not numeric: {line!r}") from exc
        t_s, x, y, z, qx, qy, qz, qw = values
        poses.append((round(t_s * 1_000_000_000), Pose(Vec3(x, y, z), (qx, qy, qz, qw))))
    poses.sort(key=lambda item: item[0])
    return poses


def _stationary_imu_csv(frames: list[StereoFramePair]) -> str:
    """A stationary-IMU CSV covering `frames` (the dataset tool needs one)."""
    header = "#timestamp [ns],w_RS_S_x,w_RS_S_y,w_RS_S_z,a_RS_S_x,a_RS_S_y,a_RS_S_z"
    if not frames:
        return header + "\n"
    rows = [header]
    start, end = frames[0].t_ns, frames[-1].t_ns
    step = 5_000_000  # 200 Hz
    t_ns = start
    while t_ns <= end:
        rows.append(f"{t_ns},0.0,0.0,0.0,9.81,0.0,0.0")
        t_ns += step
    return "\n".join(rows) + "\n"


class SidecarRtabmapBackend:
    """`SlamBackend` whose poses and scene points come from RTAB-Map.

    `cam0_yaml`/`cam1_yaml` are the rig's EuRoC `sensor.yaml` texts at
    the streamed frames' resolution; `imu_yaml`/`imu_csv` are the
    matching IMU calibration/recording when the rig has one (a
    stationary synthetic IMU is staged otherwise, so the dataset tool
    can run). Frames must carry image bytes (`left_data`/`right_data`)
    or refs that are readable image files.
    """

    def __init__(
        self,
        *,
        cam0_yaml: str,
        cam1_yaml: str,
        imu_yaml: str = "",
        imu_csv: str = "",
        image: str = PINNED_RTABMAP_IMAGE,
        runner: CommandRunner | None = None,
        work_dir: Path | None = None,
    ) -> None:
        self._cam0_yaml = cam0_yaml
        self._cam1_yaml = cam1_yaml
        self._imu_yaml = imu_yaml
        self._imu_csv = imu_csv
        self._image = image
        self._runner: CommandRunner = runner if runner is not None else _subprocess_runner
        self._owns_work_dir = work_dir is None
        self._work_dir = (
            work_dir if work_dir is not None else Path(tempfile.mkdtemp(prefix="surmap-rtabmap-"))
        )
        self._dataset = self._work_dir / "dataset"
        self._out = self._work_dir / "out"
        self._frames: list[StereoFramePair] = []
        self._results: list[FrameResult] | None = None
        self._trajectory: list[Pose] = []
        self.closed = False

    def _stage_image(self, frame: StereoFramePair, channel: int) -> None:
        data = frame.left_data if channel == 0 else frame.right_data
        ref = frame.left_ref if channel == 0 else frame.right_ref
        cam_dir = self._dataset / "mav0" / f"cam{channel}" / "data"
        cam_dir.mkdir(parents=True, exist_ok=True)
        target = cam_dir / f"{frame.t_ns}.png"
        if data:
            try:
                with Image.open(io.BytesIO(data)) as image:
                    image.convert("L").save(target, format="PNG")
            except Exception as exc:
                raise SidecarError(
                    f"frame {frame.frame_id} channel {channel} is undecodable: {exc}"
                ) from exc
            return
        source = Path(ref)
        if not source.is_file():
            raise SidecarError(
                f"frame {frame.frame_id} channel {channel} carries no image bytes "
                f"and ref {ref!r} is not a readable file"
            )
        with Image.open(source) as image:
            image.convert("L").save(target, format="PNG")

    def process_frame(self, frame: StereoFramePair) -> FrameResult:
        """Stage one pair for the batch run; no pose or points yet."""
        if self._results is not None:
            raise SidecarError("cannot stage frames after flush()")
        self._stage_image(frame, 0)
        self._stage_image(frame, 1)
        self._frames.append(frame)
        return FrameResult(frame.frame_id, frame.t_ns, None, ())

    def _write_dataset_metadata(self) -> None:
        for channel, yaml_text in ((0, self._cam0_yaml), (1, self._cam1_yaml)):
            cam_dir = self._dataset / "mav0" / f"cam{channel}"
            cam_dir.mkdir(parents=True, exist_ok=True)
            (cam_dir / "sensor.yaml").write_text(yaml_text, encoding="utf-8")
        imu_dir = self._dataset / "mav0" / "imu0"
        imu_dir.mkdir(parents=True, exist_ok=True)
        if self._imu_yaml:
            (imu_dir / "sensor.yaml").write_text(self._imu_yaml, encoding="utf-8")
        imu_csv = self._imu_csv if self._imu_csv else _stationary_imu_csv(self._frames)
        (imu_dir / "data.csv").write_text(imu_csv, encoding="utf-8")

    def _match_frame(self, t_ns: int) -> StereoFramePair | None:
        best: StereoFramePair | None = None
        for frame in self._frames:
            if best is None or abs(frame.t_ns - t_ns) < abs(best.t_ns - t_ns):
                best = frame
        if best is not None and abs(best.t_ns - t_ns) <= 1_000_000:  # exports print µs precision
            return best
        return None

    def flush(self) -> list[FrameResult]:
        """Run RTAB-Map over the staged pairs; return posed results.

        The assembled RTAB-Map cloud is attached (whole, in map frame)
        to the last posed result. Posed results are in timestamp order.
        """
        if self._results is not None:
            return list(self._results)
        if not self._frames:
            self._results = []
            return []
        self._write_dataset_metadata()
        self._out.mkdir(parents=True, exist_ok=True)
        dataset = str(self._dataset)
        self._runner(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{dataset}:/data",
                self._image,
                "rtabmap-euroc_dataset",
                "--output",
                "/data",
                "--output_name",
                "rtabmap",
                "/data",
            ]
        )
        database = self._dataset / "rtabmap.db"
        if not database.is_file():
            raise SidecarError(f"RTAB-Map sidecar produced no database at {database}")
        self._runner(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{dataset}:/data:ro",
                "-v",
                f"{self._out}:/out",
                self._image,
                "rtabmap-export",
                "--cloud",
                "--poses",
                "--poses_format",
                "11",
                "--ascii",
                "--output_dir",
                "/out",
                "--output",
                "cloud",
                "/data/rtabmap.db",
            ]
        )
        poses_file = self._out / "cloud_poses.txt"
        cloud_file = self._out / "cloud_cloud.ply"
        if not poses_file.is_file() or not cloud_file.is_file():
            raise SidecarError("RTAB-Map export produced no poses/cloud files")
        cloud = parse_ply_points(cloud_file.read_text(encoding="utf-8"))
        results: list[FrameResult] = []
        for t_ns, pose in parse_exported_poses(poses_file.read_text(encoding="utf-8")):
            frame = self._match_frame(t_ns)
            if frame is not None:
                results.append(FrameResult(frame.frame_id, frame.t_ns, pose, ()))
        if results and cloud:
            last = results[-1]
            results[-1] = FrameResult(last.frame_id, last.t_ns, last.pose, cloud)
        self._trajectory = [result.pose for result in results if result.pose is not None]
        self._results = results
        return list(results)

    def trajectory(self) -> list[Pose]:
        return list(self._trajectory)

    def close(self) -> None:
        self.closed = True
        if self._owns_work_dir:
            shutil.rmtree(self._work_dir, ignore_errors=True)
