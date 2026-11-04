"""`scripts/fetch_coral_model.py`: where the pinned Coral artifacts are downloaded from.

CI fetched them from Google's `google-coral/test_data` on raw.githubusercontent.com, whose reads
timed out on about one run in nine. They are now hosted as release assets on this repo, as the
EuRoC fixture is; the upstream stays reachable with `--upstream`, and the pinned SHA-256 is what
is trusted either way.
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "fetch_coral_model.py"
RELEASE = "https://github.com/uppin/surmap/releases/download/fixtures-coral-v1"
UPSTREAM = "https://raw.githubusercontent.com/google-coral/test_data/master"
LABELS = b"person\nbicycle\n"


def _load_fetch() -> ModuleType:
    spec = importlib.util.spec_from_file_location("fetch_coral_model", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["fetch_coral_model"] = module
    spec.loader.exec_module(module)
    return module


fetch_coral_model = _load_fetch()


class RecordingHost:
    """Serves one pinned artifact, `coco_labels.txt`, and records every URL asked for."""

    def __init__(self) -> None:
        self.requested: list[str] = []

    def urlopen(self, url: str, timeout: float) -> io.BytesIO:
        self.requested.append(url)
        return io.BytesIO(LABELS)


@pytest.fixture
def host(monkeypatch: pytest.MonkeyPatch) -> RecordingHost:
    recording = RecordingHost()
    monkeypatch.setattr(
        fetch_coral_model,
        "ARTIFACTS",
        (("coco_labels.txt", len(LABELS), hashlib.sha256(LABELS).hexdigest()),),
    )
    monkeypatch.setattr(fetch_coral_model.urllib.request, "urlopen", recording.urlopen)
    return recording


def test_the_artifacts_come_from_this_repo_s_release(host: RecordingHost, tmp_path: Path) -> None:
    # When the model is prepared into an empty directory
    fetch_coral_model.main(["--output", str(tmp_path)])

    # Then each artifact was downloaded from the fixtures-coral-v1 release of this repo
    assert host.requested == [f"{RELEASE}/coco_labels.txt"]
    assert (tmp_path / "coco_labels.txt").read_bytes() == LABELS


def test_upstream_downloads_them_from_google_s_coral_test_data(
    host: RecordingHost, tmp_path: Path
) -> None:
    # When the model is prepared from the upstream host (to refresh the release assets)
    fetch_coral_model.main(["--output", str(tmp_path), "--upstream"])

    # Then each artifact came from google-coral/test_data
    assert host.requested == [f"{UPSTREAM}/coco_labels.txt"]
