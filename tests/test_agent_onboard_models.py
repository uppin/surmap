"""The agent chooses the on-board detector model a run processes its frames with, or none.

`list_onboard_models` names the Coral profiles and which this station has; `run_demo` and
`run_rtabmap` take `onboard_model` — a profile name, `"none"`, or absent for the station
default — and `get_run` reports what a run used. Integration tests over `DemoWorkspace` on the
tiny two-frame scene, with a recording source builder in place of the TFLite runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pytest
from connectrpc.code import Code
from connectrpc.errors import ConnectError
from numpy.typing import NDArray

from surmap.agent.__main__ import config_from_args
from surmap.agent.proto import survey_tools_pb2 as pb
from surmap.agent.server.app import AgentServerConfig, build_demo_workspace
from surmap.agent.tools.handlers import get_run, list_onboard_models, run_demo, run_rtabmap
from surmap.agent.tools.onboard import OnboardModels
from surmap.detection import MODEL_PROFILES, DetectionSource, TrackedDetection
from tests.agent_tool_fakes import TINY_SCENE, a_tool_rig
from tests.test_demo import FakeLiveBackend

EFFICIENTDET = "efficientdet-lite0"
MOBILENET = "ssd-mobilenet-v2"


@dataclass
class RecordingSource:
    """A detection source that finds nothing and remembers the frames it was given."""

    frame_ids: list[int] = field(default_factory=list)

    def detect_tracked(self, frame_id: int, rgb: NDArray[np.uint8]) -> tuple[TrackedDetection, ...]:
        self.frame_ids.append(frame_id)
        return ()


@dataclass
class RecordingBuilder:
    """Builds one `RecordingSource` per run, remembering which model each was built for."""

    built: list[tuple[str, RecordingSource]] = field(default_factory=list)

    def __call__(self, model_dir: Path, model: str) -> DetectionSource:
        source = RecordingSource()
        self.built.append((model, source))
        return source

    @property
    def models(self) -> list[str]:
        return [model for model, _ in self.built]

    def frames_processed_by(self, model: str) -> list[int]:
        return [frame for name, source in self.built if name == model for frame in source.frame_ids]


def a_model_dir(tmp_path: Path, *models: str) -> Path:
    """A prepared Coral model dir holding the CPU twins of `models` and the COCO labels."""
    model_dir = tmp_path / "coral"
    model_dir.mkdir()
    (model_dir / "coco_labels.txt").write_text("person\ncar\n", encoding="utf-8")
    for model in models:
        (model_dir / MODEL_PROFILES[model].cpu_file).write_bytes(b"tflite")
    return model_dir


def a_station(
    tmp_path: Path, builder: RecordingBuilder, *, has: tuple[str, ...], default: str | None
) -> OnboardModels:
    return OnboardModels(a_model_dir(tmp_path, *has), default=default, build=builder)


def a_tiny_run(**fields: object) -> pb.RunDemoRequest:
    request = pb.RunDemoRequest(dataset=TINY_SCENE, fps=50.0)
    for name, value in fields.items():
        setattr(request, name, value)
    return request


def availability(response: pb.ListOnboardModelsResponse) -> dict[str, bool]:
    return {model.name: model.available for model in response.models}


# --- list_onboard_models --------------------------------------------------------------------


async def test_list_onboard_models_offers_every_profile_saying_which_this_station_has(
    tmp_path: Path,
) -> None:
    # Given a station holding only EfficientDet-Lite0's files
    onboard = a_station(tmp_path, RecordingBuilder(), has=(EFFICIENTDET,), default=EFFICIENTDET)
    with a_tool_rig(tmp_path, onboard=onboard) as rig:
        # When the agent lists the on-board models
        response = await list_onboard_models(pb.ListOnboardModelsRequest(), rig.workspace)

    # Then every profile is offered, and only EfficientDet-Lite0 is available
    assert availability(response) == {
        EFFICIENTDET: True,
        MOBILENET: False,
        "ssdlite-mobiledet": False,
    }


async def test_list_onboard_models_names_the_station_default(tmp_path: Path) -> None:
    # Given a station whose default is SSD MobileNet V2
    onboard = a_station(tmp_path, RecordingBuilder(), has=(MOBILENET,), default=MOBILENET)
    with a_tool_rig(tmp_path, onboard=onboard) as rig:
        # When the agent lists the on-board models
        response = await list_onboard_models(pb.ListOnboardModelsRequest(), rig.workspace)

    # Then the default is named, and only that model is marked as it
    assert response.default_model == MOBILENET
    assert [model.name for model in response.models if model.is_default] == [MOBILENET]


async def test_list_onboard_models_says_none_when_the_station_has_no_default(
    tmp_path: Path,
) -> None:
    # Given a station with no on-board model configured
    with a_tool_rig(tmp_path) as rig:
        # When the agent lists the on-board models
        response = await list_onboard_models(pb.ListOnboardModelsRequest(), rig.workspace)

    # Then a run with no choice runs none, and no model is available
    assert response.default_model == "none"
    assert not any(availability(response).values())


# --- run_demo -------------------------------------------------------------------------------


async def test_run_demo_processes_the_frames_with_the_chosen_onboard_model(
    tmp_path: Path,
) -> None:
    # Given a station with both models, defaulting to EfficientDet-Lite0
    builder = RecordingBuilder()
    onboard = a_station(tmp_path, builder, has=(EFFICIENTDET, MOBILENET), default=EFFICIENTDET)
    with a_tool_rig(tmp_path, onboard=onboard) as rig:
        # When the agent runs the tiny scene with SSD MobileNet V2
        response = await run_demo(a_tiny_run(onboard_model=MOBILENET), rig.workspace)

    # Then MobileNet processed both frames, and the run says so
    assert builder.models == [MOBILENET]
    assert builder.frames_processed_by(MOBILENET) == [1, 2]
    assert response.onboard_model == MOBILENET


async def test_run_demo_runs_no_onboard_model_when_the_agent_chooses_none(
    tmp_path: Path,
) -> None:
    # Given a station defaulting to EfficientDet-Lite0
    builder = RecordingBuilder()
    onboard = a_station(tmp_path, builder, has=(EFFICIENTDET,), default=EFFICIENTDET)
    with a_tool_rig(tmp_path, onboard=onboard) as rig:
        # When the agent runs the tiny scene with no on-board model
        response = await run_demo(a_tiny_run(onboard_model="none"), rig.workspace)

    # Then no on-board model was built, the run still played, and it reports none
    assert builder.models == []
    assert (response.status, response.frames) == (pb.RunInfo.FINISHED, 2)
    assert response.onboard_model == ""


async def test_run_demo_uses_the_station_default_when_the_agent_does_not_choose(
    tmp_path: Path,
) -> None:
    # Given a station defaulting to EfficientDet-Lite0
    builder = RecordingBuilder()
    onboard = a_station(tmp_path, builder, has=(EFFICIENTDET,), default=EFFICIENTDET)
    with a_tool_rig(tmp_path, onboard=onboard) as rig:
        # When the agent runs the tiny scene without naming a model
        response = await run_demo(a_tiny_run(), rig.workspace)

    # Then the default processed the frames
    assert builder.frames_processed_by(EFFICIENTDET) == [1, 2]
    assert response.onboard_model == EFFICIENTDET


async def test_each_run_gets_a_fresh_onboard_source(tmp_path: Path) -> None:
    # Given a station defaulting to EfficientDet-Lite0
    builder = RecordingBuilder()
    onboard = a_station(tmp_path, builder, has=(EFFICIENTDET,), default=EFFICIENTDET)
    with a_tool_rig(tmp_path, onboard=onboard) as rig:
        # When the agent runs the scene twice
        await run_demo(a_tiny_run(), rig.workspace)
        await run_demo(a_tiny_run(), rig.workspace)

    # Then each run had its own source, so no tracker state carries between runs
    assert [source.frame_ids for _, source in builder.built] == [[1, 2], [1, 2]]


async def test_run_demo_refuses_an_onboard_model_that_does_not_exist(tmp_path: Path) -> None:
    # Given a station with EfficientDet-Lite0
    builder = RecordingBuilder()
    onboard = a_station(tmp_path, builder, has=(EFFICIENTDET,), default=EFFICIENTDET)
    with a_tool_rig(tmp_path, onboard=onboard) as rig:
        # When the agent asks for a model no profile names
        with pytest.raises(ConnectError) as refused:
            await run_demo(a_tiny_run(onboard_model="yolo-v99"), rig.workspace)

    # Then the call is an invalid argument naming the choices, and nothing ran
    assert refused.value.code == Code.INVALID_ARGUMENT
    assert EFFICIENTDET in refused.value.message
    assert builder.models == []


async def test_run_demo_refuses_an_onboard_model_this_station_lacks(tmp_path: Path) -> None:
    # Given a station holding only EfficientDet-Lite0's files
    builder = RecordingBuilder()
    onboard = a_station(tmp_path, builder, has=(EFFICIENTDET,), default=EFFICIENTDET)
    with a_tool_rig(tmp_path, onboard=onboard) as rig:
        # When the agent asks for SSD MobileNet V2
        with pytest.raises(ConnectError) as refused:
            await run_demo(a_tiny_run(onboard_model=MOBILENET), rig.workspace)

        # Then the call fails its precondition and no run was recorded
        assert refused.value.code == Code.FAILED_PRECONDITION
        assert rig.host.history_store.latest_recording(TINY_SCENE) is None


# --- get_run --------------------------------------------------------------------------------


async def test_get_run_reports_the_onboard_model_a_run_used(tmp_path: Path) -> None:
    # Given a finished run processed by SSD MobileNet V2, looking for boxes
    onboard = a_station(tmp_path, RecordingBuilder(), has=(MOBILENET,), default=None)
    with a_tool_rig(tmp_path, onboard=onboard) as rig:
        played = await run_demo(a_tiny_run(prompt="box", onboard_model=MOBILENET), rig.workspace)

        # When the agent asks about it
        response = await get_run(pb.GetRunRequest(run_id=played.run_id), rig.workspace)

    # Then the run names its on-board model and still its SAM prompt
    assert (response.run.onboard_model, response.run.prompt) == (MOBILENET, "box")


# --- run_rtabmap ----------------------------------------------------------------------------


async def test_run_rtabmap_processes_the_frames_with_the_chosen_onboard_model(
    tmp_path: Path,
) -> None:
    # Given a station with SSD MobileNet V2, no default, and a faked RTAB-Map backend
    builder = RecordingBuilder()
    onboard = a_station(tmp_path, builder, has=(MOBILENET,), default=None)
    with a_tool_rig(tmp_path, onboard=onboard) as rig:
        rig.host.player_options["backend_factory"] = FakeLiveBackend
        # When the agent runs RTAB-Map on the tiny scene with MobileNet on board
        response = await run_rtabmap(
            pb.RunRtabmapRequest(dataset=TINY_SCENE, fps=50.0, onboard_model=MOBILENET),
            rig.workspace,
        )

    # Then MobileNet processed both frames, and the run says so
    assert builder.frames_processed_by(MOBILENET) == [1, 2]
    assert response.run.onboard_model == MOBILENET


# --- OnboardModels --------------------------------------------------------------------------


def test_a_station_default_that_names_no_profile_is_refused(tmp_path: Path) -> None:
    # Given / When / Then a catalogue whose default is not a profile fails at start-up
    with pytest.raises(ValueError, match="yolo-v99"):
        OnboardModels(tmp_path, default="yolo-v99")


# --- what an on-board model can recognise ---------------------------------------------------


async def test_list_onboard_models_names_the_classes_each_model_can_recognise(
    tmp_path: Path,
) -> None:
    # Given a station with no model files at all
    with a_tool_rig(tmp_path) as rig:
        # When the agent lists the on-board models
        response = await list_onboard_models(pb.ListOnboardModelsRequest(), rig.workspace)

    # Then every model names its COCO classes: people and cars, but no buildings or debris
    for model in response.models:
        assert {"person", "car", "truck"} <= set(model.classes)
        assert not {"building", "debris", "fire", "n/a"} & set(model.classes)
        assert len(model.classes) == 80


async def test_run_demo_says_the_onboard_model_recognises_a_coco_concept(tmp_path: Path) -> None:
    # Given a station with EfficientDet-Lite0
    onboard = a_station(tmp_path, RecordingBuilder(), has=(EFFICIENTDET,), default=EFFICIENTDET)
    with a_tool_rig(tmp_path, onboard=onboard) as rig:
        # When the agent runs the scene looking for cars
        response = await run_demo(a_tiny_run(prompt="cars"), rig.workspace)

    # Then the response says the on-board model can recognise them too
    assert response.onboard_recognises_prompt is True


async def test_run_demo_warns_the_onboard_model_cannot_recognise_debris(tmp_path: Path) -> None:
    # Given a station with EfficientDet-Lite0
    onboard = a_station(tmp_path, RecordingBuilder(), has=(EFFICIENTDET,), default=EFFICIENTDET)
    with a_tool_rig(tmp_path, onboard=onboard) as rig:
        # When the agent runs the scene looking for debris
        response = await run_demo(a_tiny_run(prompt="debris"), rig.workspace)

    # Then the response says only SAM can find it: the on-board model has no such class
    assert response.HasField("onboard_recognises_prompt")
    assert response.onboard_recognises_prompt is False


async def test_run_demo_says_nothing_about_recognition_without_an_onboard_model(
    tmp_path: Path,
) -> None:
    # Given a station defaulting to EfficientDet-Lite0
    onboard = a_station(tmp_path, RecordingBuilder(), has=(EFFICIENTDET,), default=EFFICIENTDET)
    with a_tool_rig(tmp_path, onboard=onboard) as rig:
        # When the agent runs the scene looking for cars with no on-board model
        response = await run_demo(a_tiny_run(prompt="car", onboard_model="none"), rig.workspace)

    # Then there is no on-board verdict to give
    assert not response.HasField("onboard_recognises_prompt")


# --- the agent's configuration ------------------------------------------------------------


def test_coral_flags_set_the_onboard_model_dir_and_station_default() -> None:
    # Given a prepared Coral model dir and SSD MobileNet V2 as the station default
    argv = ["--coral-model-dir=/models/coral", "--coral-model=ssd-mobilenet-v2"]

    # When the command line is read
    config = config_from_args(argv, environ={})

    # Then the config carries both
    assert (config.coral_model_dir, config.coral_model) == (
        Path("/models/coral"),
        "ssd-mobilenet-v2",
    )


def test_the_coral_model_dir_comes_from_the_environment_when_no_flag_names_it() -> None:
    # Given the model dir only in the environment
    environ = {"SURMAP_CORAL_MODEL_DIR": "/models/coral"}

    # When the command line is read
    config = config_from_args([], environ=environ)

    # Then the dir is the environment's, and EfficientDet-Lite0 is the default
    assert (config.coral_model_dir, config.coral_model) == (
        Path("/models/coral"),
        "efficientdet-lite0",
    )


def test_the_agent_s_workspace_defaults_runs_to_the_configured_onboard_model(
    tmp_path: Path,
) -> None:
    # Given an agent configured with a Coral model dir and SSD MobileNet V2
    config = AgentServerConfig(
        cache_dir=tmp_path,
        sam_fake=True,
        coral_model_dir=tmp_path / "coral",
        coral_model="ssd-mobilenet-v2",
    )

    # When its workspace is built
    workspace = build_demo_workspace(config)

    # Then a run that names no on-board model uses SSD MobileNet V2
    defaults = [model.name for model in workspace.onboard_models() if model.is_default]
    assert defaults == ["ssd-mobilenet-v2"]


def test_an_agent_told_coral_model_none_runs_no_onboard_model_by_default(tmp_path: Path) -> None:
    # Given an agent with a Coral model dir but `--coral-model none`
    config = config_from_args(
        [
            f"--cache-dir={tmp_path}",
            "--sam-fake",
            f"--coral-model-dir={tmp_path}",
            "--coral-model=none",
        ],
        environ={},
    )

    # When its workspace is built
    workspace = build_demo_workspace(config)

    # Then no model is the default, so a run with no choice runs none
    assert not any(model.is_default for model in workspace.onboard_models())
