"""Demo tests: registry/cache logic, overlay projection, and a real
HTTP smoke of the demo server (started and closed in the test).
"""

import hashlib
import io
import json
import threading
import urllib.request
import zipfile
from pathlib import Path

import pytest
from PIL import Image

from surmap.demo.datasets import (
    DATASETS,
    DatasetSpec,
    ensure_dataset,
    load_calibration,
    scaled_sensor_yaml,
)
from surmap.demo.server import DemoPlayer, make_demo_server, project_overlay
from surmap.types import Vec3

CAM0_YAML = """sensor_type: camera
T_BS:
  cols: 4
  rows: 4
  data: [0.0, 0.0, 0.0, 0.0,
         0.0, 0.0, 0.0, -0.05,
         0.0, 0.0, 0.0, 0.0,
         0.0, 0.0, 0.0, 1.0]
rate_hz: 20
resolution: [752, 480]
camera_model: pinhole
intrinsics: [458.0, 457.0, 367.0, 248.0]
distortion_model: radial-tangential
distortion_coefficients: [0.0, 0.0, 0.0, 0.0]
"""
CAM1_YAML = CAM0_YAML.replace("0.0, -0.05,", "0.0, 0.06,")


def _png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("L", (752, 480), 90).save(buffer, format="PNG")
    return buffer.getvalue()


def _tiny_zip(path: Path) -> DatasetSpec:
    png = _png_bytes()
    with zipfile.ZipFile(path, "w") as archive:
        for t_ns in (100, 200):
            archive.writestr(f"mav0/cam0/data/{t_ns}.png", png)
            archive.writestr(f"mav0/cam1/data/{t_ns}.png", png)
        archive.writestr("mav0/cam0/sensor.yaml", CAM0_YAML)
        archive.writestr("mav0/cam1/sensor.yaml", CAM1_YAML)
        archive.writestr("mav0/imu0/sensor.yaml", "sensor_type: imu\n")
        archive.writestr("mav0/imu0/data.csv", "t,wx,wy,wz,ax,ay,az\n")
    data = path.read_bytes()
    return DatasetSpec(
        dataset_id="tiny-test",
        title="Tiny Test",
        description="two pairs",
        zip_url="https://example.invalid/tiny.zip",
        zip_size_bytes=len(data),
        zip_sha256=hashlib.sha256(data).hexdigest(),
        official_url="https://example.invalid/",
    )


def test_the_registry_has_the_euroc_dataset() -> None:
    spec = DATASETS["euroc-v1-01-easy"]
    assert spec.dataset_format == "euroc"
    assert spec.zip_sha256.startswith("a920fe5b")
    assert spec.zip_size_bytes > 1_000_000_000


def test_ensure_dataset_downloads_once_then_hits_the_cache(tmp_path: Path) -> None:
    zip_path = tmp_path / "tiny.zip"
    spec = _tiny_zip(zip_path)
    downloads: list[str] = []

    def fetch(url: str, target: Path) -> None:
        downloads.append(url)
        target.write_bytes(zip_path.read_bytes())

    cache = tmp_path / "cache"
    prepared = ensure_dataset(spec, cache, log=lambda _: None, fetch=fetch)
    again = ensure_dataset(spec, cache, log=lambda _: None, fetch=fetch)

    assert downloads == [spec.zip_url]  # second run was a cache hit
    assert prepared.timestamps_ns == (100, 200)
    assert again.root == prepared.root
    calibration = load_calibration(prepared)
    assert calibration.width == 752
    assert abs(calibration.baseline_m - 0.11) < 1e-9


def test_scaled_sensor_yaml_halves_intrinsics_and_resolution() -> None:
    scaled = scaled_sensor_yaml(CAM0_YAML, 376, 240)
    assert "resolution: [376, 240]" in scaled
    assert "intrinsics: [229.0, 228.5, 183.5, 124.0]" in scaled


def test_project_overlay_filters_and_samples() -> None:
    from surmap.demo.datasets import DemoCalibration

    calibration = DemoCalibration(100.0, 100.0, 50.0, 50.0, 0.1, 100, 100)
    points = (
        Vec3(0.0, 0.0, 1.0),  # centre
        Vec3(0.0, 0.0, -1.0),  # behind
        Vec3(10.0, 0.0, 1.0),  # off-frame
    )
    overlay = project_overlay(points, calibration)
    assert overlay == [{"x": 50.0, "y": 50.0, "d": 1.0}]


def _write_zip_to(_url: str, target: Path, source: Path) -> None:
    target.write_bytes(source.read_bytes())


def _prepared_tiny(tmp_path: Path) -> object:
    zip_path = tmp_path / "tiny.zip"
    spec = _tiny_zip(zip_path)
    return ensure_dataset(
        spec,
        tmp_path / "cache",
        log=lambda _: None,
        fetch=lambda url, target: _write_zip_to(url, target, zip_path),
    )


def test_demo_server_serves_page_health_and_stream_then_closes(tmp_path: Path) -> None:
    prepared = _prepared_tiny(tmp_path)
    server = make_demo_server(prepared, host="127.0.0.1", port=0, with_rtabmap=False)  # type: ignore[arg-type]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host = str(server.server_address[0])
    port = int(server.server_address[1])
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/health", timeout=5) as response:
            assert json.loads(response.read()) == {"status": "ok"}
        with urllib.request.urlopen(f"http://{host}:{port}/", timeout=5) as response:
            assert b"SurMap demo" in response.read()
        with urllib.request.urlopen(f"http://{host}:{port}/stream", timeout=10) as response:
            body = response.read().decode()
        assert body.count("event: frame") == 2
        assert '"point_count"' in body
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    assert not thread.is_alive()


def test_player_paces_frames_and_closes_its_backend(tmp_path: Path) -> None:
    prepared = _prepared_tiny(tmp_path)
    player = DemoPlayer(prepared, fps=50.0, with_rtabmap=False)  # type: ignore[arg-type]
    events = list(player.events())
    assert [event.kind for event in events] == ["frame", "frame"]
    assert all(event.jpeg for event in events)
    with pytest.raises(ValueError, match="fps"):
        DemoPlayer(prepared, fps=0, with_rtabmap=False)  # type: ignore[arg-type]
