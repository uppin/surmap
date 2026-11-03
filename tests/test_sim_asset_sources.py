"""The three asset sources behind one protocol, over a canned fetch (no network)."""

import pytest

from surmap.simulation.asset_sources import (
    AmbientCg,
    AssetFile,
    AssetSourceError,
    PolyHaven,
    Sketchfab,
)
from tests.sim_fakes import RecordingFetch


def test_poly_haven_finds_models_by_name_and_tag_as_cc0() -> None:
    # Given Poly Haven's model listing
    source = PolyHaven(RecordingFetch())

    # When cars are searched for
    hits = source.search("car", "model", limit=5)

    # Then the covered car comes back, CC0, with its page and preview
    assert [(h.asset_id, h.licence, h.author) for h in hits] == [
        ("covered_car", "CC0-1.0", "Kirill Sannikov")
    ]
    assert hits[0].page_url == "https://polyhaven.com/a/covered_car"


def test_a_poly_haven_model_downloads_as_its_2k_gltf_and_includes() -> None:
    # Given Poly Haven's file index for the covered car
    source = PolyHaven(RecordingFetch())

    # When its files are listed
    files = source.files("covered_car", "model")

    # Then the glTF entry comes first, then every file it references
    assert [f.path for f in files] == ["covered_car_2k.gltf", "covered_car.bin"]


def test_sketchfab_searches_only_open_downloadable_models() -> None:
    # Given Sketchfab's search API
    fetch = RecordingFetch()
    source = Sketchfab(fetch, token=None)

    # When a burnt car is searched for
    hits = source.search("burnt car", "model", limit=5)

    # Then only CC0 and CC BY downloadable results were asked for, and the hit says CC BY
    assert all("downloadable=true" in url for url in fetch.urls())
    assert sorted(url.split("license=")[1].split("&")[0] for url in fetch.urls()) == ["by", "cc0"]
    assert [(h.asset_id, h.licence, h.author) for h in hits] == [
        ("3f1c0a", "CC Attribution", "photoscanner")
    ]


def test_a_sketchfab_download_without_a_token_names_the_variable() -> None:
    # Given Sketchfab with no API token configured
    source = Sketchfab(RecordingFetch(), token=None)

    # Then downloading says which variable to set
    with pytest.raises(AssetSourceError, match="SKETCHFAB_API_TOKEN"):
        source.files("3f1c0a", "model")


def test_a_sketchfab_download_sends_the_token_and_fetches_the_glb() -> None:
    # Given Sketchfab with a token
    fetch = RecordingFetch()
    source = Sketchfab(fetch, token="secret-token")

    # When the burnt car's files are listed
    files = source.files("3f1c0a", "model")

    # Then the download API was called with the token and the GLB is the file
    assert fetch.requests[0][1] == {"Authorization": "Token secret-token"}
    assert files == [AssetFile(path="model.glb", url="https://sketchfab-prod.s3/burnt-car.glb")]


def test_ambientcg_materials_come_from_the_2k_zip_members() -> None:
    # Given ambientCG's material search
    source = AmbientCg(RecordingFetch())

    # When ground is searched for and the first hit's files are listed
    hit = source.search("ground", "texture", limit=5)[0]
    files = source.files(hit.asset_id, "texture")

    # Then the colour, normal and roughness maps are members of one 2K-JPG zip
    assert (hit.asset_id, hit.licence) == ("Ground054", "CC0-1.0")
    assert {f.member for f in files} == {
        "Ground054_2K-JPG_Color.jpg",
        "Ground054_2K-JPG_NormalGL.jpg",
        "Ground054_2K-JPG_Roughness.jpg",
    }
    assert {f.url for f in files} == {"https://ambientcg.com/get?file=Ground054_2K-JPG.zip"}


def test_sources_do_not_offer_kinds_they_do_not_carry() -> None:
    # Given ambientCG (materials only) and Sketchfab (models only)
    fetch = RecordingFetch()

    # Then asking them for other kinds returns nothing and fetches nothing
    assert AmbientCg(fetch).search("car", "model", limit=5) == []
    assert Sketchfab(fetch, token=None).search("sky", "hdri", limit=5) == []
    assert fetch.requests == []
