"""The station's simulation store: SQLite catalogue, hashed library, versioned scenarios."""

import hashlib
from pathlib import Path

import pytest

from surmap.simulation.asset_sources import AmbientCg, AssetHit, PolyHaven, Sketchfab
from surmap.simulation.scenario_manifest import ScenarioInvalid, add_model, load_presets
from surmap.simulation.scenario_store import LicenceRefused, ScenarioStore
from tests.sim_fakes import (
    BIN_BYTES,
    DIFF_BYTES,
    GLB_BYTES,
    POC_ASSETS,
    RecordingFetch,
    element_ids,
)


def a_store(tmp_path: Path) -> ScenarioStore:
    return ScenarioStore(
        db_path=tmp_path / "simulation.sqlite",
        library_dir=tmp_path / "library",
        presets=load_presets(POC_ASSETS),
    )


def the_covered_car() -> AssetHit:
    return PolyHaven(RecordingFetch()).search("covered car", "model", limit=1)[0]


def the_burnt_car() -> AssetHit:
    return Sketchfab(RecordingFetch(), token=None).search("burnt car", "model", limit=5)[0]


def an_nc_hit() -> AssetHit:
    return AssetHit(
        source="sketchfab",
        asset_id="nc1",
        kind="model",
        title="Ruined House",
        author="someone",
        licence="CC Attribution-NonCommercial",
        page_url="https://sketchfab.com/3d-models/nc1",
        preview_url="",
    )


def test_a_downloaded_model_lands_in_the_library_with_its_hashes(tmp_path: Path) -> None:
    # Given an empty store
    store = a_store(tmp_path)

    # When the covered car is downloaded from Poly Haven
    stored = store.download(PolyHaven(RecordingFetch()), the_covered_car())

    # Then its files are under library/polyhaven/covered_car with their SHA-256
    assert stored.ref == "polyhaven:covered_car"
    assert stored.entry == "library/polyhaven/covered_car/covered_car_2k.gltf"
    by_path = {f.path: f for f in stored.files}
    binary = by_path["library/polyhaven/covered_car/covered_car.bin"]
    assert binary.sha256 == hashlib.sha256(BIN_BYTES).hexdigest()
    assert (
        tmp_path / "library" / "polyhaven" / "covered_car" / "covered_car.bin"
    ).read_bytes() == BIN_BYTES


def test_a_zip_member_material_is_extracted_into_the_library(tmp_path: Path) -> None:
    # Given ambientCG's ground material
    store = a_store(tmp_path)
    source = AmbientCg(RecordingFetch())
    hit = source.search("ground", "texture", limit=5)[0]

    # When it is downloaded
    stored = store.download(source, hit)

    # Then each map is its own file in the library, not the zip
    colour = tmp_path / "library" / "ambientcg" / "Ground054" / "Ground054_2K-JPG_Color.jpg"
    assert colour.read_bytes() == DIFF_BYTES
    assert stored.entry.endswith("Ground054_2K-JPG_Color.jpg")


def test_a_non_commercial_asset_is_refused_and_nothing_is_fetched(tmp_path: Path) -> None:
    # Given a hit under a non-commercial licence
    store = a_store(tmp_path)
    fetch = RecordingFetch()

    # Then downloading it is refused before any request is made
    with pytest.raises(LicenceRefused, match="non-commercial"):
        store.download(Sketchfab(fetch, token="t"), an_nc_hit())
    assert fetch.requests == []
    assert store.assets() == []


def test_the_library_survives_reopening_the_database(tmp_path: Path) -> None:
    # Given a store that downloaded the burnt car, then closed
    a_store(tmp_path).download(Sketchfab(RecordingFetch(), token="t"), the_burnt_car())

    # When the store is opened again on the same files
    reopened = a_store(tmp_path)

    # Then the asset and its licence are still catalogued
    asset = reopened.asset("sketchfab:3f1c0a")
    assert (asset.title, asset.licence, asset.entry) == (
        "Burnt Car",
        "CC Attribution",
        "library/sketchfab/3f1c0a/model.glb",
    )
    assert asset.files[0].sha256 == hashlib.sha256(GLB_BYTES).hexdigest()


def test_a_scenario_starts_from_a_preset_at_version_one(tmp_path: Path) -> None:
    # Given a store with the shipped presets
    store = a_store(tmp_path)

    # When a scenario is created from the earthquake block
    scenario = store.create_scenario("Morning after", "earthquake-block")

    # Then it has a slug id, version 1 and the preset's elements
    assert (scenario.id, scenario.version) == ("morning-after", 1)
    assert "block-ground" in element_ids(scenario.manifest)


def test_every_save_is_a_new_version_and_the_history_keeps_them(tmp_path: Path) -> None:
    # Given a scenario with the burnt car in the library
    store = a_store(tmp_path)
    car = store.download(Sketchfab(RecordingFetch(), token="t"), the_burnt_car())
    scenario = store.create_scenario("Wreck", "empty-lot")

    # When the car is placed and saved
    placed = add_model(scenario.manifest, car, element_id="wreck-1", position_enu=(3.0, 4.0, 0.0))
    saved = store.save(scenario.id, placed)

    # Then the version advanced, the history has both, and the CC BY author is credited
    assert saved.version == 2
    assert store.history(scenario.id) == [1, 2]
    assert [(c.title, c.author, c.licence) for c in saved.credits] == [
        ("Burnt Car", "photoscanner", "CC Attribution")
    ]


def test_an_invalid_manifest_is_refused_and_the_scenario_is_unchanged(tmp_path: Path) -> None:
    # Given a scenario
    store = a_store(tmp_path)
    scenario = store.create_scenario("Wreck", "empty-lot")
    broken = {**scenario.manifest, "version": 2}

    # Then saving a manifest the renderer would refuse fails, and nothing is stored
    with pytest.raises(ScenarioInvalid, match="version"):
        store.save(scenario.id, broken)
    assert store.scenario(scenario.id).version == 1


def test_two_scenarios_with_one_name_get_distinct_ids(tmp_path: Path) -> None:
    # Given a store
    store = a_store(tmp_path)

    # When two scenarios share a name
    first = store.create_scenario("Flood street", "empty-lot")
    second = store.create_scenario("Flood street", "empty-lot")

    # Then their ids differ and both are listed
    assert first.id != second.id
    assert {s.id for s in store.scenarios()} == {first.id, second.id}


def a_store_with_the_simulation_assets(tmp_path: Path) -> ScenarioStore:
    return ScenarioStore(
        db_path=tmp_path / "simulation.sqlite",
        library_dir=tmp_path / "library",
        presets=load_presets(POC_ASSETS),
        assets_dir=POC_ASSETS,
    )


def credited_titles(store: ScenarioStore, preset: str) -> list[tuple[str, str, str]]:
    scenario = store.create_scenario("Credits", preset)
    return [(c.title, c.author, c.licence) for c in scenario.credits]


def test_a_scenario_with_the_pinned_cc_by_car_credits_its_author(tmp_path: Path) -> None:
    # Given the store over the simulation's own assets
    store = a_store_with_the_simulation_assets(tmp_path)

    # When the shipped block, whose cars are the CC BY Car Concept, becomes a scenario
    credits = credited_titles(store, "earthquake-block")

    # Then the car's author is credited once, under its licence
    assert credits == [("Car Concept", "Eric Chadwick, Darmstadt Graphics Group GmbH", "CC-BY-4.0")]


def test_a_scenario_with_a_bus_credits_the_pinned_bus_model(tmp_path: Path) -> None:
    # Given the store over the simulation's own assets
    store = a_store_with_the_simulation_assets(tmp_path)

    # When the street traffic, which drives a bus, becomes a scenario
    credits = credited_titles(store, "street-traffic")

    # Then the bus model, shown through its vehicle class, is credited
    assert ("Bus", "Poly by Google", "CC-BY-3.0") in credits


def test_a_scenario_with_no_pinned_cc_by_model_credits_none(tmp_path: Path) -> None:
    # Given the store over the simulation's own assets
    store = a_store_with_the_simulation_assets(tmp_path)

    # When the bare lot becomes a scenario
    credits = credited_titles(store, "empty-lot")

    # Then it owes no credit
    assert credits == []
