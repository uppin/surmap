"""Region-of-interest port: query validation and the in-memory adapter."""

from surmap.slam.regions import (
    InMemoryRegionPointSource,
    RegionPointSource,
    RegionQuery,
    RegionStatus,
    invalid_reason,
)
from surmap.types import Vec3

SQUARE = ((10.0, 10.0), (50.0, 10.0), (50.0, 50.0), (10.0, 50.0))


def a_query(
    query_id: int = 1,
    frame_id: int = 7,
    channel: int = 0,
    width: int = 376,
    height: int = 240,
    polygon: tuple[tuple[float, float], ...] = SQUARE,
) -> RegionQuery:
    return RegionQuery(query_id, frame_id, channel, width, height, polygon)


def test_a_square_on_the_left_channel_is_a_valid_query() -> None:
    # Given / When / Then
    assert invalid_reason(a_query()) is None


def test_a_square_on_the_right_channel_is_a_valid_query() -> None:
    # Given / When / Then
    assert invalid_reason(a_query(channel=1)) is None


def test_a_channel_the_rig_does_not_have_is_invalid() -> None:
    # Given / When / Then
    assert invalid_reason(a_query(channel=2)) == "channel must be 0 or 1"


def test_a_polygon_with_two_vertices_encloses_nothing() -> None:
    # Given / When / Then
    assert invalid_reason(a_query(polygon=SQUARE[:2])) == "polygon needs at least 3 vertices"


def test_a_polygon_on_an_image_without_size_cannot_be_placed() -> None:
    # Given / When / Then
    assert invalid_reason(a_query(width=0)) == "image size must be positive"


def test_the_in_memory_source_answers_with_that_frames_points() -> None:
    # Given a source holding points for frame 7
    points = (Vec3(1.0, 2.0, 3.0), Vec3(1.1, 2.0, 3.0))
    source = InMemoryRegionPointSource({7: points})

    # When frame 7 is queried on the right channel
    result = source.region_points(a_query(query_id=4, channel=1))

    # Then the answer is OK, repeats the query and carries the points
    assert result.status is RegionStatus.OK
    assert (result.query_id, result.frame_id, result.channel) == (4, 7, 1)
    assert result.points == points


def test_the_in_memory_source_reports_a_frame_it_never_held_as_expired() -> None:
    # Given a source holding only frame 7
    source = InMemoryRegionPointSource({7: (Vec3(1.0, 2.0, 3.0),)})

    # When frame 8 is queried
    result = source.region_points(a_query(frame_id=8))

    # Then the frame is reported gone, with no points guessed
    assert result.status is RegionStatus.FRAME_EXPIRED
    assert result.points == ()


def test_the_in_memory_source_records_every_query_and_honours_the_port() -> None:
    # Given an empty source
    source = InMemoryRegionPointSource({})

    # When two queries arrive
    source.region_points(a_query(query_id=1))
    source.region_points(a_query(query_id=2))

    # Then both are recorded in order, and it is a RegionPointSource
    assert [query.query_id for query in source.queries] == [1, 2]
    assert isinstance(source, RegionPointSource)
