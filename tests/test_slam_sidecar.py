"""Sidecar backend unit tests: a fake command runner stands in for
`docker`, so these verify argv, staging, and export parsing without
RTAB-Map. The real sidecar is exercised by the RTAB-Map E2E.
"""

import io
from pathlib import Path

import pytest
from PIL import Image

from surmap.slam.sidecar import (
    PINNED_RTABMAP_IMAGE,
    SidecarError,
    SidecarRtabmapBackend,
    parse_exported_poses,
    parse_ply_points,
)
from surmap.types import StereoFramePair

CAM_YAML = "sensor_type: camera\nresolution: [376, 240]\n"


def _png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("L", (8, 6), 128).save(buffer, format="PNG")
    return buffer.getvalue()


def _frame(frame_id: int, t_ns: int) -> StereoFramePair:
    return StereoFramePair(frame_id, t_ns, "left", "right", "cal-1", _png_bytes(), _png_bytes())


class _FakeDocker:
    """Pretends to be the two pinned-image runs, writing canned exports."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, argv: list[str]) -> None:
        self.calls.append(argv)
        if argv[1:2] == ["rm"]:
            return
        mounts = {}
        args = iter(range(len(argv)))
        for index in args:
            if argv[index] == "-v":
                host, _, container = argv[index + 1].partition(":")
                mounts[container] = Path(host)
        if "rtabmap-euroc_dataset" in argv:
            dataset = mounts["/data"]
            assert (dataset / "mav0" / "cam0" / "sensor.yaml").is_file()
            assert (dataset / "mav0" / "cam0" / "data" / "1000000000.png").is_file()
            assert (dataset / "mav0" / "imu0" / "data.csv").is_file()
            (dataset / "rtabmap.db").write_bytes(b"fake-db")
        else:
            out = mounts["/out"]
            (out / "cloud_poses.txt").write_text(
                "#timestamp x y z qx qy qz qw id\n"
                "1.0 0.0 0.0 0.0 0.0 0.0 0.0 1.0 1\n"
                "2.0 1.0 0.5 0.25 0.0 0.0 0.0 1.0 2\n",
                encoding="utf-8",
            )
            (out / "cloud_cloud.ply").write_text(
                "ply\nformat ascii 1.0\nelement vertex 2\n"
                "property float x\nproperty float y\nproperty float z\n"
                "end_header\n1.0 2.0 3.0\n4.0 5.0 6.0\n",
                encoding="utf-8",
            )


def test_parse_ply_points_reads_vertices() -> None:
    points = parse_ply_points(
        "ply\nformat ascii 1.0\nelement vertex 2\nproperty float x\nend_header\n1 2 3\n4 5 6\n"
    )
    assert [(p.x, p.y, p.z) for p in points] == [(1.0, 2.0, 3.0), (4.0, 5.0, 6.0)]
    with pytest.raises(SidecarError, match="vertex"):
        parse_ply_points("not a ply")


def test_parse_exported_poses_keys_by_timestamp() -> None:
    poses = parse_exported_poses("2.0 1 0 0 0 0 0 1 7\n# comment\n1.0 0 0 0 0 0 0 1 3\n")
    assert [t_ns for t_ns, _ in poses] == [1_000_000_000, 2_000_000_000]
    assert poses[1][1].position.x == 1.0


def test_sidecar_flush_maps_poses_and_attaches_cloud_to_last(tmp_path: Path) -> None:
    runner = _FakeDocker()
    backend = SidecarRtabmapBackend(
        cam0_yaml=CAM_YAML, cam1_yaml=CAM_YAML, runner=runner, work_dir=tmp_path
    )
    # Given two staged pairs (no pose/points until the batch runs)
    first = backend.process_frame(_frame(1, 1_000_000_000))
    backend.process_frame(_frame(2, 2_000_000_000))
    assert first.pose is None and first.static_points == ()

    # When the sidecar flushes
    results = backend.flush()

    # Then both docker runs used the pinned image, poses are matched by
    # timestamp, and the cloud rides on the last posed result
    assert len(runner.calls) == 2
    assert all(call[0] == "docker" and PINNED_RTABMAP_IMAGE in call for call in runner.calls)
    # Containers are named under the backend's prefix and none are
    # left live once they have exited
    assert all(
        call[call.index("--name") + 1].startswith(backend.container_prefix) for call in runner.calls
    )
    assert backend.live_containers == ()
    assert [result.frame_id for result in results] == [1, 2]
    assert results[0].static_points == ()
    assert len(results[1].static_points) == 2
    assert backend.trajectory()[-1].position.x == 1.0
    assert backend.flush() == results  # cached, sidecar not rerun
    assert len(runner.calls) == 2
    backend.close()
    assert backend.closed


def test_failed_sidecar_run_is_force_removed_on_close(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def failing_runner(argv: list[str]) -> None:
        calls.append(argv)
        if argv[1:2] != ["rm"]:
            raise SidecarError("simulated docker failure")

    backend = SidecarRtabmapBackend(
        cam0_yaml=CAM_YAML, cam1_yaml=CAM_YAML, runner=failing_runner, work_dir=tmp_path / "work"
    )
    backend.process_frame(_frame(1, 1_000_000_000))

    # When the sidecar run fails mid-flight
    with pytest.raises(SidecarError, match="simulated"):
        backend.flush()

    # Then the container stays registered until close() removes it by
    # name, and close() is idempotent — nothing is left behind
    (live,) = backend.live_containers
    backend.close()
    assert ["docker", "rm", "-f", live] in calls
    assert backend.live_containers == ()
    call_count = len(calls)
    backend.close()
    assert len(calls) == call_count


def test_close_never_sweeps_a_reusable_foreign_container(tmp_path: Path) -> None:
    # Given a daemon that also hosts a reusable RTAB-Map container
    # (e.g. one the environment/developer keeps around) — represented
    # by a name this backend did not start
    calls: list[list[str]] = []

    def failing_runner(argv: list[str]) -> None:
        calls.append(argv)
        if argv[1:2] != ["rm"]:
            raise SidecarError("simulated docker failure")

    backend = SidecarRtabmapBackend(
        cam0_yaml=CAM_YAML, cam1_yaml=CAM_YAML, runner=failing_runner, work_dir=tmp_path / "work"
    )
    backend.process_frame(_frame(1, 1_000_000_000))
    with pytest.raises(SidecarError, match="simulated"):
        backend.flush()
    backend.close()

    # Then teardown issued exactly one removal — this backend's own
    # container by exact name — and never enumerated containers (no
    # `docker ps` sweep by prefix/image that could catch the reusable
    # foreign one)
    removals = [call for call in calls if call[1:2] == ["rm"]]
    assert removals == [["docker", "rm", "-f", f"{backend.container_prefix}-dataset"]]
    assert not any(call[1:2] == ["ps"] for call in calls)
    assert not any("reusable" in part for call in calls for part in call)


class _FakeSharedDocker:
    """Pretends a reusable container answers `exec`/`cp` for RTAB-Map."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, argv: list[str]) -> None:
        self.calls.append(argv)
        if argv[1:2] == ["cp"] and ":" in argv[2]:  # copy exports back
            out = Path(argv[3])
            (out / "cloud_poses.txt").write_text(
                "#timestamp x y z qx qy qz qw id\n1.0 0 0 0 0 0 0 1 1\n2.0 1 0 0 0 0 0 1 2\n",
                encoding="utf-8",
            )
            (out / "cloud_cloud.ply").write_text(
                "ply\nformat ascii 1.0\nelement vertex 1\nproperty float x\n"
                "property float y\nproperty float z\nend_header\n1 2 3\n",
                encoding="utf-8",
            )


def test_shared_container_is_borrowed_and_never_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given the SHARED environment variable names a reusable container
    monkeypatch.setenv("SURMAP_RTABMAP_SHARED_CONTAINER", "reusable-rtabmap")
    runner = _FakeSharedDocker()
    backend = SidecarRtabmapBackend(
        cam0_yaml=CAM_YAML, cam1_yaml=CAM_YAML, runner=runner, work_dir=tmp_path / "work"
    )
    assert backend.shared_container == "reusable-rtabmap"
    backend.process_frame(_frame(1, 1_000_000_000))
    backend.process_frame(_frame(2, 2_000_000_000))

    # When the backend runs RTAB-Map through it and is closed
    results = backend.flush()
    calls_at_flush = list(runner.calls)
    backend.close()

    # Then the tools ran via exec/cp inside that container, its own
    # staging directory inside the container was cleaned, and the
    # container itself was never run/stopped/removed — close() issued
    # no further Docker calls at all
    assert [result.frame_id for result in results] == [1, 2]
    assert len(results[1].static_points) == 1
    assert backend.live_containers == ()
    assert all(call[1:2] in (["exec"], ["cp"]) for call in calls_at_flush)
    assert any(call[:4] == ["docker", "exec", "reusable-rtabmap", "rm"] for call in calls_at_flush)
    assert not any(call[1:2] in (["run"], ["rm"], ["stop"], ["kill"]) for call in calls_at_flush)
    assert runner.calls == calls_at_flush


def test_shared_container_failure_still_cleans_only_its_staging_dir(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def failing_shared_runner(argv: list[str]) -> None:
        calls.append(argv)
        if "rtabmap-euroc_dataset" in argv:
            raise SidecarError("simulated tool failure")

    backend = SidecarRtabmapBackend(
        cam0_yaml=CAM_YAML,
        cam1_yaml=CAM_YAML,
        runner=failing_shared_runner,
        work_dir=tmp_path / "work",
        shared_container="reusable-rtabmap",
    )
    backend.process_frame(_frame(1, 1_000_000_000))
    with pytest.raises(SidecarError, match="simulated"):
        backend.flush()
    backend.close()

    # The only removal is `rm -rf` of this backend's staging dir
    # inside the shared container — never the container itself
    removals = [call for call in calls if "rm" in call]
    assert len(removals) == 1
    assert removals[0][:3] == ["docker", "exec", "reusable-rtabmap"]
    assert removals[0][-1].startswith("/tmp/surmap-rtabmap-")
    assert not any(call[1:2] in (["run"], ["rm"], ["stop"], ["kill"]) for call in calls)


def test_cm5_entrypoint_builds_sidecar_from_a_calibration_dir(tmp_path: Path) -> None:
    from surmap.survey.cm5_main import sidecar_backend

    mav0 = tmp_path / "mav0"
    for sensor in ("cam0", "cam1", "imu0"):
        (mav0 / sensor).mkdir(parents=True)
        (mav0 / sensor / "sensor.yaml").write_text(CAM_YAML, encoding="utf-8")
    (mav0 / "imu0" / "data.csv").write_text("t,wx,wy,wz,ax,ay,az\n", encoding="utf-8")

    backend = sidecar_backend(tmp_path)

    assert isinstance(backend, SidecarRtabmapBackend)
    backend.close()


def test_sidecar_rejects_frames_without_images(tmp_path: Path) -> None:
    backend = SidecarRtabmapBackend(
        cam0_yaml=CAM_YAML, cam1_yaml=CAM_YAML, runner=_FakeDocker(), work_dir=tmp_path
    )
    with pytest.raises(SidecarError, match="no image bytes"):
        backend.process_frame(StereoFramePair(1, 1, "missing-left", "missing-right", "cal-1"))
