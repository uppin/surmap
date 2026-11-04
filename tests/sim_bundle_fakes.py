"""Builders for the scenario-bundle tests: a station's store, a scene that uses a downloaded model,
and a bundle's members rewritten the way a tampered or hand-made file would be."""

from __future__ import annotations

import io
import json
import zipfile
from collections.abc import Callable, Mapping
from pathlib import Path

from surmap.simulation.asset_sources import PolyHaven
from surmap.simulation.scenario_manifest import add_model, load_presets
from surmap.simulation.scenario_store import Scenario, ScenarioStore
from tests.sim_fakes import POC_ASSETS, RecordingFetch

COVERED_CAR_ENTRY = "library/polyhaven/covered_car/covered_car_2k.gltf"
COVERED_CAR_BIN = "library/polyhaven/covered_car/covered_car.bin"


def a_station_store(tmp_path: Path, name: str = "station") -> ScenarioStore:
    """An empty store of its own under `tmp_path/name`."""
    return ScenarioStore(
        db_path=tmp_path / name / "simulation.sqlite",
        library_dir=tmp_path / name / "library",
        presets=load_presets(POC_ASSETS),
    )


def a_scene_with_the_covered_car(store: ScenarioStore, name: str = "Car park") -> Scenario:
    """`name` on the empty lot, the Poly Haven covered car downloaded and placed on it."""
    source = PolyHaven(RecordingFetch())
    hit = next(h for h in source.search("car", "model", 5) if h.asset_id == "covered_car")
    asset = store.download(source, hit)
    scenario = store.create_scenario(name, "empty-lot")
    return store.save(
        scenario.id,
        add_model(scenario.manifest, asset, element_id="car-1", position_enu=(3.0, 4.0, 0.0)),
    )


def with_record(bundle: bytes, edit: Callable[[dict[str, object]], None]) -> bytes:
    """`bundle` with its `scenario.json` record edited in place by `edit`."""
    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        record = json.loads(archive.read("scenario.json"))
    edit(record)
    return with_members(bundle, {"scenario.json": json.dumps(record).encode()})


def with_members(bundle: bytes, members: Mapping[str, bytes | None]) -> bytes:
    """`bundle` with each member in `members` replaced or added, or dropped when `None`."""
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(bundle)) as source, zipfile.ZipFile(out, "w") as target:
        for name in source.namelist():
            if name not in members:
                target.writestr(name, source.read(name))
        for name, data in members.items():
            if data is not None:
                target.writestr(name, data)
    return out.getvalue()


def member_names(bundle: bytes) -> list[str]:
    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        return sorted(archive.namelist())
