import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _script(name: str) -> str:
    return (ROOT / "scripts" / name).read_text(encoding="utf-8")


def test_each_deploy_script_takes_source_path_and_ssh_target_as_cli_args() -> None:
    for name in ("deploy-cm5.sh", "deploy-station.sh"):
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


def test_the_deploy_scripts_are_executable_and_parse() -> None:
    for name in ("deploy-cm5.sh", "deploy-station.sh", "deploy-lib.sh"):
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
