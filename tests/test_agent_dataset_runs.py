"""Dataset runs: builds cached by cache key, listed and run again without RTAB-Map or SAM."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from connectrpc.errors import ConnectError

from surmap.agent.proto import survey_tools_pb2 as pb
from surmap.agent.tools.handlers import (
    get_dataset,
    list_runs,
    run_cached,
    run_demo,
    run_rtabmap,
    survey_tool_handlers,
)
from tests.agent_tool_fakes import TINY_SCENE, ToolRig, a_tool_rig
from tests.test_demo import FakeLiveBackend


def a_demo_build(prompt: str = "box", **fields: object) -> pb.RunDemoRequest:
    """A fast RTAB-Map + SAM build of the tiny scene; `fields` override the request."""
    request = pb.RunDemoRequest(dataset=TINY_SCENE, prompt=prompt, fps=50.0)
    for name, value in fields.items():
        setattr(request, name, value)
    return request


def an_rtabmap_build() -> pb.RunRtabmapRequest:
    return pb.RunRtabmapRequest(dataset=TINY_SCENE, fps=50.0)


@contextmanager
def a_rig_with_fake_rtabmap(tmp_path: Path) -> Iterator[ToolRig]:
    """`a_tool_rig` whose RTAB-Map backend is the fake live backend."""
    with a_tool_rig(tmp_path) as rig:
        rig.host.player_options["backend_factory"] = lambda: FakeLiveBackend()
        yield rig


def recorded_runs(rig: ToolRig) -> int:
    return len(rig.host.history_store.list_runs())


async def runs_of(rig: ToolRig) -> list[pb.CachedRun]:
    return list((await list_runs(pb.ListRunsRequest(dataset=TINY_SCENE), rig.workspace)).runs)


# --- building caches by key -----------------------------------------------------------------


async def test_a_repeated_build_answers_from_its_cached_run(tmp_path: Path) -> None:
    # Given a dataset already built with RTAB-Map and SAM looking for boxes
    with a_tool_rig(tmp_path) as rig:
        first = await run_demo(a_demo_build(), rig.workspace)

        # When the agent asks for the same build again
        again = await run_demo(a_demo_build(), rig.workspace)

        # Then it answers from the cached run and records nothing new
        assert (again.run_id, again.cached, first.cached) == (first.run_id, True, False)
        assert recorded_runs(rig) == 1


async def test_a_build_with_another_key_records_its_own_run(tmp_path: Path) -> None:
    # Given a dataset built looking for boxes
    with a_tool_rig(tmp_path) as rig:
        boxes = await run_demo(a_demo_build("box"), rig.workspace)

        # When the agent builds it looking for cars
        cars = await run_demo(a_demo_build("car"), rig.workspace)

        # Then that is a new build, and both runs stay cached under their own keys
        assert cars.run_id != boxes.run_id and not cars.cached
        assert {run.run_id for run in await runs_of(rig)} == {boxes.run_id, cars.run_id}


async def test_rebuild_records_a_new_run_that_becomes_the_cached_one(tmp_path: Path) -> None:
    # Given a dataset already built
    with a_tool_rig(tmp_path) as rig:
        first = await run_demo(a_demo_build(), rig.workspace)

        # When the agent rebuilds the same key
        rebuilt = await run_demo(a_demo_build(rebuild=True), rig.workspace)

        # Then a new run is recorded and replaces the old one under that key
        assert rebuilt.run_id != first.run_id and not rebuilt.cached
        assert [run.run_id for run in await runs_of(rig)] == [rebuilt.run_id]


async def test_a_frame_limit_is_part_of_the_cache_key(tmp_path: Path) -> None:
    # Given a dataset built on its first frame only
    with a_tool_rig(tmp_path) as rig:
        short = await run_demo(a_demo_build(max_frames=1), rig.workspace)

        # When the agent builds the whole dataset
        whole = await run_demo(a_demo_build(), rig.workspace)

        # Then the short run is not mistaken for the whole one
        assert whole.run_id != short.run_id and whole.frames == 2


async def test_an_rtabmap_build_is_cached_apart_from_a_sam_build(tmp_path: Path) -> None:
    # Given a dataset built with RTAB-Map and SAM
    with a_rig_with_fake_rtabmap(tmp_path) as rig:
        both = await run_demo(a_demo_build(), rig.workspace)

        # When RTAB-Map alone builds it, twice
        first = await run_rtabmap(an_rtabmap_build(), rig.workspace)
        again = await run_rtabmap(an_rtabmap_build(), rig.workspace)

        # Then RTAB-Map has its own cached run, reused the second time
        assert first.run.run_id != both.run_id and not first.run.cached
        assert (again.run.run_id, again.run.cached) == (first.run.run_id, True)


# --- list_runs and run_cached ---------------------------------------------------------------


async def test_list_runs_names_each_cache_key_with_a_preview_frame(tmp_path: Path) -> None:
    # Given a dataset built looking for boxes, on its first frame only
    with a_tool_rig(tmp_path) as rig:
        built = await run_demo(a_demo_build(max_frames=1), rig.workspace)

        # When the agent lists the dataset's runs
        (run,) = await runs_of(rig)

    # Then the run names what it was built with and a frame to preview it by
    assert run.run_id == built.run_id
    assert run.cache_key == "rtabmap+sam=box;frames=1"
    assert (run.frames, run.preview_frame_id > 0, run.created_at > 0) == (1, True, True)


async def test_list_runs_is_empty_before_the_first_build(tmp_path: Path) -> None:
    # Given a dataset never built
    with a_tool_rig(tmp_path) as rig:
        # When / Then it has no runs
        assert await runs_of(rig) == []


async def test_list_runs_refuses_an_unknown_dataset(tmp_path: Path) -> None:
    with a_tool_rig(tmp_path) as rig:
        with pytest.raises(ConnectError):
            await list_runs(pb.ListRunsRequest(dataset="atlantis"), rig.workspace)


async def test_run_cached_answers_from_the_recording_without_a_new_run(tmp_path: Path) -> None:
    # Given a cached run of the dataset
    with a_tool_rig(tmp_path) as rig:
        built = await run_demo(a_demo_build(), rig.workspace)

        # When the agent runs that cached run
        response = await run_cached(pb.RunCachedRequest(run_id=built.run_id), rig.workspace)

        # Then it describes the run, marked cached, and nothing new is recorded
        assert (response.run.run_id, response.run.cached) == (built.run_id, True)
        assert (response.run.frames, response.run.prompt) == (2, "box")
        assert recorded_runs(rig) == 1


async def test_run_cached_refuses_a_run_that_is_not_cached(tmp_path: Path) -> None:
    with a_tool_rig(tmp_path) as rig:
        with pytest.raises(ConnectError):
            await run_cached(pb.RunCachedRequest(run_id="nope"), rig.workspace)


async def test_the_dataset_entry_carries_its_runs(tmp_path: Path) -> None:
    # Given a dataset built once
    with a_tool_rig(tmp_path) as rig:
        built = await run_demo(a_demo_build(), rig.workspace)

        # When the agent reads the dataset
        response = await get_dataset(pb.GetDatasetRequest(dataset_id=TINY_SCENE), rig.workspace)

    # Then its entry lists that run
    assert [run.run_id for run in response.dataset.runs] == [built.run_id]


def test_list_runs_and_run_cached_are_survey_tools(tmp_path: Path) -> None:
    with a_tool_rig(tmp_path) as rig:
        assert {"ListRuns", "RunCached"} <= set(survey_tool_handlers(rig.workspace))
