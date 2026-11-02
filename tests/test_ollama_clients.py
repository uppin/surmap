"""Local Ollama adapters behind the label, scene-note, and SAM ports."""

from collections.abc import Mapping

import pytest

from surmap.labelling.ollama import OllamaError, OllamaLabelClient, OllamaSceneClient
from surmap.survey.ollama_box import OllamaBoxDetector
from surmap.survey.sam import RawFrame
from surmap.types import Vec3

_JPEG = b"\xff\xd8fake-jpeg\xff\xd9"
_POINT = Vec3(1.0, 2.0, 3.0)


class RecordingTransport:
    """In-memory Ollama transport: records requests, returns a canned reply."""

    def __init__(self, content: str) -> None:
        self.content = content
        self.urls: list[str] = []
        self.bodies: list[Mapping[str, object]] = []

    def post_json(self, url: str, body: Mapping[str, object]) -> Mapping[str, object]:
        self.urls.append(url)
        self.bodies.append(body)
        return {"message": {"role": "assistant", "content": self.content}}


def a_frame() -> RawFrame:
    return RawFrame(7, 1_000, 0, 640, 480, "jpeg", _JPEG)


def test_the_label_client_names_the_crop_from_the_local_model() -> None:
    # Given a local model that calls the crop a survivor
    transport = RecordingTransport("survivor\nA person in orange awaiting rescue.")

    # When the crop is labelled
    labelled = OllamaLabelClient(model="gemma4:e4b-mlx", transport=transport).label(
        _JPEG, "person", _POINT
    )

    # Then the first line is the map label, the point is attached, the
    # model id names the local adapter, and the image went to /api/chat
    assert labelled.label == "survivor"
    assert labelled.map_point == _POINT
    assert labelled.model_id == "ollama:gemma4:e4b-mlx"
    assert transport.urls == ["http://127.0.0.1:11434/api/chat"]
    message = transport.bodies[0]["messages"]
    assert isinstance(message, list)


def test_the_scene_client_returns_the_local_models_note() -> None:
    # Given a local model describing the mapped area
    transport = RecordingTransport("Rubble and a flooded street; no flight advice.")

    # When a scene note is requested for two labels
    note = OllamaSceneClient(model="gemma4:e4b-mlx", transport=transport).note(
        ["survivor", "vehicle"], _JPEG
    )

    # Then the note is the model's text, verbatim
    assert note == "Rubble and a flooded street; no flight advice."


def test_any_configured_model_is_used_and_an_unconfigured_one_fails_by_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given the operator configured a different local vision model
    monkeypatch.setenv("SURMAP_OLLAMA_MODEL", "llava:13b")
    transport = RecordingTransport("survivor")

    # When a label is requested without naming a model in code
    labelled = OllamaLabelClient(transport=transport).label(_JPEG, "person", _POINT)

    # Then that configured model is the one recorded on the label
    assert labelled.model_id == "ollama:llava:13b"
    body_model = transport.bodies[0]["model"]
    assert body_model == "llava:13b"

    # And with nothing configured, construction fails and names the option
    monkeypatch.delenv("SURMAP_OLLAMA_MODEL")
    with pytest.raises(OllamaError, match="SURMAP_OLLAMA_MODEL"):
        OllamaLabelClient(transport=transport)


def test_an_empty_local_reply_fails_by_name() -> None:
    # Given a local model that replies with nothing
    transport = RecordingTransport("  ")

    # When a label is requested
    # Then the failure names the local adapter instead of inventing a label
    with pytest.raises(OllamaError, match="Ollama"):
        OllamaLabelClient(model="any-vision:1", transport=transport).label(_JPEG, "person", _POINT)


def test_the_box_detector_scales_normalised_boxes_to_frame_pixels() -> None:
    # Given a local model reporting one person box in 0-1000 coordinates
    transport = RecordingTransport('[{"x_min": 100, "y_min": 200, "x_max": 300, "y_max": 600}]')
    detector = OllamaBoxDetector(prompt="person", model="any-vision:1", transport=transport)

    # When the frame is analysed
    found = detector.detect(a_frame())

    # Then the detection carries pixel box and rectangle mask in frame pixels
    assert len(found) == 1
    assert found[0].label == "person"
    assert found[0].box_xyxy == (64.0, 96.0, 192.0, 288.0)
    assert found[0].mask_polygon == ((64.0, 96.0), (192.0, 96.0), (192.0, 288.0), (64.0, 288.0))


def test_the_box_detector_accepts_an_empty_array_as_no_detections() -> None:
    # Given a frame with nobody in it
    detector = OllamaBoxDetector(
        prompt="person", model="any-vision:1", transport=RecordingTransport("[]")
    )

    # When the frame is analysed
    # Then nothing is claimed
    assert detector.detect(a_frame()) == ()


def test_unparsable_box_output_fails_by_name() -> None:
    # Given a reply that is not the JSON array the prompt requires
    detector = OllamaBoxDetector(
        prompt="person", model="any-vision:1", transport=RecordingTransport("I see rubble.")
    )

    # When the frame is analysed
    # Then the failure names the adapter instead of guessing boxes
    with pytest.raises(OllamaError, match="Ollama"):
        detector.detect(a_frame())
