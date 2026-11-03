"""Agent dataset tools: catalogue, prepare, RTAB-Map-only and SAM-only runs."""

from __future__ import annotations

from pathlib import Path

import pytest
from connectrpc.errors import ConnectError

from surmap.agent.proto import survey_tools_pb2 as pb
from surmap.agent.tools.handlers import (
    get_dataset,
    list_datasets,
    prepare_dataset,
    run_rtabmap,
    run_sam_on_dataset,
)
from tests.agent_tool_fakes import a_tool_rig


def test_list_datasets_reports_licence_modality_and_prepared_state(tmp_path: Path) -> None:
    # Given a station offering the tiny scene
    with a_tool_rig(tmp_path) as rig:
        import asyncio

        # When the agent lists the dataset gallery
        response = asyncio.run(list_datasets(pb.ListDatasetsRequest(), rig.workspace))

    # Then the scene appears as a dataset with licence/modality/prepared metadata
    (entry,) = [d for d in response.datasets if d.id == rig.prepared.spec.dataset_id]
    assert entry.title == rig.prepared.spec.title
    assert entry.prepared is True
    assert entry.modality != pb.MODALITY_UNSPECIFIED
    assert entry.HasField("license")


def test_get_dataset_refuses_an_unknown_dataset(tmp_path: Path) -> None:
    # Given a station
    with a_tool_rig(tmp_path) as rig:
        import asyncio

        # When / Then an unknown dataset is refused as NOT_FOUND
        with pytest.raises(ConnectError):
            asyncio.run(get_dataset(pb.GetDatasetRequest(dataset_id="nope"), rig.workspace))


def test_run_sam_on_dataset_segments_frames_without_a_run(tmp_path: Path) -> None:
    # Given a prepared scene and no recorded run of it
    with a_tool_rig(tmp_path) as rig:
        import asyncio

        # When SAM runs directly on the dataset for "box"
        response = asyncio.run(
            run_sam_on_dataset(
                pb.RunSamOnDatasetRequest(
                    dataset=rig.prepared.spec.dataset_id, concept="box", max_frames=2
                ),
                rig.workspace,
            )
        )

    # Then frames come back with detections, and no run was needed
    assert response.dataset_id == rig.prepared.spec.dataset_id
    assert len(response.frames) == 2
    assert all(frame.detections for frame in response.frames)


def test_run_rtabmap_records_a_run_without_sam(tmp_path: Path) -> None:
    # Given a station whose RTAB-Map backend is faked through the host options
    from tests.test_demo import FakeLiveBackend

    with a_tool_rig(tmp_path) as rig:
        rig.host.player_options["backend_factory"] = lambda: FakeLiveBackend()
        import asyncio

        # When RTAB-Map alone runs the dataset
        response = asyncio.run(
            run_rtabmap(
                pb.RunRtabmapRequest(dataset=rig.prepared.spec.dataset_id, max_frames=2),
                rig.workspace,
            )
        )

        # Then a finished run is recorded and can be described
        assert response.run.run_id != ""
        assert response.run.status == pb.RunInfo.FINISHED
        assert rig.workspace.run(response.run.run_id) is not None


def test_prepare_dataset_answers_with_the_prepared_entry(tmp_path: Path) -> None:
    # Given a station with the tiny scene already cached
    with a_tool_rig(tmp_path) as rig:
        import asyncio

        # When the agent prepares it
        response = asyncio.run(
            prepare_dataset(
                pb.PrepareDatasetRequest(dataset_id=rig.prepared.spec.dataset_id), rig.workspace
            )
        )

    # Then the entry reports prepared with its frame count
    assert response.dataset.prepared is True
    assert response.dataset.frame_count == len(rig.prepared.timestamps_ns)
