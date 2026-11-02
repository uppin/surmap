"""Station surfaces: each dense region point is assigned to one object surface.

Patches are flat grids of points 2 cm apart (one per storage voxel) at a
quarter-voxel offset, so the 10 cm match voxels they cover are exact:
a patch of `columns` x 20 points starting at `x` spans the match-voxel
columns floor(x / 0.1) .. floor((x + 0.02 * (columns - 1)) / 0.1), four
rows deep, one layer thick.
"""

import numpy as np
import pytest
from numpy.typing import NDArray

from surmap.survey.surfaces import SurfaceMap, object_points
from surmap.types import Vec3


def a_patch(x: float, columns: int = 20) -> NDArray[np.float32]:
    xs = x + 0.02 * np.arange(columns)
    ys = 0.005 + 0.02 * np.arange(20)
    grid = np.array([(px, py, 1.005) for px in xs for py in ys], dtype=np.float32)
    return grid


def surface_sizes(surfaces: SurfaceMap) -> dict[int, int]:
    return {surface.surface_id: len(surface.points) for surface in surfaces.surfaces()}


def test_the_first_region_starts_surface_one_with_one_point_per_voxel() -> None:
    # Given no surfaces yet
    surfaces = SurfaceMap()

    # When a car's region arrives with every point twice
    patch = a_patch(0.005)
    assignment = surfaces.assign(1, 7, "car", np.concatenate([patch, patch]))

    # Then surface 1 starts with one point per 2 cm voxel
    assert assignment is not None
    assert (assignment.surface_id, assignment.label, assignment.continued) == (1, "car", False)
    assert len(assignment.points) == assignment.total_points == 400
    assert surface_sizes(surfaces) == {1: 400}


def test_a_region_overlapping_an_earlier_surface_continues_it_under_a_new_track_id() -> None:
    # Given surface 1 from frame 1, SAM track 7
    surfaces = SurfaceMap()
    surfaces.assign(1, 7, "car", a_patch(0.005))

    # When frame 2 sees half of it again under SAM's restarted track id 0
    assignment = surfaces.assign(2, 0, "car", a_patch(0.205))

    # Then the region continues surface 1
    assert assignment is not None
    assert (assignment.surface_id, assignment.track_id, assignment.continued) == (1, 0, True)


def test_a_continued_surface_gains_only_the_points_in_voxels_it_did_not_hold() -> None:
    # Given surface 1 holding 400 voxels
    surfaces = SurfaceMap()
    surfaces.assign(1, 7, "car", a_patch(0.005))

    # When a region half on it, half beyond it, arrives
    assignment = surfaces.assign(2, 7, "car", a_patch(0.205))

    # Then only the 200 points beyond it are new
    assert assignment is not None
    assert (len(assignment.points), assignment.total_points) == (200, 600)
    assert surface_sizes(surfaces) == {1: 600}


def test_a_region_that_overlaps_nothing_starts_a_new_surface() -> None:
    # Given surface 1
    surfaces = SurfaceMap()
    surfaces.assign(1, 7, "car", a_patch(0.005))

    # When a region five metres away arrives
    assignment = surfaces.assign(2, 8, "car", a_patch(5.005))

    # Then it is surface 2
    assert assignment is not None
    assert (assignment.surface_id, assignment.continued) == (2, False)
    assert surface_sizes(surfaces) == {1: 400, 2: 400}


def test_a_region_below_the_overlap_threshold_starts_a_new_surface_and_leaves_shared_voxels() -> (
    None
):
    # Given surface 1 over match columns 0-3
    surfaces = SurfaceMap()
    surfaces.assign(1, 7, "car", a_patch(0.005))

    # When a region over columns 3-8 arrives (4 of its 24 match voxels are surface 1's)
    assignment = surfaces.assign(2, 8, "car", a_patch(0.305, columns=30))

    # Then it starts surface 2 without the 100 points on surface 1's column
    assert assignment is not None
    assert (assignment.surface_id, assignment.continued) == (2, False)
    assert surface_sizes(surfaces) == {1: 400, 2: 500}


def test_points_on_another_surfaces_voxels_stay_with_that_surface() -> None:
    # Given surface 1 over match columns 0-3 and surface 2 over columns 10-13
    surfaces = SurfaceMap()
    surfaces.assign(1, 7, "car", a_patch(0.005))
    surfaces.assign(1, 8, "car", a_patch(1.005))

    # When a region spanning columns 1-11 arrives (12 votes for surface 1, 8 for surface 2)
    assignment = surfaces.assign(2, 0, "car", a_patch(0.105, columns=51))

    # Then it continues surface 1, and its points over surface 2 stay surface 2's
    assert assignment is not None
    assert assignment.surface_id == 1
    assert surface_sizes(surfaces) == {1: 1000, 2: 400}


def test_a_region_with_no_points_assigns_nothing() -> None:
    # Given no surfaces
    surfaces = SurfaceMap()
    version = surfaces.version

    # When a region that stereo could not place arrives
    assignment = surfaces.assign(1, 7, "car", np.zeros((0, 3), np.float32))

    # Then nothing is assigned and the layer is unchanged
    assert assignment is None
    assert surfaces.surfaces() == ()
    assert surfaces.version == version


def test_every_assignment_bumps_the_layer_version() -> None:
    # Given an empty layer
    surfaces = SurfaceMap()
    version = surfaces.version

    # When one region is assigned
    surfaces.assign(1, 7, "car", a_patch(0.005))

    # Then the layer reports a change
    assert surfaces.version > version


def test_a_surface_re_observed_in_place_stays_static() -> None:
    # Given a car seen on frame 1
    surfaces = SurfaceMap()
    surfaces.assign(1, 7, "car", a_patch(0.005))

    # When frames 2 and 3 see it in the same place
    surfaces.assign(2, 7, "car", a_patch(0.005))
    assignment = surfaces.assign(3, 7, "car", a_patch(0.005))

    # Then it is a static surface
    assert assignment is not None and assignment.moving is False
    assert [surface.moving for surface in surfaces.surfaces()] == [False]


def test_a_surface_whose_observations_drift_becomes_a_moving_smeared_surface() -> None:
    # Given a car seen on frame 1
    surfaces = SurfaceMap()
    surfaces.assign(1, 7, "car", a_patch(0.005))

    # When each next frame sees it 20 cm further on
    after_one_step = surfaces.assign(2, 7, "car", a_patch(0.205))
    surfaces.assign(3, 7, "car", a_patch(0.405))
    after_three_steps = surfaces.assign(4, 7, "car", a_patch(0.605))

    # Then 20 cm is still noise, but 60 cm from where it was first seen is motion,
    # and the smear keeps accumulating into the one surface
    assert after_one_step is not None and after_one_step.moving is False
    assert after_three_steps is not None and after_three_steps.moving is True
    assert after_three_steps.surface_id == 1
    assert surface_sizes(surfaces) == {1: 1000}


def test_a_moving_surface_stays_moving_when_it_stops() -> None:
    # Given a surface that has already been seen moving
    surfaces = SurfaceMap()
    for frame_id, x in enumerate((0.005, 0.205, 0.405, 0.605), start=1):
        surfaces.assign(frame_id, 7, "car", a_patch(x))

    # When it is seen back near where it started
    assignment = surfaces.assign(5, 7, "car", a_patch(0.405))

    # Then it is still marked moving: the smear it left is still motion
    assert assignment is not None and assignment.moving is True


# The camera that saw the patches, 4 m in front of their z = 1.005 plane.
CAMERA = Vec3(0.2, 0.2, -3.0)


def a_tail_behind(patch: NDArray[np.float32], metres: float, count: int) -> NDArray[np.float32]:
    """Background points on the rays through the patch, `metres` beyond it."""
    camera = np.array([CAMERA.x, CAMERA.y, CAMERA.z], np.float64)
    rays = patch[:count].astype(np.float64) - camera
    beyond = rays * (1.0 + metres / np.linalg.norm(rays, axis=1, keepdims=True))
    return (camera + beyond).astype(np.float32)


def test_points_far_behind_the_object_along_the_view_ray_are_cut_away() -> None:
    # Given a car's region whose mask edge also caught 100 background points 6 m behind it
    surfaces = SurfaceMap()
    car = a_patch(0.005)
    region = np.concatenate([car, a_tail_behind(car, 6.0, 100)])

    # When it is assigned with the camera that saw it
    assignment = surfaces.assign(1, 7, "car", region, viewpoint=CAMERA)

    # Then only the car's own 400 points make up the surface
    assert assignment is not None
    assert assignment.total_points == 400
    depth = surfaces.surfaces()[0].points[:, 2]
    assert float(depth.max()) == pytest.approx(1.005, abs=1e-4)


def test_the_band_keeps_points_within_its_width_of_the_median_range() -> None:
    # Given a 1.5 m band and background 1 m and 3 m behind a car
    surfaces = SurfaceMap(depth_band_m=1.5)
    car = a_patch(0.005)
    region = np.concatenate([car, a_tail_behind(car, 1.0, 50), a_tail_behind(car, 3.0, 50)])

    # When the region is assigned
    assignment = surfaces.assign(1, 7, "car", region, viewpoint=CAMERA)

    # Then the points 1 m behind are inside the band and those 3 m behind are not
    assert assignment is not None and assignment.total_points == 450


def test_object_points_is_the_band_the_surfaces_apply() -> None:
    # Given a car region with a tail
    car = a_patch(0.005)
    region = np.concatenate([car, a_tail_behind(car, 6.0, 100)])

    # When it is banded on its own
    kept = object_points(region, CAMERA, band_m=1.5)

    # Then exactly the car remains, and without a camera nothing is cut
    np.testing.assert_array_equal(kept, car)
    assert len(object_points(region, None, band_m=1.5)) == 500


def test_a_region_with_too_few_points_starts_no_surface_yet() -> None:
    # Given a far car's mask that recovered only 30 depth points
    surfaces = SurfaceMap(min_points=50)

    # When it is assigned
    assignment = surfaces.assign(1, 7, "car", a_patch(0.005)[:30], viewpoint=CAMERA)

    # Then it is no surface yet
    assert assignment is None
    assert surfaces.surfaces() == ()


def test_the_same_object_becomes_a_surface_once_a_frame_has_enough_depth() -> None:
    # Given a car first seen with 30 points
    surfaces = SurfaceMap(min_points=50)
    surfaces.assign(1, 7, "car", a_patch(0.005)[:30], viewpoint=CAMERA)

    # When a later frame recovers its whole patch
    assignment = surfaces.assign(2, 7, "car", a_patch(0.005), viewpoint=CAMERA)

    # Then that frame starts surface 1
    assert assignment is not None
    assert (assignment.surface_id, assignment.continued, assignment.total_points) == (1, False, 400)


def test_a_sparse_region_does_not_grow_an_existing_surface() -> None:
    # Given surface 1 of 400 points
    surfaces = SurfaceMap(min_points=50)
    surfaces.assign(1, 7, "car", a_patch(0.005), viewpoint=CAMERA)

    # When a frame sees only 30 points, just beyond its edge
    assignment = surfaces.assign(2, 7, "car", a_patch(0.205)[-30:], viewpoint=CAMERA)

    # Then nothing is added
    assert assignment is None
    assert surface_sizes(surfaces) == {1: 400}


def test_the_minimum_counts_points_left_after_the_band() -> None:
    # Given 40 car points and 15 background points far behind them
    surfaces = SurfaceMap(min_points=50)
    car = a_patch(0.005)[:40]
    region = np.concatenate([car, a_tail_behind(a_patch(0.005), 6.0, 15)])

    # When the region is assigned
    assignment = surfaces.assign(1, 7, "car", region, viewpoint=CAMERA)

    # Then the 40 left after the band are too few
    assert assignment is None
