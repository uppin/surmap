# Coral detection model fixture (generated)

`coral_model/` next to this file is generated data, prepared by
project tooling — never committed:

    uv run python scripts/fetch_coral_model.py

It holds the pinned EfficientDet-Lite0 INT8 artifacts (Edge-TPU
compiled + CPU twin) and COCO labels; see
`docs/coral-edge-tpu-model-spike.md` for why the detector is
Coral-native. `tests/test_survey_cm5_coral_e2e.py` runs the CPU twin
through the real CM5 server (separate detections stream + object
points) against the EuRoC fixture.
