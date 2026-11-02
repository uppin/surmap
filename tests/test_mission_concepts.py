"""Muse Wonder chooses the concepts SAM 3.1 segments in the live mission."""

from pathlib import Path

import pytest

from surmap.labelling.baseten_muse import ObjectLabel
from surmap.labelling.meta_muse import (
    MetaMuseConceptClient,
    MetaMuseLabelClient,
    MetaMuseSceneClient,
    MetaMuseSceneError,
)
from surmap.mission import demo
from surmap.mission.demo import MissionConfigError, live_max_concepts, run_live_mission
from surmap.slam.base import FrameResult
from surmap.survey.meta_sam import MetaSamDetector
from surmap.survey.sam import RawFrame, SamDetection
from surmap.types import Pose, StereoFramePair, Vec3

_CAPTURE = Path(__file__).parent / "fixtures" / "sitl_capture_tiny"


class _Map:
    def __init__(self) -> None:
        self.frames: list[StereoFramePair] = []

    def process_frame(self, frame: StereoFramePair) -> FrameResult:
        self.frames.append(frame)
        return FrameResult(frame.frame_id, frame.t_ns, None, ())

    def flush(self) -> list[FrameResult]:
        pose = Pose(Vec3(0.0, 0.0, 0.0))
        return [FrameResult(frame.frame_id, frame.t_ns, pose, ()) for frame in self.frames]

    def map_snapshot(self) -> tuple[Vec3, ...]:
        return (Vec3(0.0, 0.0, 2.0),)

    def close(self) -> None:
        return None


@pytest.fixture
def mission(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[str]]:
    """Live Meta flags, fake SAM/labels/note, and a log of what was asked."""
    monkeypatch.setenv("SURMAP_LIVE_META", "1")
    monkeypatch.setenv("MODEL_API_KEY", "k")
    for name in (
        "SURMAP_LIVE_BASETEN",
        "SURMAP_LIVE_MODAL",
        "SURMAP_SAM_PROMPT",
        "SURMAP_SAM_MAX_CONCEPTS",
        "SURMAP_CONCEPT_EVERY",
    ):
        monkeypatch.delenv(name, raising=False)
    log: dict[str, list[str]] = {"sam": [], "proposals": []}

    async def detect(self: MetaSamDetector, frame: RawFrame) -> tuple[SamDetection, ...]:
        del frame
        log["sam"].append(self._prompt)
        return ()

    def propose(self: MetaMuseConceptClient, frame_jpeg: bytes) -> tuple[str, ...]:
        assert frame_jpeg.startswith(b"\xff\xd8")
        log["proposals"].append(str(self.max_concepts))
        return ("person", "collapsed building", "flooded road", "vehicle")[: self.max_concepts]

    def label(self: object, jpeg: bytes, coarse_label: str, xyz: Vec3) -> ObjectLabel:
        del self, jpeg
        return ObjectLabel(
            label=coarse_label,
            description=coarse_label,
            confidence=None,
            model_id="muse-wonder-1.0",
            raw_text=coarse_label,
            map_point=xyz,
        )

    def note(self: object, labels: list[str], frame_jpeg: bytes, **kwargs: object) -> str:
        del self, labels, frame_jpeg, kwargs
        return "note"

    monkeypatch.setattr(demo, "open_live_map", lambda _calibration, **_kwargs: _Map())
    monkeypatch.setattr(MetaSamDetector, "detect", detect)
    monkeypatch.setattr(MetaMuseConceptClient, "propose", propose)
    monkeypatch.setattr(MetaMuseLabelClient, "label", label)
    monkeypatch.setattr(MetaMuseSceneClient, "note", note)
    return log


def test_each_concept_muse_spark_proposes_is_sent_to_sam(
    tmp_path: Path, mission: dict[str, list[str]]
) -> None:
    run_live_mission(tmp_path, _CAPTURE)
    # One proposal for the two-frame capture (every 10 frames), four SAM calls per frame
    assert len(mission["proposals"]) == 1
    expected = ["person", "collapsed building", "flooded road", "vehicle"]
    assert mission["sam"] == expected * 2


def test_the_concept_count_is_capped(
    tmp_path: Path, mission: dict[str, list[str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SURMAP_SAM_MAX_CONCEPTS", "2")
    run_live_mission(tmp_path, _CAPTURE)
    assert mission["sam"] == ["person", "collapsed building"] * 2


def test_surmap_sam_prompt_still_wins(
    tmp_path: Path, mission: dict[str, list[str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SURMAP_SAM_PROMPT", "rubble")
    run_live_mission(tmp_path, _CAPTURE)
    assert mission["proposals"] == []
    assert mission["sam"] == ["rubble", "rubble"]


def test_concepts_are_refreshed_every_n_posed_frames(
    tmp_path: Path, mission: dict[str, list[str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SURMAP_CONCEPT_EVERY", "1")
    run_live_mission(tmp_path, _CAPTURE)
    assert len(mission["proposals"]) == 2


def test_an_unusable_reply_keeps_the_previous_concepts(
    tmp_path: Path, mission: dict[str, list[str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(self: MetaMuseConceptClient, frame_jpeg: bytes) -> tuple[str, ...]:
        del self, frame_jpeg
        raise MetaMuseSceneError("concept reply was not JSON")

    monkeypatch.setattr(MetaMuseConceptClient, "propose", broken)
    run_live_mission(tmp_path, _CAPTURE)
    assert mission["sam"] == ["person", "person"]


def test_without_the_meta_flag_no_concepts_are_requested(
    tmp_path: Path, mission: dict[str, list[str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Modal SAM and Baseten labels only: SAM keeps the single default concept
    monkeypatch.delenv("SURMAP_LIVE_META")
    monkeypatch.setenv("SURMAP_LIVE_MODAL", "1")
    monkeypatch.setenv("MODAL_SAM_URL", "https://example.invalid/sam")
    monkeypatch.setenv("SURMAP_LIVE_BASETEN", "1")
    monkeypatch.setenv("BASETEN_API_KEY", "b")
    asked: list[str] = []

    async def modal_detect(self: object, frame: RawFrame) -> tuple[SamDetection, ...]:
        del frame
        asked.append(str(getattr(self, "prompt", "")))
        return ()

    monkeypatch.setattr("surmap.survey.modal_sam.ModalSamDetector.detect", modal_detect)
    run_live_mission(tmp_path, _CAPTURE)
    assert mission["proposals"] == []
    assert asked == ["person", "person"]


@pytest.mark.parametrize("raw", ["0", "9", "many"])
def test_a_bad_concept_cap_is_refused(monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
    monkeypatch.setenv("SURMAP_SAM_MAX_CONCEPTS", raw)
    with pytest.raises(MissionConfigError):
        live_max_concepts()
