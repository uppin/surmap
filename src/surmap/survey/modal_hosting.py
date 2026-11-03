"""What the Modal deploy targets run: the simulated CM5 and the station, as web servers.

The app files (`modal_cm5_app.py`, `modal_station_app.py`) import `modal`, which CI does not
install; everything they decide lives here so it is tested directly. Each app runs one survey
main as a `@modal.web_server` on its port, bound to every interface. Modal carries the Connect
WebSocket (`/connect`) on the app's stable HTTPS URL, and `$SURMAP_SURVEY_TOKEN` from the
`surmap-survey` secret guards it.
"""

from __future__ import annotations

CM5_APP_NAME = "surmap-cm5-sim"
STATION_APP_NAME = "surmap-station"

CM5_PORT = 8080
STATION_PORT = 8081

# Modal secret holding SURMAP_SURVEY_TOKEN, read by both apps.
SURVEY_SECRET = "surmap-survey"

# Where the CM5 image builds RTAB-Map and its stream tool (scripts/build_rtabmap_native.sh).
RTABMAP_WORK = "/opt/surmap-rtabmap"
RTABMAP_BINARY = f"{RTABMAP_WORK}/stream-build/surmap-rtabmap-stream"

# Where the station image keeps the SAM 3.1 checkpoint cache (a Modal Volume).
MODEL_MOUNT = "/models"


def cm5_command(rtabmap_binary: str = RTABMAP_BINARY) -> list[str]:
    """The simulated drone: live RTAB-Map run natively, region points on, no Coral.

    No `--calibration-dir`: the simulator sends each stream's camera definitions in its config.
    """
    return [
        "python",
        "-m",
        "surmap.survey.cm5_main",
        "--host",
        "0.0.0.0",
        "--port",
        str(CM5_PORT),
        "--slam-backend",
        "streaming",
        "--rtabmap-native",
        rtabmap_binary,
        "--region-points",
        "--detector",
        "none",
    ]


def station_command(label: str = "object") -> list[str]:
    """The station: SAM 3.1 (PyTorch) on the container's GPU, prompting `label`."""
    return [
        "python",
        "-m",
        "surmap.survey.station_main",
        "--host",
        "0.0.0.0",
        "--port",
        str(STATION_PORT),
        "--detector",
        "sam31-torch",
        "--sam31-device",
        "cuda:0",
        "--sam31-label",
        label,
    ]
