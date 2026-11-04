"""Real Coral COCO detectors on the Bevy simulation's detector capture.

`tests/fixtures/bevy_sim_detector_capture/` is a native recording of the shipped scene
(`--record … --frames 75 --rate-hz 1 --start 12 --jpeg --colour`: the survey loop's east side
past the cars, then the north-east corner past the survivors), carrying only its colour left
frames. The CPU twins of the Coral profiles run over it and every ground-truth car and person is
projected into each frame (`surmap.simulation.detection_eval`). The floors sit under the hit
rates measured when the capture was recorded (docs/simulation/bevy-simulation.md § *On-board
detectors*), so a regression in the simulation's realism — a car under a tarp again, a capsule
person, grey frames — fails here.

Prepared by tooling:

    uv run python scripts/fetch_coral_model.py

Without the models this skips (fails when `SURMAP_REQUIRE_CORAL_E2E=1`, as CI sets).
"""

import os
import pathlib

import pytest

from surmap.detection import MODEL_PROFILES, CoralDetector
from surmap.simulation.bevy_capture import BevyCapture, load_bevy_capture
from surmap.simulation.detection_eval import DetectionReport, detect_capture, score_capture

ROOT = pathlib.Path(__file__).parent / "fixtures"
MODEL_DIR = ROOT / "coral_model"
CAPTURE = ROOT / "bevy_sim_detector_capture"
REQUIRED = os.environ.get("SURMAP_REQUIRE_CORAL_E2E") == "1"


def _require_models() -> None:
    if not (MODEL_DIR / "manifest.json").is_file():
        message = "Coral models not prepared: run `uv run python scripts/fetch_coral_model.py`"
        if REQUIRED:
            pytest.fail(message)
        pytest.skip(message)


@pytest.fixture(scope="module")
def capture() -> BevyCapture:
    return load_bevy_capture(CAPTURE)


def scored(capture: BevyCapture, profile: str) -> DetectionReport:
    _require_models()
    model = MODEL_PROFILES[profile]
    detector = CoralDetector(
        MODEL_DIR / model.cpu_file, MODEL_DIR / "coco_labels.txt", score_threshold=0.3
    )
    return score_capture(capture, detect_capture(capture, detector))


def test_the_detector_capture_is_colour_with_cars_and_people_in_view(
    capture: BevyCapture,
) -> None:
    # Given the recorded detector capture
    kinds = {obj.kind for obj in capture.objects}

    # Then every frame has a colour image and the ground truth holds cars and people
    assert all(frame.left_rgb_ref for frame in capture.frames)
    assert {"car", "person"} <= kinds


def test_the_default_profile_finds_the_simulations_cars(capture: BevyCapture) -> None:
    # When the default on-board detector runs over the capture at score 0.3
    report = scored(capture, "efficientdet-lite0")

    # Then it finds the cars in at least a tenth of the frames they are in view
    car = report.kinds["car"]
    assert car.visible > 0
    assert car.hit_rate >= 0.10, f"{car.found}/{car.visible}"


def test_an_on_board_profile_finds_the_simulations_cars_and_survivors(
    capture: BevyCapture,
) -> None:
    # When SSDLite MobileDet runs over the capture at score 0.3
    report = scored(capture, "ssdlite-mobiledet")

    # Then it finds cars and survivors in at least a quarter of the frames they are in view
    car, person = report.kinds["car"], report.kinds["person"]
    assert car.hit_rate >= 0.25, f"cars {car.found}/{car.visible}"
    assert person.hit_rate >= 0.25, f"people {person.found}/{person.visible}"
