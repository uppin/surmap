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
    assert [result.frame_id for result in results] == [1, 2]
    assert results[0].static_points == ()
    assert len(results[1].static_points) == 2
    assert backend.trajectory()[-1].position.x == 1.0
    assert backend.flush() == results  # cached, sidecar not rerun
    assert len(runner.calls) == 2
    backend.close()
    assert backend.closed


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
