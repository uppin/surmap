"""The building presets of `load_presets`: `district-showcase` (the look checkpoint) and
`downtown-blaze` (a glass tower burning on its third floor, with a neighbour downwind)."""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence

from surmap.simulation.building_presets import add_building_fire, set_district
from surmap.simulation.manifest_checks import Manifest

# One rectangle per shipped district on the lot's 200 m ground, west to east; six buildings each
# (east, north, up) on a 2 x 3 grid — heights are whole floors of the district.
_SHOWCASE: Sequence[tuple[str, float, Sequence[tuple[float, float, float]]]] = (
    (
        "old-town",
        -75.0,
        (
            (9, 10, 9.6),
            (11, 9, 12.8),
            (8, 8, 9.6),
            (10, 11, 16.0),
            (9, 9, 12.8),
            (12, 10, 9.6),
        ),
    ),
    (
        "downtown",
        -25.0,
        (
            (14, 14, 36.0),
            (16, 13, 54.0),
            (13, 15, 28.8),
            (15, 15, 72.0),
            (14, 12, 43.2),
            (16, 16, 36.0),
        ),
    ),
    (
        "industrial",
        25.0,
        (
            (18, 14, 10.0),
            (18, 12, 10.0),
            (16, 14, 15.0),
            (18, 14, 10.0),
            (17, 13, 10.0),
            (18, 14, 15.0),
        ),
    ),
    (
        "suburban",
        75.0,
        (
            (9, 8, 5.6),
            (10, 9, 5.6),
            (8, 8, 8.4),
            (10, 8, 5.6),
            (9, 9, 8.4),
            (11, 9, 5.6),
        ),
    ),
)
_GRID = ((-12.5, -22.0), (12.5, -22.0), (-12.5, 0.0), (12.5, 0.0), (-12.5, 22.0), (12.5, 22.0))
DISTRICT_SIZE_M = (50.0, 70.0)

# The blaze block: id, size (east, north, up), position (east, north); the tower is block 1.
_BLAZE: Sequence[tuple[str, tuple[float, float, float], tuple[float, float]]] = (
    ("tower-1", (18.0, 18.0, 43.2), (-10.0, 0.0)),
    ("block-2", (14.0, 14.0, 28.8), (11.0, 0.0)),
    ("block-3", (16.0, 14.0, 32.4), (-42.0, 24.0)),
    ("block-4", (14.0, 14.0, 21.6), (-42.0, -24.0)),
    ("block-5", (15.0, 14.0, 36.0), (34.0, 26.0)),
    ("block-6", (14.0, 15.0, 25.2), (34.0, -26.0)),
    ("block-7", (16.0, 12.0, 18.0), (-8.0, 30.0)),
    ("block-8", (16.0, 12.0, 14.4), (-8.0, -30.0)),
)


def _building(
    building_id: str, size: Sequence[float], position: tuple[float, float]
) -> dict[str, object]:
    return {
        "kind": "building",
        "id": building_id,
        "size_m": list(size),
        "position_enu": [position[0], position[1], 0.0],
    }


def _with_elements(manifest: Mapping[str, object], added: list[dict[str, object]]) -> Manifest:
    edited: Manifest = copy.deepcopy(dict(manifest))
    elements = edited["elements"]
    assert isinstance(elements, list)
    edited["elements"] = [*elements, *added]
    return edited


def district_showcase(lot: Mapping[str, object]) -> Manifest:
    """The empty lot with the four shipped districts side by side, six generic buildings each."""
    showcase = lot
    buildings: list[dict[str, object]] = []
    for name, east, sizes in _SHOWCASE:
        showcase = set_district(
            showcase, name, name, position_enu=(east, 0.0, 0.0), size_m=DISTRICT_SIZE_M, seed=1
        )
        for index, (size, (dx, dy)) in enumerate(zip(sizes, _GRID, strict=True), start=1):
            buildings.append(_building(f"{name}-{index}", size, (east + dx, dy)))
    return _with_elements(showcase, buildings)


def downtown_blaze(lot: Mapping[str, object]) -> Manifest:
    """A downtown block of eight buildings in a 5 m/s westerly, a glass tower alight on its third
    floor at 5 s and a neighbour 5 m downwind of it."""
    block = set_district(
        lot, "core", "downtown", position_enu=(0.0, 0.0, 0.0), size_m=(120.0, 80.0), seed=4
    )
    buildings = [_building(*spec) for spec in _BLAZE]
    buildings[0].update({"facade": "glass", "roof": "metal", "roof_shape": "flat", "floors": 12})
    block = _with_elements(block, buildings)
    block["weather"] = {
        "rain_mm_h": 0.0,
        "wind": {"from_deg": 270.0, "speed_m_s": 5.0, "gust_m_s": 0.0},
    }
    return add_building_fire(block, "blaze-1", building="tower-1", floor=3, start_s=5.0)
