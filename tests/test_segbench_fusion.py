"""Voxel log-odds fusion and one Muse crop per landmark."""

from __future__ import annotations

import io

from PIL import Image

from surmap.labelling.baseten_muse import ObjectLabel
from surmap.segbench.fusion import (
    FusionConfig,
    FusionFrame,
    MaskEvidence,
    clipped_probability,
    crop_jpeg,
    evidence_weight,
    fuse,
    label_landmarks,
    label_requests,
)
from surmap.survey.stereo import StereoRig
from surmap.types import Pose, Vec3

_RIG = StereoRig(fx=10.0, fy=10.0, cx=4.0, cy=4.0, baseline_m=0.1)
_WIDE = StereoRig(fx=4.0, fy=4.0, cx=4.0, cy=4.0, baseline_m=0.1)
_FULL = ((0.0, 0.0), (8.0, 0.0), (8.0, 8.0), (0.0, 8.0))
_POSE = Pose(Vec3(0.0, 0.0, 0.0))
_CORNER = ((0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (0.0, 2.0))


def _frame(
    points: tuple[Vec3, ...],
    polygon: tuple[tuple[float, float], ...],
    *,
    frame_id: int = 1,
    t_ns: int = 1_000,
    rig: StereoRig = _RIG,
    score: float = 0.9,
) -> FusionFrame:
    return FusionFrame(
        frame_id=frame_id,
        t_ns=t_ns,
        pose=_POSE,
        rig=rig,
        width=8,
        height=8,
        points=points,
        detections=(
            MaskEvidence(
                mask_id=f"{frame_id}-0",
                polygon=polygon,
                score=score,
                label="person",
                box_xyxy=(0.0, 0.0, 8.0, 8.0),
            ),
        ),
        source="replay",
        model_id="recorded",
    )


def test_clip_and_edge_weight_follow_the_fusion_formula() -> None:
    # Given a saturated score and a boundary pixel versus an interior pixel
    config = FusionConfig()

    # When the probability is clipped and the two weights are compared
    saturated = clipped_probability(1.0, 1.0, config)
    faint = clipped_probability(0.01, 1.0, config)
    on_edge = evidence_weight(2.0, 0.0, config)
    inside = evidence_weight(2.0, 10.0, config)
    far = evidence_weight(40.0, 10.0, config)

    # Then the score stays inside the clip and the edge and the distance both down-weight
    assert saturated == 0.95
    assert faint == 0.05
    assert on_edge < inside
    assert far < inside


def test_the_occluded_point_does_not_move_the_landmark() -> None:
    # Given a subject at 2 m and background at 5 m on the same pixel
    frame = _frame((Vec3(0.0, 0.0, 2.0), Vec3(0.0, 0.0, 5.0)), _FULL)

    # When the frames are fused
    landmarks = fuse((frame,))

    # Then one landmark sits on the nearer point
    assert len(landmarks) == 1
    assert landmarks[0].centroid.z == 2.0
    assert landmarks[0].observation_count == 1
    assert landmarks[0].map_frame == "gazebo_enu"


def test_a_visible_unmasked_point_does_not_become_a_landmark() -> None:
    # Given a point whose pixel lies outside a corner polygon
    frame = _frame((Vec3(0.0, 0.0, 2.0),), _CORNER)

    # When fusion runs
    landmarks = fuse((frame,))

    # Then the negative evidence leaves no landmark
    assert landmarks == ()


def test_two_views_of_one_voxel_are_one_landmark_and_one_label_request() -> None:
    # Given the same subject seen on two frames
    first = _frame((Vec3(0.0, 0.0, 2.0),), _FULL, frame_id=1, t_ns=10)
    second = _frame((Vec3(0.0, 0.0, 2.0),), _FULL, frame_id=2, t_ns=20)

    # When the views are fused and labelling is planned
    landmarks = fuse((first, second))
    requests = label_requests(landmarks)

    # Then there is one landmark, two observations, and one Muse crop
    assert len(landmarks) == 1
    assert landmarks[0].observation_count == 2
    assert landmarks[0].frame_ids == (1, 2)
    assert len(requests) == 1
    assert requests[0].landmark_id == landmarks[0].landmark_id


def test_points_more_than_the_cluster_radius_apart_stay_separate_landmarks() -> None:
    # Given two masked points 1.5 m apart in the map
    frame = FusionFrame(
        frame_id=3,
        t_ns=30,
        pose=_POSE,
        rig=_WIDE,
        width=8,
        height=8,
        points=(Vec3(0.0, 0.0, 2.0), Vec3(1.5, 0.0, 2.0)),
        detections=(MaskEvidence("3-0", _FULL, 0.9, "person", box_xyxy=(0.0, 0.0, 8.0, 8.0)),),
    )

    # When they are fused
    landmarks = fuse((frame,))

    # Then each point is its own landmark
    assert len(landmarks) == 2


def test_the_labeller_is_called_once_on_a_crop_of_the_best_frame() -> None:
    # Given one fused landmark and a frame larger than the detection box
    landmark = fuse((_frame((Vec3(0.0, 0.0, 2.0),), _FULL),))
    image = Image.new("RGB", (32, 24), (20, 40, 60))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    seen: list[tuple[int, int]] = []

    class _Once:
        def label(self, jpeg: bytes, coarse_label: str, xyz: Vec3) -> ObjectLabel:
            with Image.open(io.BytesIO(jpeg)) as opened:
                seen.append(opened.size)
            return ObjectLabel("survivor", "a person", 0.8, "fixture", "survivor", map_point=xyz)

    # When labelling runs with padding that cannot cover the whole frame
    labelled = label_landmarks(
        landmark, {1: buffer.getvalue()}, _Once(), provider="baseten", padding_px=1
    )

    # Then Muse saw one crop smaller than the frame, and the landmark took that label
    assert len(seen) == 1
    assert seen[0][0] < 32
    assert seen[0][1] < 24
    assert labelled[0].label == "survivor"
    assert labelled[0].provider == "baseten"
    assert labelled[0].model_id == "fixture"
    assert labelled[0].prompt_version == "muse-crop-v1"


def test_a_jpeg_crop_is_the_box_plus_padding_clamped_to_the_image() -> None:
    # Given a 32x24 image and a box inset from the edges
    image = Image.new("RGB", (32, 24), (1, 2, 3))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")

    # When the crop is taken with 2 px of padding
    crop = crop_jpeg(buffer.getvalue(), (8.0, 6.0, 18.0, 14.0), padding_px=2)
    with Image.open(io.BytesIO(crop)) as opened:
        size = opened.size

    # Then the crop is that padded box and it is a JPEG
    assert size == (14, 12)
    assert crop.startswith(b"\xff\xd8")
