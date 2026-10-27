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

Two ways to reach RTAB-Map, with opposite ownership:

- Owned (default): `docker run` the pinned image per tool, under a
  unique container name this instance records. `close()` removes
  only those exact containers (plus its own staging dir).
- Shared: when the environment variable
  `SURMAP_RTABMAP_SHARED_CONTAINER` (or the `shared_container`
  argument) names an already-running reusable container, the backend
  borrows it — `docker cp` the dataset in, `docker exec` the tools,
  `docker cp` the exports out, and delete only its own staging
  directory inside the container. A shared container is never
  started, stopped, or removed by this backend.
"""

from __future__ import annotations

import io
import math
import os
import shutil
import subprocess
import tempfile
import uuid
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

# Environment variable naming a reusable, already-running RTAB-Map
# container to borrow instead of starting owned ones. The SHARED
# segment marks it as not ours: it is never garbage-collected.
SHARED_CONTAINER_ENV = "SURMAP_RTABMAP_SHARED_CONTAINER"


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
        shared_container: str | None = None,
    ) -> None:
        self._cam0_yaml = cam0_yaml
        self._cam1_yaml = cam1_yaml
        self._imu_yaml = imu_yaml
        self._imu_csv = imu_csv
        self._image = image
        if shared_container is None:
            shared_container = os.environ.get(SHARED_CONTAINER_ENV, "").strip() or None
        self._shared_container = shared_container
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
        # Every sidecar container this instance starts gets a name
        # under this unique prefix, purely so tests/operators can
        # recognise them. Removal is ownership-based (exact names in
        # `_live_containers`), never a prefix/image sweep — see close().
        self._instance_id = uuid.uuid4().hex[:12]
        self._container_prefix = f"surmap-rtabmap-{self._instance_id}"
        self._live_containers: list[str] = []
        self.closed = False

    @property
    def work_dir(self) -> Path:
        """Staging directory this backend owns (removed by `close()`)."""
        return self._work_dir

    @property
    def container_prefix(self) -> str:
        """Name prefix of every Docker container this backend starts."""
        return self._container_prefix

    @property
    def live_containers(self) -> tuple[str, ...]:
        """Sidecar containers started but not yet seen to exit."""
        return tuple(self._live_containers)

    @property
    def shared_container(self) -> str | None:
        """The borrowed reusable container, if in shared mode.

        A shared container is not ours: it is never started, stopped,
        or removed by this backend (see `close()`).
        """
        return self._shared_container

    def _docker_run(self, suffix: str, mounts: list[str], command: list[str]) -> None:
        name = f"{self._container_prefix}-{suffix}"
        argv = ["docker", "run", "--rm", "--name", name]
        for mount in mounts:
            argv += ["-v", mount]
        argv += [self._image, *command]
        self._live_containers.append(name)
        try:
            self._runner(argv)
        except BaseException:
            # The container may still be running (killed client, CI
            # timeout): keep it registered so close() removes it.
            raise
        else:
            self._live_containers.remove(name)

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

    def _run_shared(self) -> None:
        """Run both RTAB-Map tools inside the shared container.

        The dataset is copied into a staging directory unique to this
        backend inside the container, and that directory — only that
        directory — is deleted afterwards, success or failure. The
        shared container itself is left exactly as found.
        """
        shared = self._shared_container
        if shared is None:
            raise SidecarError("_run_shared called without a shared container")
        remote = f"/tmp/surmap-rtabmap-{self._instance_id}"
        self._out.mkdir(parents=True, exist_ok=True)
        try:
            self._runner(["docker", "exec", shared, "mkdir", "-p", f"{remote}/out"])
            self._runner(["docker", "cp", str(self._dataset), f"{shared}:{remote}/dataset"])
            self._runner(
                [
                    "docker",
                    "exec",
                    shared,
                    "rtabmap-euroc_dataset",
                    "--output",
                    f"{remote}/dataset",
                    "--output_name",
                    "rtabmap",
                    f"{remote}/dataset",
                ]
            )
            self._runner(
                [
                    "docker",
                    "exec",
                    shared,
                    "rtabmap-export",
                    "--cloud",
                    "--poses",
                    "--poses_format",
                    "11",
                    "--ascii",
                    "--output_dir",
                    f"{remote}/out",
                    "--output",
                    "cloud",
                    f"{remote}/dataset/rtabmap.db",
                ]
            )
            self._runner(["docker", "cp", f"{shared}:{remote}/out/.", str(self._out)])
        finally:
            try:
                self._runner(["docker", "exec", shared, "rm", "-rf", remote])
            except Exception:
                pass  # best effort: only our staging dir is targeted

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
        if self._shared_container is not None:
            self._run_shared()
            return self._collect_results()
        dataset = str(self._dataset)
        self._docker_run(
            "dataset",
            [f"{dataset}:/data"],
            [
                "rtabmap-euroc_dataset",
                "--output",
                "/data",
                "--output_name",
                "rtabmap",
                "/data",
            ],
        )
        database = self._dataset / "rtabmap.db"
        if not database.is_file():
            raise SidecarError(f"RTAB-Map sidecar produced no database at {database}")
        self._docker_run(
            "export",
            [f"{dataset}:/data:ro", f"{self._out}:/out"],
            [
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
            ],
        )
        return self._collect_results()

    def _collect_results(self) -> list[FrameResult]:
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
        """Tear down only what this backend instance started.

        Ownership, never sweeping: the only containers removed are
        the exact names recorded in `live_containers` when this
        instance issued `docker run` for them. Nothing is enumerated
        by image, label, or name prefix. A shared container named by
        `SURMAP_RTABMAP_SHARED_CONTAINER` is borrowed, never owned:
        it does not appear in `live_containers`, and `close()` issues
        no `docker rm`/`stop`/`kill` against it — it is left running
        for its owner. Likewise the staging directory is deleted only
        when this backend created it; a caller-supplied `work_dir`
        stays.

        Containers that exited normally already removed themselves
        (`--rm`); any still registered as live — the run was killed,
        timed out, or failed mid-flight — are force-removed by name.
        Idempotent, and a later `close()` retries any removal that
        failed the first time.
        """
        if self.closed and not self._live_containers:
            return
        self.closed = True
        for name in list(self._live_containers):
            try:
                self._runner(["docker", "rm", "-f", name])
            except Exception:
                pass  # best effort; a later close() retries it
            else:
                self._live_containers.remove(name)
        if self._owns_work_dir:
            shutil.rmtree(self._work_dir, ignore_errors=True)
