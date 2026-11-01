"""`.env` loading: project-local secrets/config without a dependency."""

import os
from pathlib import Path

import pytest

from surmap.env import load_env


def test_load_env_reads_keys_without_overriding_the_real_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given a project .env and one key already set in the real environment
    (tmp_path / ".env").write_text(
        "# a comment\n"
        "HF_TOKEN=from-file\n"
        "export SURMAP_SAM_MODEL='/models/sam 3.1.onnx'\n"
        "EMPTY=\n"
        "not-a-key-value-line\n"
    )
    monkeypatch.setenv("HF_TOKEN", "from-shell")
    monkeypatch.delenv("SURMAP_SAM_MODEL", raising=False)
    monkeypatch.delenv("EMPTY", raising=False)

    # When the .env is loaded from a subdirectory of the project
    nested = tmp_path / "src" / "surmap"
    nested.mkdir(parents=True)
    loaded = load_env(start=nested)

    # Then file keys fill gaps only, quotes/export are handled, and the
    # names (never the values) of what was set are reported
    assert loaded == ("SURMAP_SAM_MODEL", "EMPTY")
    assert os.environ["HF_TOKEN"] == "from-shell"
    assert os.environ["SURMAP_SAM_MODEL"] == "/models/sam 3.1.onnx"
    assert os.environ["EMPTY"] == ""


def test_load_env_without_a_file_is_a_no_op(tmp_path: Path) -> None:
    # Given / When / Then no .env anywhere above the start directory
    assert load_env(start=tmp_path) == ()
