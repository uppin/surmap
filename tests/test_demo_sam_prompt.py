"""Demo SAM prompt: each scene has a default concept, the page changes it.

The prompt is resolved per stream — the page's `?prompt=`, else the
launcher's `--sam-label`, else the scene's own default — and reaches
SAM when playback starts. An ONNX export's concept is fixed, so the
page shows it read-only.
"""

import json
import threading
import urllib.parse
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from http.server import ThreadingHTTPServer
from pathlib import Path

from surmap.demo.datasets import DATASETS, PreparedDataset
from surmap.demo.server import DemoPlayer, make_demo_server
from surmap.survey.sam import InMemoryVideoSamStreamer, SamDetection
from tests.test_demo import _prepared_tiny

FAKE_ONNX = Path(__file__).parent / "fixtures" / "sam3_fake" / "fake_sam3.onnx"


def a_streamer() -> InMemoryVideoSamStreamer:
    return InMemoryVideoSamStreamer((SamDetection("any", 0.9, (1.0, 2.0, 30.0, 40.0)),))


def a_scene_prompted(tmp_path: Path, prompt: str) -> PreparedDataset:
    prepared = _prepared_tiny(tmp_path)
    return replace(prepared, spec=replace(prepared.spec, sam_prompt=prompt))


@contextmanager
def serving(server: ThreadingHTTPServer) -> Iterator[str]:
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = str(server.server_address[0]), int(server.server_address[1])
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def get(url: str) -> str:
    with urllib.request.urlopen(url, timeout=10) as response:
        body: bytes = response.read()
    return body.decode()


def test_every_scene_names_a_default_sam_prompt() -> None:
    # Given / When the registry is read
    prompts = {dataset_id: spec.sam_prompt for dataset_id, spec in DATASETS.items()}

    # Then each scene has a concept to look for, cars on the KITTI street
    assert all(prompt.strip() for prompt in prompts.values())
    assert prompts["kitti-2011-09-26-drive-0009"] == "car"


def test_the_player_prompts_sam_with_the_runs_prompt(tmp_path: Path) -> None:
    # Given a player for a run prompted "person"
    streamer = a_streamer()
    player = DemoPlayer(
        _prepared_tiny(tmp_path),
        fps=1000.0,
        with_rtabmap=False,
        sam_streamer=streamer,
        sam_prompt="person",
    )

    # When playback runs to the end
    list(player.events())

    # Then SAM was asked for that concept for the whole video
    assert streamer.prompts == ["person"]


def test_a_stream_without_a_prompt_uses_the_scenes_default(tmp_path: Path) -> None:
    # Given a scene whose default concept is "tree"
    streamer = a_streamer()
    server = make_demo_server(
        a_scene_prompted(tmp_path, "tree"),
        host="127.0.0.1",
        port=0,
        with_rtabmap=False,
        sam_streamer=streamer,
    )

    # When the stream is opened without a prompt
    with serving(server) as base:
        get(f"{base}/stream")

    # Then SAM looks for trees
    assert streamer.prompts == ["tree"]


def test_the_pages_prompt_replaces_the_scenes_default(tmp_path: Path) -> None:
    # Given a scene whose default concept is "tree"
    streamer = a_streamer()
    server = make_demo_server(
        a_scene_prompted(tmp_path, "tree"),
        host="127.0.0.1",
        port=0,
        with_rtabmap=False,
        sam_streamer=streamer,
    )

    # When the page opens the stream prompted "traffic sign"
    with serving(server) as base:
        get(f"{base}/stream?{urllib.parse.urlencode({'prompt': 'traffic sign'})}")

    # Then SAM looks for traffic signs
    assert streamer.prompts == ["traffic sign"]


def test_a_blank_prompt_falls_back_to_the_scenes_default(tmp_path: Path) -> None:
    # Given a scene whose default concept is "tree"
    streamer = a_streamer()
    server = make_demo_server(
        a_scene_prompted(tmp_path, "tree"),
        host="127.0.0.1",
        port=0,
        with_rtabmap=False,
        sam_streamer=streamer,
    )

    # When the page sends a blank prompt
    with serving(server) as base:
        get(f"{base}/stream?prompt=%20%20")

    # Then the scene's default is used
    assert streamer.prompts == ["tree"]


def test_the_launchers_label_overrides_every_scenes_default(tmp_path: Path) -> None:
    # Given a launcher started with --sam-label bicycle on a "tree" scene
    streamer = a_streamer()
    server = make_demo_server(
        a_scene_prompted(tmp_path, "tree"),
        host="127.0.0.1",
        port=0,
        with_rtabmap=False,
        sam_streamer=streamer,
        sam_label="bicycle",
    )

    # When the stream is opened without a prompt
    with serving(server) as base:
        get(f"{base}/stream")

    # Then the launcher's label wins over the scene's default
    assert streamer.prompts == ["bicycle"]


def test_the_page_offers_the_prompt_box_filled_with_the_scenes_default(tmp_path: Path) -> None:
    # Given a SAM-enabled server on a "tree" scene
    server = make_demo_server(
        a_scene_prompted(tmp_path, "tree"),
        host="127.0.0.1",
        port=0,
        with_rtabmap=False,
        sam_streamer=a_streamer(),
    )

    # When the page is loaded
    with serving(server) as base:
        page = get(f"{base}/")

    # Then the SAM pane has an editable prompt box holding "tree"
    assert 'id="sam-prompt"' in page
    assert 'name="prompt"' in page
    assert 'value="tree"' in page
    assert "readonly" not in page


def test_the_page_keeps_the_applied_prompt_escaped(tmp_path: Path) -> None:
    # Given a SAM-enabled server
    server = make_demo_server(
        _prepared_tiny(tmp_path),
        host="127.0.0.1",
        port=0,
        with_rtabmap=False,
        sam_streamer=a_streamer(),
    )

    # When the page is loaded with a prompt carrying markup
    with serving(server) as base:
        page = get(f"{base}/?{urllib.parse.urlencode({'prompt': 'red <b>car'})}")

    # Then the box holds it as text, never as markup
    assert 'value="red &lt;b&gt;car"' in page
    assert "red <b>car" not in page


def test_the_page_has_no_prompt_box_without_sam(tmp_path: Path) -> None:
    # Given a server with no SAM
    server = make_demo_server(
        _prepared_tiny(tmp_path), host="127.0.0.1", port=0, with_rtabmap=False
    )

    # When the page is loaded
    with serving(server) as base:
        page = get(f"{base}/")

    # Then there is nothing to prompt
    assert 'id="sam-prompt"' not in page


def test_an_onnx_exports_concept_is_shown_read_only(tmp_path: Path) -> None:
    # Given a server on an ONNX export labelled "fixture"
    server = make_demo_server(
        a_scene_prompted(tmp_path, "tree"),
        host="127.0.0.1",
        port=0,
        with_rtabmap=False,
        sam_model=FAKE_ONNX,
        sam_device="cpu",
        sam_label="fixture",
    )

    # When the page is loaded, even asking for another concept
    with serving(server) as base:
        page = get(f"{base}/?prompt=person")

    # Then the box shows the export's own concept and cannot be edited
    assert 'value="fixture"' in page
    assert "readonly" in page


def test_a_persisted_run_names_its_prompt(tmp_path: Path) -> None:
    # Given a SAM-enabled server
    server = make_demo_server(
        _prepared_tiny(tmp_path),
        host="127.0.0.1",
        port=0,
        with_rtabmap=False,
        sam_streamer=a_streamer(),
    )

    # When a run is played prompted "person"
    with serving(server) as base:
        get(f"{base}/stream?prompt=person")
        runs = json.loads(get(f"{base}/runs"))["runs"]

    # Then the persisted run's title says what SAM looked for
    assert "SAM: person" in runs[0]["title"]
