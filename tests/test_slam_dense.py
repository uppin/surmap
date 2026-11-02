"""Offline region answers from RTAB-Map's journalled dense buffer (no sidecar)."""

import json
from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray

from surmap.slam.dense import (
    ChannelRig,
    DenseBufferRegionSource,
    DenseFrame,
    RegionRig,
    decode_disparity,
    dense_region_points,
    encode_disparity,
    fill_poly,
    project_to_display,
    round_half_away,
    undistort_points,
)
from surmap.slam.regions import RegionPointSource, RegionQuery, RegionResult, RegionStatus
from surmap.types import Pose, Vec3

WIDTH, HEIGHT = 100, 80
FX, CX, CY = 50.0, 50.0, 40.0
BASELINE_M = 0.1
SQUARE = ((20.0, 20.0), (40.0, 20.0), (40.0, 40.0), (20.0, 40.0))
# The sidecar's SGBM disparity is fixed-point: 16 units per pixel.
SUBPIXELS = 16
ORIGIN = Pose(Vec3(0.0, 0.0, 0.0))


def a_pinhole() -> tuple[float, ...]:
    return (FX, 0.0, CX, 0.0, FX, CY, 0.0, 0.0, 1.0)


def a_rig(max_depth_m: float = 30.0, distortion: tuple[float, ...] = (0.0,) * 4) -> RegionRig:
    identity = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)
    left = ChannelRig(
        camera_matrix=a_pinhole(),
        distortion=distortion,
        rotation=identity,
        projection=(FX, 0.0, CX, 0.0, 0.0, FX, CY, 0.0, 0.0, 0.0, 1.0, 0.0),
    )
    right = ChannelRig(
        camera_matrix=a_pinhole(),
        distortion=distortion,
        rotation=identity,
        projection=(FX, 0.0, CX, -FX * BASELINE_M, 0.0, FX, CY, 0.0, 0.0, 0.0, 1.0, 0.0),
    )
    return RegionRig(WIDTH, HEIGHT, BASELINE_M, max_depth_m, (left, right))


def a_wall(disparity_px: float) -> NDArray[np.uint16]:
    return np.full((HEIGHT, WIDTH), round(disparity_px * SUBPIXELS), np.uint16)


def a_dense_frame(
    disparity: NDArray[np.uint16],
    frame_id: int = 7,
    channel: int = 0,
    to_map: Pose = ORIGIN,
) -> DenseFrame:
    return DenseFrame(frame_id, 7_000_000_000, channel, to_map, encode_disparity(disparity))


def a_query(
    polygon: tuple[tuple[float, float], ...] = SQUARE,
    size: tuple[int, int] = (WIDTH, HEIGHT),
    frame_id: int = 7,
    channel: int = 0,
) -> RegionQuery:
    return RegionQuery(1, frame_id, channel, size[0], size[1], polygon)


def xyz(result: RegionResult) -> NDArray[np.float64]:
    return np.array([(p.x, p.y, p.z) for p in result.points], np.float64).reshape(-1, 3)


def test_a_wall_two_metres_away_comes_back_two_metres_away_under_the_polygon() -> None:
    # Given a frame whose disparity puts a flat wall at fx * b / d = 2 m
    frame = a_dense_frame(a_wall(2.5))

    # When a 20 x 20 px square on it is asked
    result = dense_region_points(a_query(), a_rig(), frame)

    # Then every pixel of the square (edges included) is one point on the wall
    assert result.status is RegionStatus.OK
    points = xyz(result)
    assert len(points) == 21 * 21
    np.testing.assert_allclose(points[:, 2], 2.0, atol=1e-6)
    # ... spanning the square's back-projection, (u - cx) * z / fx
    assert float(np.min(points[:, 0])) == pytest.approx(-1.2)
    assert float(np.max(points[:, 0])) == pytest.approx(-0.4)


def test_points_are_placed_with_the_map_transform_the_sidecar_used() -> None:
    # Given the frame's journalled map transform: 1 m right, 2 m up, 3 m on
    frame = a_dense_frame(a_wall(2.5), to_map=Pose(Vec3(1.0, 2.0, 3.0)))

    # When the square is asked
    points = xyz(dense_region_points(a_query(), a_rig(), frame))

    # Then the wall sits 3 m further along z in the map frame
    np.testing.assert_allclose(points[:, 2], 5.0, atol=1e-6)


def test_a_polygon_drawn_on_a_larger_display_image_is_scaled_to_the_rig() -> None:
    # Given the same square, drawn on an image twice the rig's size
    doubled = tuple((2 * x, 2 * y) for x, y in SQUARE)
    frame = a_dense_frame(a_wall(2.5))

    # When both are asked
    native = dense_region_points(a_query(), a_rig(), frame)
    scaled = dense_region_points(a_query(doubled, (2 * WIDTH, 2 * HEIGHT)), a_rig(), frame)

    # Then they cover the same pixels
    assert scaled.points == native.points


def test_pixels_without_a_disparity_or_beyond_the_depth_cap_give_no_point() -> None:
    # Given a wall 2 m away with its left half unmatched, under a 1.5 m depth cap
    disparity = a_wall(2.5)
    disparity[:, :30] = 0

    # When the square is asked with and without the cap
    uncapped = dense_region_points(a_query(), a_rig(), a_dense_frame(disparity))
    capped = dense_region_points(a_query(), a_rig(max_depth_m=1.5), a_dense_frame(disparity))

    # Then only matched pixels count, and nothing beyond the cap does
    assert len(uncapped.points) == 21 * 11
    assert capped.status is RegionStatus.OK and capped.points == ()


def test_the_right_channel_sits_one_baseline_along_x_from_the_left_camera() -> None:
    # Given the same wall seen as the right channel's disparity
    left = dense_region_points(a_query(), a_rig(), a_dense_frame(a_wall(2.5)))
    right = dense_region_points(a_query(channel=1), a_rig(), a_dense_frame(a_wall(2.5), channel=1))

    # Then the right channel's points are offset by the baseline
    np.testing.assert_allclose(xyz(right)[:, 0] - xyz(left)[:, 0], BASELINE_M, atol=1e-6)


def test_undistorting_a_distorted_pixel_returns_where_it_was_rectified() -> None:
    # Given a lens with barrel distortion, and a pixel 30 px off the centre
    rig = a_rig(distortion=(-0.28, 0.07, 0.0002, 0.00002))
    camera = rig.channels[0]
    x, y = (80.0 - CX) / FX, (70.0 - CY) / FX
    r2 = x * x + y * y
    k1, k2, p1, p2 = camera.distortion
    radial = 1 + k1 * r2 + k2 * r2 * r2
    distorted = np.array(
        [
            [
                FX * (x * radial + 2 * p1 * x * y + p2 * (r2 + 2 * x * x)) + CX,
                FX * (y * radial + p1 * (r2 + 2 * y * y) + 2 * p2 * x * y) + CY,
            ]
        ]
    )

    # When the distorted pixel is undistorted
    undistorted = undistort_points(distorted, camera)

    # Then it lands back on the ideal pixel
    np.testing.assert_allclose(undistorted, [[80.0, 70.0]], atol=0.05)


def test_the_journal_holds_the_sidecars_fixed_point_disparity_losslessly() -> None:
    # Given a disparity with sub-pixel steps
    disparity = np.arange(WIDTH * HEIGHT, dtype=np.uint16).reshape(HEIGHT, WIDTH)

    # When it goes through the journal's PNG
    restored = decode_disparity(encode_disparity(disparity))

    # Then not one unit is lost
    np.testing.assert_array_equal(restored, disparity)


def test_the_dense_buffer_answers_only_the_frames_it_holds() -> None:
    # Given a buffer holding frame 7's left channel
    source = DenseBufferRegionSource(a_rig(), [a_dense_frame(a_wall(2.5))])

    # When frame 7, frame 8 and frame 7's right channel are asked
    held = source.region_points(a_query())
    missing = source.region_points(a_query(frame_id=8))
    other_channel = source.region_points(a_query(channel=1))

    # Then only the held frame and channel answer; the rest aged out of the ring
    assert isinstance(source, RegionPointSource)
    assert held.status is RegionStatus.OK and len(held.points) == 21 * 21
    assert missing.status is RegionStatus.FRAME_EXPIRED
    assert other_channel.status is RegionStatus.FRAME_EXPIRED


def test_a_malformed_query_is_invalid_like_the_sidecar_says() -> None:
    # Given a two-vertex "polygon"
    source = DenseBufferRegionSource(a_rig(), [a_dense_frame(a_wall(2.5))])

    # When it is asked
    result = source.region_points(a_query(polygon=((1.0, 1.0), (5.0, 5.0))))

    # Then it is rejected, as the sidecar would
    assert result.status is RegionStatus.INVALID_QUERY


GOLDEN = Path(__file__).parent / "fixtures" / "fill_poly_golden.json"


def golden_cases() -> list[dict[str, object]]:
    loaded = json.loads(GOLDEN.read_text())
    cases = loaded["cases"]
    assert isinstance(cases, list)
    return cases


@pytest.mark.parametrize("case", golden_cases(), ids=lambda case: str(case["name"]))
def test_a_polygon_covers_exactly_the_pixels_the_sidecars_fillpoly_does(
    case: dict[str, object],
) -> None:
    # Given a polygon and the mask OpenCV's fillPoly gave it (the sidecar's raster)
    golden = json.loads(GOLDEN.read_text())
    width, height = int(golden["width"]), int(golden["height"])
    expected = np.zeros((height, width), bool)
    rows = case["rows"]
    assert isinstance(rows, list)
    for row in rows:
        expected[row[0], row[1:]] = True

    # When the journal's raster fills it
    mask = fill_poly(np.array(case["polygon"], np.int64), width, height)

    # Then it covers exactly the same pixels
    np.testing.assert_array_equal(mask, expected)


def test_polygon_vertices_round_half_away_from_zero_like_the_sidecar() -> None:
    # Given rectified vertices on exact halves (C++ lround, not banker's rounding)
    halves = np.array([[0.5, 1.5], [2.5, -0.5], [-1.5, 3.49]])

    # Then they round away from zero
    np.testing.assert_array_equal(round_half_away(halves), [[1, 2], [3, -1], [-2, 3]])


def test_the_dense_buffer_decodes_each_frames_disparity_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import surmap.slam.dense as dense

    # Given a buffer holding one frame, and a count of PNG decodes
    decodes: list[int] = []
    real_decode = dense.decode_disparity

    def counting_decode(png: bytes) -> NDArray[np.uint16]:
        decodes.append(len(png))
        return real_decode(png)

    monkeypatch.setattr(dense, "decode_disparity", counting_decode)
    source = DenseBufferRegionSource(a_rig(), [a_dense_frame(a_wall(2.5))])

    # When SAM's many masks on that frame are asked
    answers = [source.region_points(a_query()) for _ in range(5)]

    # Then its disparity was decoded once, and every answer is the same
    assert len(decodes) == 1
    assert all(answer.points == answers[0].points for answer in answers)


def test_a_region_answer_names_the_camera_its_points_were_placed_from() -> None:
    # Given a frame placed 1 m right, 2 m up, 3 m on in the map
    to_map = Pose(Vec3(1.0, 2.0, 3.0))

    # When the square is asked on each channel
    left = dense_region_points(a_query(), a_rig(), a_dense_frame(a_wall(2.5), to_map=to_map))
    right = dense_region_points(
        a_query(channel=1), a_rig(), a_dense_frame(a_wall(2.5), channel=1, to_map=to_map)
    )

    # Then the left answer carries the frame's camera, the right one sits a baseline along x
    assert left.camera == to_map
    assert right.camera is not None
    assert right.camera.position == Vec3(1.0 + BASELINE_M, 2.0, 3.0)


def test_a_region_answer_that_placed_nothing_names_no_camera() -> None:
    # When a frame the buffer does not hold is asked
    result = dense_region_points(a_query(), a_rig(), None)

    # Then there is no camera to name
    assert result.status is RegionStatus.FRAME_EXPIRED and result.camera is None


def test_region_points_project_back_onto_the_pixels_they_came_from() -> None:
    # Given the square's points on a wall 2 m away, placed from a moved camera
    to_map = Pose(Vec3(1.0, 2.0, 3.0))
    result = dense_region_points(a_query(), a_rig(), a_dense_frame(a_wall(2.5), to_map=to_map))

    # When they are projected onto an image twice the rig's size
    pixels = project_to_display(xyz(result), to_map, a_rig(), 0, (2 * WIDTH, 2 * HEIGHT))

    # Then they land on the square, doubled
    assert pixels.shape == (21 * 21, 2)
    np.testing.assert_allclose(pixels.min(axis=0), [40.0, 40.0], atol=1e-6)
    np.testing.assert_allclose(pixels.max(axis=0), [80.0, 80.0], atol=1e-6)


def test_projection_redistorts_onto_the_raw_image_the_mask_was_drawn_on() -> None:
    # Given a barrel-distorted lens and a raw pixel 30 px off the centre
    rig = a_rig(distortion=(-0.28, 0.07, 0.0002, 0.00002))
    raw = np.array([[80.0, 70.0]])
    rectified = undistort_points(raw, rig.channels[0])
    u, v = rectified[0]
    point = np.array([[(u - CX) * 2.0 / FX, (v - CY) * 2.0 / FX, 2.0]])

    # When the point it back-projects to is projected
    pixels = project_to_display(point, ORIGIN, rig, 0, (WIDTH, HEIGHT))

    # Then it lands back on the raw pixel
    np.testing.assert_allclose(pixels, raw, atol=0.05)


def test_points_behind_the_camera_do_not_project() -> None:
    # Given a point behind the camera and one in front of it
    points = np.array([[0.0, 0.0, -2.0], [0.0, 0.0, 2.0]])

    # When both are projected
    pixels = project_to_display(points, ORIGIN, a_rig(), 0, (WIDTH, HEIGHT))

    # Then only the one in front has a pixel, at the image centre
    assert np.isnan(pixels[0]).all()
    np.testing.assert_allclose(pixels[1], [CX, CY])
