"""surmap-obj v1 text and GLB for objects."""

from __future__ import annotations

import numpy as np
import pytest

from surmap.objects3d import (
    decode_obj_text,
    encode_obj_text,
    read_glb_header,
    write_glb,
)
from tests.object_fakes import (
    a_box,
    a_noisy_box,
    a_square,
    a_summary_of,
    f_lines,
    farthest_from,
    spans,
    the_square_colours,
    two_triangles,
    v_lines,
)

# --- surmap-obj v1 text ----------------------------------------------------------------------


def test_a_dense_cloud_encodes_to_at_most_500_vertices() -> None:
    # Given a 14,000-point car-sized cloud
    points = a_noisy_box()

    # When it is encoded with the default limits
    text = encode_obj_text(a_summary_of(points), points)

    # Then the text carries no more than 500 vertices
    assert 0 < len(v_lines(text)) <= 500


def test_a_decimated_cloud_says_how_many_points_it_came_from() -> None:
    # Given a 14,000-point car-sized cloud
    points = a_noisy_box()

    # When it is encoded with the default limits
    text = encode_obj_text(a_summary_of(points), points)

    # Then the header records the original count
    assert "(decimated from 14000)" in text.splitlines()[1]


def test_a_decimated_cloud_decodes_within_a_centimetre_of_the_original_points() -> None:
    # Given a 14,000-point car-sized cloud far from the map origin
    points = a_noisy_box()

    # When it is encoded and read back
    decoded = decode_obj_text(encode_obj_text(a_summary_of(points), points))

    # Then every vertex lies within 1 cm of a real point
    assert farthest_from(decoded.points, points) <= 0.01


def test_encoding_the_same_cloud_twice_gives_the_same_text() -> None:
    # Given a 14,000-point cloud and its summary
    points = a_noisy_box()
    summary = a_summary_of(points)

    # When it is encoded twice
    first, second = encode_obj_text(summary, points), encode_obj_text(summary, points)

    # Then the tool result is reproducible
    assert first == second


def test_the_header_names_the_object_frame_up_axis_and_unit() -> None:
    # Given a car's cloud in the y-down demo map
    points = a_noisy_box()

    # When it is encoded
    text = encode_obj_text(a_summary_of(points, id="obj_17", label="car", up_axis="-y"), points)

    # Then the first line says what the block is and how to read it
    assert text.splitlines()[0] == "# surmap-obj v1 id=obj_17 label=car frame=map up=-y unit=cm"


def test_vertices_are_integer_centimetres_from_the_box_centre() -> None:
    # Given a 1 m square around (412.35, -88.10, 2.04)
    points = a_square()

    # When it is encoded
    text = encode_obj_text(a_summary_of(points), points)

    # Then each corner is written 50 cm from the centre, in input order
    assert v_lines(text) == ["v -50 0 -50", "v 50 0 -50", "v 50 0 50", "v -50 0 50"]


def test_a_small_cloud_keeps_every_point_and_is_not_marked_decimated() -> None:
    # Given four corners a metre apart, sparser than the 5 cm voxel
    points = a_square()

    # When it is encoded
    text = encode_obj_text(a_summary_of(points), points)

    # Then nothing was dropped and the header says so
    assert (len(v_lines(text)), "decimated" in text) == (4, False)


def test_a_decoded_block_returns_to_map_metres() -> None:
    # Given a 1 m square around (412.35, -88.10, 2.04)
    points = a_square()

    # When it is encoded and read back
    decoded = decode_obj_text(encode_obj_text(a_summary_of(points), points))

    # Then the corners are back where they were in the map
    assert np.allclose(decoded.points, points, atol=0.01)


def test_colours_ride_on_the_vertex_lines() -> None:
    # Given a coloured square
    points = a_square()

    # When it is encoded with its colours
    text = encode_obj_text(a_summary_of(points), points, colors=the_square_colours())

    # Then each vertex carries its r g b
    assert v_lines(text)[0] == "v -50 0 -50 158 156 153"


def test_colours_decode_back_unchanged() -> None:
    # Given a coloured square
    points, colours = a_square(), the_square_colours()

    # When it is encoded and read back
    decoded = decode_obj_text(encode_obj_text(a_summary_of(points), points, colors=colours))

    # Then the colours are the ones given
    assert decoded.colors is not None and decoded.colors.tolist() == colours.tolist()


def test_faces_encode_as_one_based_f_lines() -> None:
    # Given a square split into two triangles
    points, faces = a_square(), two_triangles()

    # When it is encoded with its faces
    text = encode_obj_text(a_summary_of(points), points, faces=faces)

    # Then the faces are OBJ's 1-based index lines
    assert f_lines(text) == ["f 1 2 3", "f 1 3 4"]


def test_faces_decode_back_to_zero_based_indices() -> None:
    # Given a square split into two triangles
    points, faces = a_square(), two_triangles()

    # When it is encoded and read back
    decoded = decode_obj_text(encode_obj_text(a_summary_of(points), points, faces=faces))

    # Then the same triangles come back
    assert decoded.faces is not None and decoded.faces.tolist() == faces.tolist()


def test_a_decoded_block_remembers_where_it_came_from() -> None:
    # Given a car's cloud in the y-down demo map
    points = a_noisy_box()

    # When it is encoded and read back
    decoded = decode_obj_text(encode_obj_text(a_summary_of(points), points))

    # Then the decoder knows the object, its frame and the original point count
    assert (decoded.id, decoded.label, decoded.frame, decoded.up_axis, decoded.decimated_from) == (
        "obj_17",
        "car",
        "map",
        "-y",
        14_000,
    )


def test_text_that_is_not_a_surmap_obj_block_is_refused() -> None:
    # Given a plain Wavefront OBJ file
    text = "v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n"

    # When / Then decoding it is refused
    with pytest.raises(ValueError):
        decode_obj_text(text)


# --- GLB -------------------------------------------------------------------------------------


def test_a_glb_is_gltf_version_2() -> None:
    # Given a square's points
    points = a_square()

    # When they are written as GLB
    header = read_glb_header(write_glb(points, frame="map", up_axis="-y"))

    # Then the container is binary glTF 2.0
    assert (header.magic, header.version) == (b"glTF", 2)


def test_a_glb_header_states_the_file_length() -> None:
    # Given a square's points
    points = a_square()

    # When they are written as GLB
    data = write_glb(points, frame="map", up_axis="-y")

    # Then the header's length is the whole file
    assert read_glb_header(data).length == len(data)


def test_a_point_set_is_a_points_primitive() -> None:
    # Given a square's points and no faces
    points = a_square()

    # When they are written as GLB
    header = read_glb_header(write_glb(points, frame="map", up_axis="-y"))

    # Then the one primitive draws points (mode 0)
    assert header.primitive_modes == (0,)


def test_a_mesh_is_a_triangles_primitive() -> None:
    # Given a square split into two triangles
    points, faces = a_square(), two_triangles()

    # When it is written as GLB
    header = read_glb_header(write_glb(points, faces=faces, frame="map", up_axis="-y"))

    # Then the one primitive draws triangles (mode 4)
    assert header.primitive_modes == (4,)


def test_the_position_accessor_bounds_are_the_axis_aligned_box() -> None:
    # Given a 4 x 2 x 1 m box centred at (10, 5, 1)
    points = a_box(centre=(10.0, 5.0, 1.0))

    # When it is written as GLB
    header = read_glb_header(write_glb(points, frame="map", up_axis="+z"))

    # Then the accessor's min and max span the box
    assert spans(header.position_min, header.position_max, (8.0, 4.0, 0.5), (12.0, 6.0, 1.5))


def test_a_glb_names_its_frame_and_up_axis() -> None:
    # Given a square's points in the y-down demo map
    points = a_square()

    # When they are written as GLB
    header = read_glb_header(write_glb(points, frame="map", up_axis="-y"))

    # Then the asset says where its coordinates live
    assert header.asset_extras == {"frame": "map", "up_axis": "-y"}


def test_a_point_set_binary_chunk_holds_float32_positions() -> None:
    # Given four points
    points = a_square()

    # When they are written as GLB
    header = read_glb_header(write_glb(points, frame="map", up_axis="-y"))

    # Then the BIN chunk is four float32 xyz triples
    assert header.bin_chunk_length == 4 * 3 * 4
