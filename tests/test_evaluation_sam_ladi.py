from __future__ import annotations

import pytest

from surmap.evaluation import cli
from surmap.evaluation.ladi import LadiSample
from surmap.evaluation.sam_ladi import SAM_CONCEPTS, ModalSamLadiClassifier
from surmap.survey.sam import SamDetection


def _det(score: float | None) -> SamDetection:
    return SamDetection("x", score, (0.0, 0.0, 1.0, 1.0))


def test_a_class_is_predicted_when_its_prompt_returns_a_confident_detection() -> None:
    calls: list[str] = []

    def segment(prompt: str, jpeg: bytes) -> tuple[SamDetection, ...]:
        calls.append(prompt)
        return {"debris": (_det(0.9),), "bridge": (_det(0.2),), "water": (_det(None),)}.get(
            prompt, ()
        )

    found = ModalSamLadiClassifier(segmenter=segment).classify(b"jpeg")

    assert found == {"debris_any", "water_any"}
    assert sorted(calls) == sorted(SAM_CONCEPTS.values())


def test_cli_scores_modal_only_on_classes_it_has_a_prompt_for(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("SURMAP_LIVE_MODAL", "1")
    monkeypatch.setenv("MODAL_SAM_URL", "https://example.invalid")
    sample = LadiSample("test", 0, b"jpeg", frozenset({"roads_any", "roads_damage"}))

    def loader(*_args: object, **_kwargs: object) -> list[LadiSample]:
        return [sample]

    def factory(_provider: str) -> ModalSamLadiClassifier:
        return ModalSamLadiClassifier(
            segmenter=lambda prompt, _jpeg: (_det(0.8),) if prompt == "road" else ()
        )

    code = cli.main(
        ["--provider", "modal", "--limit", "1"], loader=loader, classifier_factory=factory
    )

    out = capsys.readouterr().out
    assert code == 0
    assert "micro F1: 1.000" in out
    assert "modal sam-3.1" in out


def test_cli_refuses_modal_without_its_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SURMAP_LIVE_MODAL", raising=False)
    with pytest.raises(cli.EvalConfigError):
        cli.check_live(["modal"], 1)
