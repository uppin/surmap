"""What the Modal deploy targets run: the CM5, the station and the agent, as web servers.

The app files (`modal_cm5_app.py`, `modal_station_app.py`) import `modal`, which CI does not
install; everything they decide lives here so it is tested directly. Each app runs one survey
main as a `@modal.web_server` on its port, bound to every interface. Modal carries the Connect
WebSocket (`/connect`) on the app's stable HTTPS URL, and `$SURMAP_SURVEY_TOKEN` from the
`surmap-survey` secret guards it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from surmap.simulation.sim_assets import load_asset_pins

AGENT_APP_NAME = "surmap-agent"
CM5_APP_NAME = "surmap-cm5-sim"
STATION_APP_NAME = "surmap-station"

CM5_PORT = 8080
STATION_PORT = 8081

# Modal secret holding SURMAP_SURVEY_TOKEN, read by every app.
SURVEY_SECRET = "surmap-survey"

# The survey agent and its chat page: one CPU web server. Its secret holds MODEL_API_KEY and
# SURMAP_AGENT_ACCESS_CODE; the built page and the demo cache (a Volume) sit at these paths.
AGENT_PORT = 8780
AGENT_SECRET = "surmap-agent"
AGENT_WEB_DIST = "/opt/surmap/web"
AGENT_CACHE = "/cache"
# The agent's persisted state, all under the cache mount (Volume `surmap-agent-cache`), so a
# container restart keeps it: the demo run history, the chat conversations, the simulation
# store (`simulation.sqlite` + `library/`). The map scenes, tool outputs and usage log join
# them via `--cache-dir`, which is also the agent's state dir.
AGENT_HISTORY_DB = f"{AGENT_CACHE}/demo-history.db"
AGENT_CONVERSATIONS_DB = f"{AGENT_CACHE}/conversations.sqlite"
AGENT_SIM_DIR = f"{AGENT_CACHE}/simulation"
# The Bevy simulation the agent serves, baked into the image: the PoC's `assets/` (with its
# fetched pinned files) and its `trunk build` output, at /sim/.
AGENT_SIM_ASSETS = "/opt/surmap/sim/assets"
AGENT_SIM_PAGE = "/opt/surmap/sim/dist"

# Where the CM5 image builds RTAB-Map and its stream tool (scripts/build_rtabmap_native.sh).
RTABMAP_WORK = "/opt/surmap-rtabmap"
RTABMAP_BINARY = f"{RTABMAP_WORK}/stream-build/surmap-rtabmap-stream"

# Where the station image keeps the SAM 3.1 checkpoint cache (a Modal Volume).
MODEL_MOUNT = "/models"

# Meta's SAM 3.1 package. It declares numpy<2 but runs on surmap's numpy pin, so the image
# installs it without dependency resolution, after the pyproject, with the rest of what it
# declares (SAM3_RUNTIME_PACKAGES) installed beforehand.
SAM3_PACKAGE = "sam3 @ git+https://github.com/facebookresearch/sam3.git"
SAM3_RUNTIME_PACKAGES = (
    "timm>=1.0.17",
    "tqdm",
    "ftfy==6.1.1",
    "regex",
    "iopath>=0.1.10",
    "typing_extensions",
    "huggingface_hub",
)

# Station settings, read where the app is deployed (see StationSettings).
GPU_ENV = "SURMAP_MODAL_GPU"
TIMEOUT_ENV = "SURMAP_MODAL_TIMEOUT"
SCALEDOWN_ENV = "SURMAP_MODAL_SCALEDOWN_WINDOW"
LABEL_ENV = "SURMAP_STATION_LABEL"

# Modal tries these in order, so a busy L4 pool falls through to an A10G (both 24 GB).
DEFAULT_STATION_GPUS = ("L4", "A10G")


@dataclass(frozen=True)
class StationSettings:
    """What the station app is deployed with.

    Modal imports the app file twice: where it is deployed, and again inside the container.
    Decorator arguments (`gpus`, `timeout_s`, `scaledown_s`) take effect at deploy time; the
    `label` is used inside the container, so it has to travel there: `container_env()` is the
    env the app hands the container, from which `from_env` reads the same settings back.
    """

    gpus: list[str]
    timeout_s: int
    scaledown_s: int
    label: str

    @classmethod
    def from_env(cls, environ: Mapping[str, str]) -> StationSettings:
        gpus = [gpu.strip() for gpu in environ.get(GPU_ENV, "").split(",") if gpu.strip()]
        return cls(
            gpus=gpus or list(DEFAULT_STATION_GPUS),
            timeout_s=int(environ.get(TIMEOUT_ENV, "86400")),
            scaledown_s=int(environ.get(SCALEDOWN_ENV, "300")),
            label=environ.get(LABEL_ENV, "").strip() or "object",
        )

    def container_env(self) -> dict[str, str]:
        return {
            GPU_ENV: ",".join(self.gpus),
            TIMEOUT_ENV: str(self.timeout_s),
            SCALEDOWN_ENV: str(self.scaledown_s),
            LABEL_ENV: self.label,
        }


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


def agent_command() -> list[str]:
    """The survey agent behind its pass code, serving the chat page, its SAM on the station app."""
    return [
        "python",
        "-m",
        "surmap.agent",
        "--host",
        "0.0.0.0",
        "--port",
        str(AGENT_PORT),
        "--station",
        "modal",
        "--web-dist",
        AGENT_WEB_DIST,
        "--cache-dir",
        AGENT_CACHE,
        "--history-db",
        AGENT_HISTORY_DB,
        "--conversations-db",
        AGENT_CONVERSATIONS_DB,
        "--sim-dir",
        AGENT_SIM_DIR,
        "--sim-assets",
        AGENT_SIM_ASSETS,
        "--sim-dist",
        AGENT_SIM_PAGE,
    ]


class SimBundleError(RuntimeError):
    """The simulation the agent's deploy would ship is missing or stale."""


# What `trunk build` compiles into the page: a change to any of them means a rebuild.
_SIM_PAGE_SOURCES = ("index.html", "Cargo.toml", "Cargo.lock")


def check_sim_bundle(poc_dir: Path) -> None:
    """Refuse to deploy the PoC at `poc_dir` unless its `dist/` is a build newer than every page
    source and every asset pinned in `assets/assets.lock.json` is on disk."""
    dist = poc_dir / "dist"
    wasm = sorted(dist.glob("*.wasm"), key=lambda path: path.stat().st_mtime)
    if not (dist / "index.html").is_file() or not wasm:
        raise SimBundleError(
            f"no simulation page in {dist}; build it: "
            f"(cd {poc_dir} && trunk build index.html --release)"
        )
    built_at = wasm[-1].stat().st_mtime
    sources = [poc_dir / name for name in _SIM_PAGE_SOURCES]
    sources += [path for path in (poc_dir / "src").rglob("*") if path.is_file()]
    newer = [path for path in sources if path.is_file() and path.stat().st_mtime > built_at]
    if newer:
        newest = max(newer, key=lambda path: path.stat().st_mtime)
        raise SimBundleError(
            f"the simulation page in {dist} is older than {newest.relative_to(poc_dir)}; "
            f"rebuild it: (cd {poc_dir} && trunk build index.html --release)"
        )
    assets = poc_dir / "assets"
    missing = [pin.path for pin in load_asset_pins(assets / "assets.lock.json")]
    missing = [path for path in missing if not (assets / path).is_file()]
    if missing:
        raise SimBundleError(
            f"{len(missing)} pinned simulation assets are not fetched (first: {missing[0]}); "
            "fetch them: uv run python scripts/fetch_sim_assets.py"
        )


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
