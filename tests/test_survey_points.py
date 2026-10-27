from surmap.survey.points import IncrementalPointEmitter
from surmap.types import Vec3

SCENE = 1
CAR = 107


def test_the_first_emission_forwards_every_spawned_point() -> None:
    # Given a scene point and an object point spawned in the first frame
    emitter = IncrementalPointEmitter()

    # When they are emitted
    # Then both are forwarded
    assert emitter.emit(SCENE, [Vec3(1.0, 2.0, 3.0)]) == (Vec3(1.0, 2.0, 3.0),)
    assert emitter.emit(CAR, [Vec3(4.0, 5.0, 6.0)]) == (Vec3(4.0, 5.0, 6.0),)


def test_a_point_still_at_a_sent_position_is_never_resent() -> None:
    # Given a point that was already streamed
    emitter = IncrementalPointEmitter()
    emitter.emit(SCENE, [Vec3(1.0, 2.0, 3.0)])

    # When the next frame reports it at the same position
    # Then nothing is forwarded for it
    assert emitter.emit(SCENE, [Vec3(1.0, 2.0, 3.0)]) == ()


def test_a_point_that_moved_to_a_new_position_is_forwarded() -> None:
    # Given a tracked point that was streamed at its old position
    emitter = IncrementalPointEmitter()
    emitter.emit(CAR, [Vec3(1.0, 2.0, 3.0)])

    # When it is seen somewhere new
    # Then the new position is forwarded
    assert emitter.emit(CAR, [Vec3(1.5, 2.0, 3.0)]) == (Vec3(1.5, 2.0, 3.0),)


def test_the_same_position_under_another_designation_is_a_different_point() -> None:
    # Given scene points already sent at a position
    emitter = IncrementalPointEmitter()
    emitter.emit(SCENE, [Vec3(1.0, 2.0, 3.0)])

    # When an object reports a point at that very position
    # Then it is still forwarded — designations never suppress each other
    assert emitter.emit(CAR, [Vec3(1.0, 2.0, 3.0)]) == (Vec3(1.0, 2.0, 3.0),)


def test_a_duplicate_within_one_batch_is_forwarded_only_once() -> None:
    emitter = IncrementalPointEmitter()
    batch = [Vec3(1.0, 2.0, 3.0), Vec3(1.0, 2.0, 3.0), Vec3(4.0, 5.0, 6.0)]
    assert emitter.emit(SCENE, batch) == (Vec3(1.0, 2.0, 3.0), Vec3(4.0, 5.0, 6.0))


def test_reset_makes_previously_sent_points_forwardable_again() -> None:
    # Given a new stream (reset after a calibration change)
    emitter = IncrementalPointEmitter()
    emitter.emit(SCENE, [Vec3(1.0, 2.0, 3.0)])
    emitter.reset()

    # Then the same position counts as newly spawned again
    assert emitter.emit(SCENE, [Vec3(1.0, 2.0, 3.0)]) == (Vec3(1.0, 2.0, 3.0),)
