"""Dense stereo fallback for masks the sparse RTAB-Map cloud misses."""

from __future__ import annotations

import json
import shutil
import time
import urllib.request
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from surmap.labelling.baseten_muse import ObjectLabel
from surmap.labelling.meta_muse import (
    MetaMuseConceptClient,
    MetaMuseLabelClient,
    MetaMuseSceneClient,
)
from surmap.mission.demo import run_live_mission
from surmap.mission.dense import DenseStereoFallback
from surmap.slam.base import FrameResult
from surmap.survey.meta_sam import MetaSamDetector
from surmap.survey.sam import RawFrame, SamDetection
from surmap.survey.stereo import StereoRig
from surmap.types import Pose, StereoFramePair, Vec3

_TINY = Path(__file__).parent / "fixtures" / "sitl_capture_tiny"
_DISPARITY = 4  # px; tiny rig fx 50, baseline 0.12 -> 1.5 m
_EXPECTED_DEPTH_M = 50.0 * 0.12 / _DISPARITY


def _texture(width: int, height: int, seed: int = 3) -> np.ndarray:
    rng = np.random.default_rng(seed)
    blocks = rng.random((height // 3 + 2, width // 3 + 2))
    return np.repeat(np.repeat(blocks, 3, axis=0), 3, axis=1)[:height, :width] * 255.0


def _textured_capture(root: Path, *, textbook: bool = True) -> Path:
    """The tiny capture with a textured pair at one known disparity.

    ``textbook`` is the Gazebo rig geometry: the right eye sees the scene
    ``_DISPARITY`` px further left (x_r = x_l - d).
    """
    capture = root / "capture"
    shutil.copytree(_TINY, capture)
    texture = _texture(64 + 2 * _DISPARITY, 48)
    left = texture[:, _DISPARITY : _DISPARITY + 64]
    offset = _DISPARITY + _DISPARITY if textbook else 0
    right = texture[:, offset : offset + 64]
    for index in (0, 1):
        Image.fromarray(left.astype(np.uint8)).save(capture / "images" / f"left_{index:03d}.png")
        Image.fromarray(right.astype(np.uint8)).save(capture / "images" / f"right_{index:03d}.png")
    return capture


def _pair(capture: Path, frame_id: int = 0) -> StereoFramePair:
    return StereoFramePair(
        frame_id,
        0,
        str(capture / "images" / f"left_{frame_id:03d}.png"),
        str(capture / "images" / f"right_{frame_id:03d}.png"),
        "gazebo-stereo-v1",
    )


_RIG = StereoRig(50.0, 50.0, 32.0, 24.0, 0.12)


@pytest.mark.parametrize("textbook", [True, False])
def test_both_disparity_conventions_give_the_known_depth(tmp_path: Path, textbook: bool) -> None:
    capture = _textured_capture(tmp_path, textbook=textbook)
    dense = DenseStereoFallback(_RIG, 64, 48, max_depth_m=30.0, min_disparity_px=2.0)

    points = dense.camera_points(_pair(capture))

    assert len(points) > 100
    depths = sorted(point.z for point in points)
    assert depths[len(depths) // 2] == pytest.approx(_EXPECTED_DEPTH_M, rel=0.15)


def test_one_reconstruction_per_frame_is_shared_by_its_masks(tmp_path: Path) -> None:
    capture = _textured_capture(tmp_path)
    dense = DenseStereoFallback(_RIG, 64, 48, max_depth_m=30.0, min_disparity_px=2.0)

    first = dense.camera_points(_pair(capture, 0))
    again = dense.camera_points(_pair(capture, 0))
    dense.camera_points(_pair(capture, 1))

    assert again is first
    assert dense.reconstructions == 2


def test_the_depth_cap_and_minimum_disparity_bound_the_points(tmp_path: Path) -> None:
    capture = _textured_capture(tmp_path)
    # A 5 px minimum disparity means nothing beyond fx * B / 5 = 1.2 m survives
    dense = DenseStereoFallback(_RIG, 64, 48, max_depth_m=30.0, min_disparity_px=5.0)
    assert dense.max_depth_m == pytest.approx(1.2)
    assert all(point.z <= 1.2 for point in dense.camera_points(_pair(capture)))


def test_flat_frames_give_no_points() -> None:
    dense = DenseStereoFallback(_RIG, 64, 48, max_depth_m=30.0, min_disparity_px=2.0)
    assert dense.camera_points(_pair(_TINY)) == ()


class _EmptyMap:
    """Streaming backend double: a pose for every frame, no sparse map points."""

    def __init__(self, snapshot: tuple[Vec3, ...] = ()) -> None:
        self.frames: list[StereoFramePair] = []
        self._snapshot = snapshot

    def process_frame(self, frame: StereoFramePair) -> FrameResult:
        self.frames.append(frame)
        return FrameResult(frame.frame_id, frame.t_ns, None, ())

    def flush(self) -> list[FrameResult]:
        pose = Pose(Vec3(0.0, 0.0, 0.0))
        return [FrameResult(f.frame_id, f.t_ns, pose, ()) for f in self.frames]

    def map_snapshot(self) -> tuple[Vec3, ...]:
        return self._snapshot

    def close(self) -> None:
        return None


async def _detect_centre(self: object, frame: RawFrame) -> tuple[SamDetection, ...]:
    del self, frame
    return (
        SamDetection(
            label="person",
            score=0.9,
            box_xyxy=(20.0, 12.0, 44.0, 36.0),
            mask_polygon=((20.0, 12.0), (44.0, 12.0), (44.0, 36.0), (20.0, 36.0)),
        ),
    )


def _live(monkeypatch: pytest.MonkeyPatch, snapshot: tuple[Vec3, ...]) -> list[Vec3]:
    monkeypatch.setenv("SURMAP_LIVE_META", "1")
    monkeypatch.setenv("MODEL_API_KEY", "secret-model-key")
    monkeypatch.delenv("SURMAP_LIVE_BASETEN", raising=False)
    monkeypatch.delenv("SURMAP_LIVE_MODAL", raising=False)
    monkeypatch.delenv("SURMAP_SAM_PROMPT", raising=False)
    monkeypatch.setenv("SURMAP_USAGE_LOG", "/dev/null")

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("test opened the network")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    labelled: list[Vec3] = []

    def label(self: object, jpeg: bytes, coarse_label: str, xyz: Vec3) -> ObjectLabel:
        del self, jpeg, coarse_label
        labelled.append(xyz)
        return ObjectLabel(
            label="survivor",
            description="person",
            confidence=None,
            model_id="test-double",
            raw_text="survivor",
            map_point=xyz,
        )

    def note(self: object, labels: list[str], frame_jpeg: bytes, **kwargs: object) -> str:
        del self, labels, frame_jpeg, kwargs
        return "note"

    def propose(self: object, frame_jpeg: bytes) -> tuple[str, ...]:
        del self, frame_jpeg
        return ("person",)

    backend = _EmptyMap(snapshot)
    monkeypatch.setattr("surmap.mission.demo.open_live_map", lambda _c, **_k: backend)
    monkeypatch.setattr(MetaSamDetector, "detect", _detect_centre)
    monkeypatch.setattr(MetaMuseLabelClient, "label", label)
    monkeypatch.setattr(MetaMuseSceneClient, "note", note)
    monkeypatch.setattr(MetaMuseConceptClient, "propose", propose)
    return labelled


def test_an_empty_sparse_map_keeps_the_detection_with_dense_stereo_points(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given an empty sparse map and a textured stereo pair at 1.5 m
    capture = _textured_capture(tmp_path)
    labelled = _live(monkeypatch, snapshot=())

    # When the live mission runs
    started = time.perf_counter()
    result = run_live_mission(tmp_path / "out", capture)
    elapsed = time.perf_counter() - started
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    snapshot = json.loads(result.snapshot_path.read_text(encoding="utf-8"))

    # Then the person is one object, labelled once, at a plausible depth in front
    assert len(labelled) == 1
    assert labelled[0].z == pytest.approx(_EXPECTED_DEPTH_M, rel=0.15)
    assert abs(labelled[0].x) < 0.5 and abs(labelled[0].y) < 0.5
    tracks = snapshot["landmarks"] + snapshot["dynamic"]
    assert len(tracks) == 1
    assert len(tracks[0]["mask_points"]) > 20
    # And the report says the points came from the stereo fallback
    sources = report["mask_point_sources"]
    assert sources["observations"] == {"sparse-rtabmap": 0, "stereo-fallback": 2}
    assert sources["tracks"] == {"1": ["stereo-fallback"]}
    assert sources["stereo_reconstructions"] == 2
    assert "dense stereo" in report["basis_note"]
    assert elapsed < 10.0


def test_a_sparse_hit_does_not_run_dense_stereo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given a sparse point inside the mask
    capture = _textured_capture(tmp_path)
    labelled = _live(monkeypatch, snapshot=(Vec3(0.0, 0.0, 2.0),))

    result = run_live_mission(tmp_path / "out", capture)
    report = json.loads(result.report_path.read_text(encoding="utf-8"))

    # Then the sparse point is used as before and no stereo pair was matched
    assert labelled == [Vec3(0.0, 0.0, 2.0)]
    sources = report["mask_point_sources"]
    assert sources["observations"] == {"sparse-rtabmap": 2, "stereo-fallback": 0}
    assert sources["stereo_reconstructions"] == 0
    assert report["basis_note"].endswith("live RTAB-Map streaming backend.")
