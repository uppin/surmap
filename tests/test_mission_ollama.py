"""Mission service selection for the fully local Ollama path."""

import pytest

from surmap.mission.demo import _live_segmenter, build_live_services


def test_ollama_selects_local_services_without_any_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given no hosted-service flags or keys at all
    for name in (
        "SURMAP_LIVE_META",
        "SURMAP_LIVE_BASETEN",
        "SURMAP_LIVE_MODAL",
        "MODEL_API_KEY",
        "BASETEN_API_KEY",
        "MODAL_SAM_URL",
    ):
        monkeypatch.delenv(name, raising=False)

    # When the operator asks for the local Ollama stack
    monkeypatch.setenv("SURMAP_LIVE_OLLAMA", "1")
    services = build_live_services()

    # Then segmentation, labels, and the scene note are all local
    assert services.sam == "ollama"
    assert services.labels == "ollama"
    assert services.scene_note == "ollama"


def test_the_segmenter_uses_the_model_the_operator_chose() -> None:
    # Given an operator-chosen Ollama model name, Gemma or any other
    segmenter = _live_segmenter("ollama", model="minicpm-v:8b")

    # Then the segmenter records that exact model, not a built-in one
    assert segmenter.model_id == "ollama:minicpm-v:8b"
