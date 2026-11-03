"""The Modal deploy targets for the simulated CM5 and the station.

`surmap.survey.modal_hosting` holds what the app files run — importable, so it is tested
directly. The app files themselves import `modal`, which CI does not install, so their shape is
read with the AST: one `web_server` function at module scope, one container, the token secret.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from surmap.survey.cm5_main import build_parser as cm5_parser
from surmap.survey.modal_hosting import (
    CM5_PORT,
    STATION_PORT,
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
