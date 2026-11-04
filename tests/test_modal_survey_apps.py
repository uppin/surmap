"""The Modal deploy targets for the simulated CM5 and the station.

`surmap.survey.modal_hosting` holds what the app files run — importable, so it is tested
directly. The app files themselves import `modal`, which CI does not install, so their shape is
read with the AST: one `web_server` function at module scope, one container, the token secret.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from surmap.agent.__main__ import build_parser as agent_parser
from surmap.survey.cm5_main import build_parser as cm5_parser
from surmap.survey.modal_hosting import (
    AGENT_CACHE,
    AGENT_PORT,
    AGENT_WEB_DIST,
    CM5_PORT,
    SAM3_PACKAGE,
    SAM3_RUNTIME_PACKAGES,
    STATION_PORT,
    StationSettings,
    agent_command,
    cm5_command,
    station_command,
)
from surmap.survey.station_main import build_parser as station_parser

CM5_APP = Path("src/surmap/survey/modal_cm5_app.py")
STATION_APP = Path("src/surmap/survey/modal_station_app.py")


def module_function(source: Path, name: str) -> ast.FunctionDef:
    tree = ast.parse(source.read_text(encoding="utf-8"))
    found = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name]
    assert len(found) == 1, f"{source} defines no module-level {name}()"
    return found[0]


def decorator(function: ast.FunctionDef, attribute: str) -> ast.Call:
    calls = [
        node
        for node in function.decorator_list
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == attribute
    ]
    assert len(calls) == 1, f"{function.name} has no @...{attribute}(...)"
    return calls[0]


def keyword_value(call: ast.Call, name: str) -> object:
    for keyword in call.keywords:
        if keyword.arg == name:
            return ast.literal_eval(keyword.value) if _is_literal(keyword.value) else keyword.value
    return None


def _is_literal(node: ast.expr) -> bool:
    try:
        ast.literal_eval(node)
    except ValueError:
        return False
    return True


def image_steps(source: Path) -> list[ast.Call]:
    """The module-level `image = (...)` builder chain, first call first."""
    tree = ast.parse(source.read_text(encoding="utf-8"))
    assigned = [
        node.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "image" for target in node.targets)
    ]
    assert len(assigned) == 1, f"{source} assigns no module-level image"
    steps: list[ast.Call] = []
    node: ast.expr = assigned[0]
    while isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        steps.append(node)
        node = node.func.value
    return steps[::-1]


def step_named(steps: list[ast.Call], name: str, first_arg: str) -> int:
    """Index of the `.name(first_arg, ...)` step, by the unparsed first argument."""
    found = [
        index
        for index, step in enumerate(steps)
        if isinstance(step.func, ast.Attribute)
        and step.func.attr == name
        and step.args
        and ast.unparse(step.args[0]) == first_arg
    ]
    assert len(found) == 1, f"no single .{name}({first_arg}, ...) step"
    return found[0]


def test_the_cm5_command_serves_the_simulated_drone_on_every_interface() -> None:
    # Given the command the CM5 app runs
    args = cm5_parser().parse_args(
        cm5_command(rtabmap_binary="/opt/rtabmap/surmap-rtabmap-stream")[3:]
    )

    # Then it binds all interfaces on the app's port, runs RTAB-Map natively, and has no Coral
    assert (args.host, args.port) == ("0.0.0.0", CM5_PORT)
    assert (args.slam_backend, args.rtabmap_native) == (
        "streaming",
        Path("/opt/rtabmap/surmap-rtabmap-stream"),
    )
    assert args.detector == "none"


def test_the_station_command_serves_sam_on_every_interface() -> None:
    # Given the command the station app runs
    args = station_parser().parse_args(station_command()[3:])

    # Then it binds all interfaces on the app's port and runs SAM 3.1 on the GPU
    assert (args.host, args.port) == ("0.0.0.0", STATION_PORT)
    assert args.detector == "sam31-torch"


@pytest.mark.parametrize("command", [cm5_command(rtabmap_binary="/bin/x"), station_command()])
def test_each_command_runs_a_survey_main_as_a_module(command: list[str]) -> None:
    # Given a command an app runs
    # When its program is read
    # Then it runs one of the survey mains as a module (the app swaps in its own interpreter)
    assert command[:2] == ["python", "-m"]
    assert command[2] in {"surmap.survey.cm5_main", "surmap.survey.station_main"}


@pytest.mark.parametrize(
    ("source", "port_name"), [(CM5_APP, "CM5_PORT"), (STATION_APP, "STATION_PORT")]
)
def test_each_app_is_one_web_server_container_holding_the_token_secret(
    source: Path, port_name: str
) -> None:
    # Given the app file, which CI does not import
    serve = module_function(source, "serve")
    function = decorator(serve, "function")
    web_server = decorator(serve, "web_server")

    # Then it is one web-server container on the hosting port, reading the survey secret
    assert keyword_value(function, "max_containers") == 1
    assert keyword_value(function, "timeout") is not None
    assert keyword_value(function, "cpu") is not None
    assert keyword_value(function, "memory") is not None
    assert isinstance(web_server.args[0], ast.Name) and web_server.args[0].id == port_name
    text = source.read_text(encoding="utf-8")
    assert "SURVEY_SECRET" in text and "from_name(SURVEY_SECRET)" in text


def test_the_station_app_runs_on_a_gpu_and_the_cm5_app_does_not() -> None:
    # Given both app files, which CI does not import
    # When their function decorators are read
    station = decorator(module_function(STATION_APP, "serve"), "function")
    cm5 = decorator(module_function(CM5_APP, "serve"), "function")

    # Then only the station asks for a GPU
    assert keyword_value(station, "gpu") is not None
    assert keyword_value(cm5, "gpu") is None


def test_the_label_set_at_deploy_time_is_the_label_the_container_runs() -> None:
    # Given the settings read where the app is deployed, with a concept prompt chosen
    deployed = StationSettings.from_env({"SURMAP_STATION_LABEL": "mattress"})

    # When the container reads its settings from only the env the deploy hands it
    in_container = StationSettings.from_env(deployed.container_env())

    # Then the station it starts prompts SAM with the deploy-time label
    args = station_parser().parse_args(station_command(in_container.label)[3:])
    assert args.sam31_label == "mattress"


def test_the_station_app_hands_the_container_its_settings_through_a_deploy_time_secret() -> None:
    # Given the station app file, which CI does not import
    function = decorator(module_function(STATION_APP, "serve"), "function")

    # When its secrets and GPU are read
    secrets = keyword_value(function, "secrets")
    gpu = keyword_value(function, "gpu")

    # Then the container gets the deploy-time settings, and the GPU list comes from them too
    assert isinstance(secrets, ast.expr)
    assert "Secret.from_dict(_SETTINGS.container_env())" in ast.unparse(secrets)
    assert isinstance(gpu, ast.expr) and ast.unparse(gpu) == "_SETTINGS.gpus"


def test_the_station_falls_back_from_an_l4_to_an_a10g_by_default() -> None:
    # Given no GPU override
    settings = StationSettings.from_env({})

    # Then Modal may place it on an L4, or on an A10G when no L4 is free
    assert settings.gpus == ["L4", "A10G"]


def test_a_gpu_override_names_its_own_fallback_order() -> None:
    # Given an override listing two GPU types
    settings = StationSettings.from_env({"SURMAP_MODAL_GPU": "A10G, A100"})

    # Then the station asks for exactly those, in that order
    assert settings.gpus == ["A10G", "A100"]


def test_the_station_keeps_its_day_long_timeout_and_five_minute_scaledown_by_default() -> None:
    # Given no overrides
    settings = StationSettings.from_env({})

    # Then a stream may last a day, an idle container stays five minutes, SAM looks for objects
    assert (settings.timeout_s, settings.scaledown_s, settings.label) == (86400, 300, "object")


def test_the_sam3_runtime_leaves_numpy_to_surmaps_own_pin() -> None:
    # Given the packages the station image installs for sam3
    names = {package.split(">")[0].split("=")[0].split("<")[0] for package in SAM3_RUNTIME_PACKAGES}

    # Then sam3's declared runtime dependencies are there, except its numpy<2 pin
    assert {
        "timm",
        "tqdm",
        "ftfy",
        "regex",
        "iopath",
        "typing_extensions",
        "huggingface_hub",
    } <= names
    assert "numpy" not in names


def test_the_station_image_installs_sam3_without_its_deps_after_surmaps_pyproject() -> None:
    # Given the station image's build steps, which CI does not run
    steps = image_steps(STATION_APP)

    # When the sam3 package and the pyproject install are found
    pyproject = step_named(steps, "pip_install_from_pyproject", "'pyproject.toml'")
    sam3 = step_named(steps, "pip_install", "SAM3_PACKAGE")

    # Then sam3 comes after surmap's own pins, with no dependency resolution of its own
    assert sam3 > pyproject
    assert keyword_value(steps[sam3], "extra_options") == "--no-deps"
    assert SAM3_PACKAGE.startswith("sam3 @ git+https://github.com/facebookresearch/sam3.git")


AGENT_APP = Path("src/surmap/agent/modal_agent_app.py")


def test_the_agent_command_serves_the_chat_page_on_every_interface_with_the_modal_station() -> None:
    # Given the command the agent app runs
    args = agent_parser().parse_args(agent_command()[3:])

    # Then it binds all interfaces on the app's port, drives the Modal station, serves the page
    assert (args.host, args.port) == ("0.0.0.0", AGENT_PORT)
    assert args.station == "modal"
    assert (args.web_dist, args.cache_dir) == (Path(AGENT_WEB_DIST), Path(AGENT_CACHE))


def test_the_agent_app_is_one_cpu_web_server_holding_its_secrets() -> None:
    # Given the agent app file, which CI does not import
    serve = module_function(AGENT_APP, "serve")
    function = decorator(serve, "function")
    web_server = decorator(serve, "web_server")

    # Then it is one CPU container (conversations live in its memory) on the agent port,
    # reading the agent's secret (model key, pass code) and the survey token
    assert keyword_value(function, "max_containers") == 1
    assert keyword_value(function, "gpu") is None
    assert keyword_value(function, "timeout") is not None
    assert isinstance(web_server.args[0], ast.Name) and web_server.args[0].id == "AGENT_PORT"
    text = AGENT_APP.read_text(encoding="utf-8")
    assert "from_name(AGENT_SECRET)" in text and "from_name(SURVEY_SECRET)" in text
