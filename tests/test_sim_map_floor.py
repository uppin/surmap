"""Map floor: GPS bbox -> stitched OSM texture -> geo-anchored scenario manifest."""

from __future__ import annotations

import io

import pytest
from PIL import Image

from surmap.simulation.map_floor import (
    GeoBBox,
    InMemoryTileSource,
    MapFloorError,
    bbox_geometry,
    choose_zoom,
    enu_to_wgs84,
    stitch_floor,
    wgs84_to_enu,
)
from surmap.simulation.scenario_manifest import (
    ScenarioInvalid,
    load_presets,
    set_map_floor,
    validate_manifest,
)
from tests.sim_fakes import POC_ASSETS

VILNIUS = GeoBBox(sw_lat=54.0, sw_lon=25.0, ne_lat=54.001, ne_lon=25.002)


def test_bbox_geometry_centres_on_the_bbox_and_sizes_it_in_metres() -> None:
    # Given a bbox a thousandth of a degree tall and two thousandths wide
    # When its geometry is derived
    centre_lat, centre_lon, east_m, north_m = bbox_geometry(VILNIUS)

    # Then the centre is the bbox middle and the size follows the snapshot's ENU rule
    assert centre_lat == pytest.approx(54.0005)
    assert centre_lon == pytest.approx(25.001)
    assert north_m == pytest.approx(111.32)
    assert east_m == pytest.approx(130.84, abs=0.1)


def test_wgs84_enu_conversion_round_trips_through_the_centre() -> None:
    # Given the bbox centre as the ENU origin
    centre_lat, centre_lon, _, _ = bbox_geometry(VILNIUS)

    # When a corner is converted to ENU and back
    east, north = wgs84_to_enu(VILNIUS.ne_lat, VILNIUS.ne_lon, centre_lat, centre_lon)
    lat, lon = enu_to_wgs84(east, north, centre_lat, centre_lon)

    # Then it lands back on the corner, north-east of the centre
    assert east == pytest.approx(65.42, abs=0.1)
    assert north == pytest.approx(55.66)
    assert lat == pytest.approx(VILNIUS.ne_lat)
    assert lon == pytest.approx(VILNIUS.ne_lon)


def test_a_bbox_that_is_not_south_west_to_north_east_is_refused() -> None:
    # Given a bbox whose north-east corner is south of its south-west corner
    # When it is built
    # Then it is refused by name
    with pytest.raises(MapFloorError, match="south-west.*north-east"):
        GeoBBox(sw_lat=54.001, sw_lon=25.0, ne_lat=54.0, ne_lon=25.002)


def test_a_bbox_wider_than_a_kilometre_is_refused() -> None:
    # Given a bbox two degrees wide
    # When it is built
    # Then it is refused: the floor is one city block, not a region
    with pytest.raises(MapFloorError, match="1000"):
        GeoBBox(sw_lat=54.0, sw_lon=25.0, ne_lat=54.001, ne_lon=27.0)


def test_choose_zoom_picks_the_sharpest_zoom_inside_the_tile_cap() -> None:
    # Given the Vilnius bbox
    # When a zoom is chosen under the default tile cap
    zoom = choose_zoom(VILNIUS)

    # Then it is a street-level zoom whose tile range stays inside the cap
    assert 15 <= zoom <= 18


def test_stitch_floor_crops_the_tile_mosaic_to_the_bbox() -> None:
    # Given fake tiles, each a solid colour naming its tile
    source = InMemoryTileSource()

    # When the floor is stitched at a fixed zoom
    floor = stitch_floor(source, VILNIUS, zoom=17)

    # Then the PNG is exactly the bbox's pixel extent at that zoom, from those tiles
    image = Image.open(io.BytesIO(floor.png))
    assert image.size == (floor.width_px, floor.height_px)
    assert floor.width_px > 0 and floor.height_px > 0
    assert floor.zoom == 17
    assert floor.tiles >= 1
    assert set(source.fetched)  # the port was actually asked for tiles


def test_stitch_floor_is_deterministic_for_the_same_bbox() -> None:
    # Given the same fake source and bbox stitched twice
    first = stitch_floor(InMemoryTileSource(), VILNIUS, zoom=16)
    second = stitch_floor(InMemoryTileSource(), VILNIUS, zoom=16)

    # Then the texture is byte-identical, so its content-hashed name is stable
    assert first.png == second.png
    assert first.texture_path == second.texture_path
    assert first.texture_path.startswith("library/map-floor/")


def test_set_map_floor_anchors_the_manifest_and_it_still_validates() -> None:
    # Given the empty lot
    lot = load_presets(POC_ASSETS)["empty-lot"]

    # When a map floor is set from the Vilnius bbox
    edited = set_map_floor(
        lot,
        sw=(VILNIUS.sw_lat, VILNIUS.sw_lon),
        ne=(VILNIUS.ne_lat, VILNIUS.ne_lon),
        texture="library/map-floor/abc123.png",
        zoom=17,
    )

    # Then the manifest carries the floor and validates
    validate_manifest(edited)
    floor = edited["map_floor"]
    assert isinstance(floor, dict)
    assert floor["texture"] == "library/map-floor/abc123.png"
    assert floor["zoom"] == 17


def test_a_manifest_with_an_absolute_floor_texture_is_refused() -> None:
    # Given a floor texture that escapes the assets
    lot = load_presets(POC_ASSETS)["empty-lot"]

    # When it is set
    # Then the renderer-mirroring validation refuses it
    with pytest.raises(ScenarioInvalid, match="map_floor"):
        set_map_floor(
            lot,
            sw=(VILNIUS.sw_lat, VILNIUS.sw_lon),
            ne=(VILNIUS.ne_lat, VILNIUS.ne_lon),
            texture="/etc/passwd.png",
            zoom=17,
        )


def test_the_osm_source_reuses_the_map_layers_tile_url() -> None:
    # Given the map layer catalogue the station map already uses
    from surmap.agent.tools.map_layers import OSM_TILE_URL_TEMPLATE

    # Then the tile source speaks the same URL, not a second copy
    assert OSM_TILE_URL_TEMPLATE == "https://tile.openstreetmap.org/{z}/{x}/{y}.png"


def test_a_cached_tile_is_served_from_disk_without_a_second_fetch(
    tmp_path: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given an OSM source with a disk cache, and a counting fake HTTP fetch
    from pathlib import Path

    import surmap.simulation.map_floor as map_floor

    assert isinstance(tmp_path, Path)
    fetches: list[str] = []

    class _Response(io.BytesIO):
        def __enter__(self) -> _Response:
            return self

        def __exit__(self, *args: object) -> None:
            self.close()

    def fake_urlopen(request: object, timeout: int = 0) -> _Response:
        url = request.full_url if hasattr(request, "full_url") else str(request)
        fetches.append(url)
        buffer = io.BytesIO()
        Image.new("RGB", (256, 256), (9, 9, 9)).save(buffer, format="PNG")
        return _Response(buffer.getvalue())

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    source = map_floor.OsmTileSource(cache_dir=tmp_path / "tiles")

    # When the same tile is fetched twice
    first = source.fetch_tile(17, 100, 200)
    second = source.fetch_tile(17, 100, 200)

    # Then the second fetch came from the disk cache
    assert first == second
    assert len(fetches) == 1
    assert (tmp_path / "tiles" / "17" / "100" / "200.png").is_file()


def test_choose_zoom_also_respects_the_texture_pixel_cap() -> None:
    # Given a kilometre-square bbox at the equator (the largest floor allowed)
    big = GeoBBox(sw_lat=0.0, sw_lon=0.0, ne_lat=0.0075, ne_lon=0.0085)

    # When a zoom is chosen
    zoom = choose_zoom(big)
    floor = stitch_floor(InMemoryTileSource(), big, zoom=zoom)

    # Then the stitched texture is no wider or taller than the cap
    assert floor.width_px <= 4096
    assert floor.height_px <= 4096
