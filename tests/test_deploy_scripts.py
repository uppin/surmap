import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _script(name: str) -> str:
    return (ROOT / "scripts" / name).read_text(encoding="utf-8")


def test_each_deploy_script_takes_source_path_and_ssh_target_as_cli_args() -> None:
    for name in ("deploy-cm5.sh", "deploy-station.sh", "deploy-demo.sh"):
        text = _script(name)
        # Source path is $1, SSH target is $2; missing args print usage and exit 2
        assert 'SOURCE_DIR="${1:-}"' in text
        assert 'SSH_TARGET="${2:-}"' in text
        assert "exit 2" in text


def test_deployment_restarts_the_systemd_service_and_requires_it_active() -> None:
    lib = _script("deploy-lib.sh")
    # The remote sequence ends with a restart and an is-active gate
    assert "systemctl daemon-reload" in lib
    assert "systemctl restart" in lib
    assert "systemctl is-active" in lib
    assert lib.index("systemctl restart") < lib.index("systemctl is-active")


def test_cm5_deploy_can_choose_the_detector_model_profile() -> None:
    cm5 = _script("deploy-cm5.sh")
    lib = _script("deploy-lib.sh")
    unit = (ROOT / "deploy/systemd/surmap-cm5.service").read_text(encoding="utf-8")
    # The CLI option validates against the profile registry names and
    # renders the choice into the systemd unit's server args
    assert "--model" in cm5 and "--coral-cpu" in cm5
    for profile in ("efficientdet-lite0", "ssd-mobilenet-v2", "ssdlite-mobiledet"):
        assert profile in cm5
    assert "fetch_coral_model.py" in cm5
    assert "--detector coral --coral-model $MODEL" in cm5
    assert "--coral-edgetpu" in cm5
    assert "SERVER_ARGS" in lib and "@SERVER_ARGS@" in lib
    assert "@SERVER_ARGS@" in unit


def test_cm5_deploy_defaults_to_rtabmap_plus_coral_with_extras_off() -> None:
    cm5 = _script("deploy-cm5.sh")
    # The deployed default is the streaming RTAB-Map backend plus the
    # default Coral profile; optional computations are forwarded only
    # when their deploy flags are given
    assert 'SLAM="streaming"' in cm5
    assert "--slam-backend $SLAM" in cm5
    assert "--calibration-dir" in cm5
    assert 'MODEL="efficientdet-lite0"' in cm5
    assert "--object-tracking" in cm5
    assert "--moving-areas" in cm5
    assert "--region-points" in cm5
    assert "--rtabmap-native" in cm5


def test_cm5_deploy_builds_the_native_rtabmap_binary_only_when_missing() -> None:
    cm5 = _script("deploy-cm5.sh")
    build = _script("build_rtabmap_native.sh")
    # The target-side build directory is the cache: the stream binary
    # stays in the build tree (no copy elsewhere), the deploy ensures
    # it before the main sync/restart, and the build script itself
    # exits early when the binary already exists there
    assert ".cache/surmap-rtabmap/stream-build/surmap-rtabmap-stream" in cm5
    assert "build_rtabmap_native.sh" in cm5
    assert cm5.index("build_rtabmap_native.sh") < cm5.index("deploy_component")
    assert "--rtabmap-docker" in cm5
    assert "stream-build" in build and "already present" in build and "FORCE" in build
    cmake = (ROOT / "deploy/rtabmap-stream/CMakeLists.txt").read_text(encoding="utf-8")
    assert "find_package(jsoncpp" in cmake


def test_cm5_deploy_rejects_an_unknown_model_without_touching_ssh() -> None:
    script = ROOT / "scripts" / "deploy-cm5.sh"
    result = subprocess.run(
        [str(script), "/tmp", "user@invalid", "/opt/surmap", "8080", "22", "--model", "bogus"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "unknown model profile" in result.stderr


def test_station_deploy_can_select_sam31_torch_and_provisions_it_before_restart() -> None:
    station = _script("deploy-station.sh")
    lib = _script("deploy-lib.sh")
    # The station deploy selects the PyTorch SAM 3.1 detector and
    # installs the torch stack into the station venv before the
    # service restarts with it (the hook runs pre-restart)
    assert "--detector sam31-torch" in station
    assert "--sam31-model" in station
    assert "--sam31-device" in station
    assert "torch" in station and "sam3" in station
    assert "pre_restart" in lib
    assert lib.index("pre_restart") < lib.index("systemctl restart")


def test_demo_deploy_points_the_page_at_the_cm5_and_station_hosts() -> None:
    demo = _script("deploy-demo.sh")
    unit = (ROOT / "deploy/systemd/surmap-demo.service").read_text(encoding="utf-8")
    # The demo deploy renders both remote hosts into the unit's args;
    # the Radxa CM5 is the default CM5 host, the station is local
    assert "--cm5-host" in demo and "--station-host" in demo
    assert "10.88.77.14:8080" in demo
    assert "127.0.0.1:8081" in demo
    assert "scripts/demo.py" in unit
    assert "@SERVER_ARGS@" in unit
    assert "User=surmap" in unit
    # The dataset cache + history live in a state directory, not the
    # install tree, so a redeploy's rsync --delete cannot wipe them
    assert "StateDirectory=surmap-demo" in unit
    assert "SURMAP_DEMO_CACHE_DIR=/var/lib/surmap-demo" in unit


def test_the_deploy_scripts_are_executable_and_parse() -> None:
    for name in ("deploy-cm5.sh", "deploy-station.sh", "deploy-demo.sh", "deploy-lib.sh"):
        path = ROOT / "scripts" / name
        assert path.stat().st_mode & 0o111
        subprocess.run(["bash", "-n", str(path)], check=True)


def test_systemd_units_run_the_entrypoints_as_the_surmap_user() -> None:
    cm5 = (ROOT / "deploy/systemd/surmap-cm5.service").read_text(encoding="utf-8")
    station = (ROOT / "deploy/systemd/surmap-station.service").read_text(encoding="utf-8")
    assert "User=surmap" in cm5 and "User=surmap" in station
    assert "surmap.survey.cm5_main" in cm5
    assert "surmap.survey.station_main" in station
    assert "Restart=on-failure" in cm5 and "Restart=on-failure" in station
    # Both units must carry the deploy-rendered server args, or the
    # deployed detector/SLAM options silently never reach the process
    assert "@SERVER_ARGS@" in cm5 and "@SERVER_ARGS@" in station
