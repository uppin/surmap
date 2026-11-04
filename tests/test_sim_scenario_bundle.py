"""A scenario exported as a zip bundle and imported on another station, over real stores.

The bundle carries the latest manifest and every library asset it references, so the receiving
station serves the scene without having fetched anything itself.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from surmap.simulation.scenario_bundle import BundleInvalid, export_bundle, import_bundle
from surmap.simulation.scenario_store import UnknownRecord
from tests.sim_bundle_fakes import (
    COVERED_CAR_BIN,
    COVERED_CAR_ENTRY,
    a_scene_with_the_covered_car,
    a_station_store,
    member_names,
    with_members,
    with_record,
)
from tests.sim_fakes import BIN_BYTES


def test_a_bundle_carries_the_manifest_and_the_library_files_it_uses(tmp_path: Path) -> None:
    # Given a scene that places the downloaded covered car
    store = a_station_store(tmp_path)
    scene = a_scene_with_the_covered_car(store)

    # When it is exported
    bundle = export_bundle(store, scene.id)

    # Then the bundle holds its record and both of the car's files
    assert member_names(bundle) == sorted(["scenario.json", COVERED_CAR_ENTRY, COVERED_CAR_BIN])


def test_a_bundle_imported_on_another_station_is_a_new_scenario_with_its_assets(
    tmp_path: Path,
) -> None:
    # Given a bundle exported from one station
    origin = a_station_store(tmp_path, "origin")
    bundle = export_bundle(origin, a_scene_with_the_covered_car(origin, "Car park").id)
    elsewhere = a_station_store(tmp_path, "elsewhere")

    # When a station that never downloaded the car imports it
    imported = import_bundle(elsewhere, bundle)

    # Then it is the same scene at version 1, with the car's files and credit-bearing record
    assert (imported.id, imported.name, imported.version) == ("car-park", "Car park", 1)
    assert imported.manifest == origin.scenario("car-park").manifest
    assert (elsewhere.library_dir / "polyhaven/covered_car/covered_car.bin").read_bytes() == (
        BIN_BYTES
    )
    assert (
        elsewhere.asset("polyhaven:covered_car").licence
        == origin.asset("polyhaven:covered_car").licence
    )


def test_a_bundle_imported_into_a_scenario_becomes_its_next_version(tmp_path: Path) -> None:
    # Given a station with "Car park" at version 2 and a bundle of another scene
    store = a_station_store(tmp_path)
    target = a_scene_with_the_covered_car(store, "Car park")
    other = store.create_scenario("Flooded street", "flood-street")
    bundle = export_bundle(store, other.id)

    # When the bundle is imported into "Car park"
    imported = import_bundle(store, bundle, into=target.id)

    # Then "Car park" keeps its id and name and now holds the flooded street at version 3
    assert (imported.id, imported.name, imported.version) == ("car-park", "Car park", 3)
    assert imported.manifest == other.manifest


def test_importing_into_an_unknown_scenario_is_unknown(tmp_path: Path) -> None:
    # Given a bundle
    store = a_station_store(tmp_path)
    bundle = export_bundle(store, a_scene_with_the_covered_car(store).id)

    # Then importing it into a scenario the station does not have is refused
    with pytest.raises(UnknownRecord):
        import_bundle(store, bundle, into="no-such-scene")


def test_a_file_whose_hash_does_not_match_its_record_is_refused(tmp_path: Path) -> None:
    # Given a bundle whose car geometry was altered after export
    origin = a_station_store(tmp_path, "origin")
    bundle = export_bundle(origin, a_scene_with_the_covered_car(origin).id)
    tampered = with_members(bundle, {COVERED_CAR_BIN: b"not the car"})

    # Then the import names the file
    with pytest.raises(BundleInvalid, match="covered_car.bin"):
        import_bundle(a_station_store(tmp_path, "elsewhere"), tampered)


def test_a_file_path_leaving_the_library_is_refused(tmp_path: Path) -> None:
    # Given a bundle whose record claims a file outside the library
    origin = a_station_store(tmp_path, "origin")
    bundle = export_bundle(origin, a_scene_with_the_covered_car(origin).id)
    escape = "library/polyhaven/../../../escaped.txt"
    sneaky = with_members(
        with_record(bundle, lambda record: _add_file(record, escape, b"x")), {escape: b"x"}
    )

    # Then the import refuses it and writes nothing outside the library
    with pytest.raises(BundleInvalid, match="escaped.txt"):
        import_bundle(a_station_store(tmp_path, "elsewhere"), sneaky)
    assert not (tmp_path / "escaped.txt").exists()


def test_a_manifest_using_a_library_file_the_bundle_lacks_is_refused(tmp_path: Path) -> None:
    # Given a bundle with the car's geometry dropped, record and all
    origin = a_station_store(tmp_path, "origin")
    bundle = export_bundle(origin, a_scene_with_the_covered_car(origin).id)
    stripped = with_members(
        with_record(bundle, lambda record: record.update(assets=[])),
        {
            COVERED_CAR_ENTRY: None,
            COVERED_CAR_BIN: None,
        },
    )

    # Then a station without the car refuses it, naming the missing file
    with pytest.raises(BundleInvalid, match="covered_car_2k.gltf"):
        import_bundle(a_station_store(tmp_path, "elsewhere"), stripped)


def test_a_file_that_is_not_a_bundle_is_refused(tmp_path: Path) -> None:
    # Given a store
    store = a_station_store(tmp_path)

    # Then a file that is not a zip of a scenario record is refused
    with pytest.raises(BundleInvalid, match="not a SurMap scenario bundle"):
        import_bundle(store, b"PK\x03\x04 but not really")


def test_an_asset_whose_licence_is_refused_is_not_imported(tmp_path: Path) -> None:
    # Given a bundle whose car record was relabelled with a non-commercial licence
    origin = a_station_store(tmp_path, "origin")
    bundle = export_bundle(origin, a_scene_with_the_covered_car(origin).id)
    relabelled = with_record(bundle, lambda record: _set_licence(record, "CC BY-NC 4.0"))

    # Then the import refuses it
    with pytest.raises(BundleInvalid, match="polyhaven:covered_car"):
        import_bundle(a_station_store(tmp_path, "elsewhere"), relabelled)


def _assets(record: dict[str, object]) -> list[dict[str, object]]:
    assets = record["assets"]
    assert isinstance(assets, list)
    return assets


def _add_file(record: dict[str, object], path: str, data: bytes) -> None:
    files = _assets(record)[0]["files"]
    assert isinstance(files, list)
    files.append({"path": path, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)})


def _set_licence(record: dict[str, object], licence: str) -> None:
    _assets(record)[0]["licence"] = licence
