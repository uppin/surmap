# EuRoC V1_01 RTAB-Map fixture (generated)

`euroc_v101_rtabmap/` next to this file is generated data, prepared by
project tooling — never committed, never installed from the host:

    uv run python scripts/fetch_rtabmap_fixture.py

The script pulls the pinned RTAB-Map Docker image by digest and cuts
90 stereo pairs (plus `sensor.yaml` calibrations and the IMU
recording) out of the EuRoC MAV V1_01_easy sequence zip with HTTP
range requests, CRC-verifying every file. Frames are half resolution
(376x240, calibration scaled), starting at zip index 400 where the
MAV is moving. `tests/test_survey_cm5_rtabmap_e2e.py` streams them
through the real CM5 server backed by the real RTAB-Map sidecar.
