"""LADI v2 eval: download, cache, both classifiers, and scoring, all with fakes."""

from __future__ import annotations

import io
import json
from collections.abc import Mapping
from pathlib import Path

import pytest
from PIL import Image

from surmap.evaluation import cli
from surmap.evaluation.ladi import (
    LADI_CLASSES,
    BasetenLadiClassifier,
    LadiError,
    LadiSample,
    MetaLadiClassifier,
    evaluate,
    load_samples,
    report_json,
    score,
    shrink_jpeg,
)
from surmap.usage import BudgetExceeded, UsageLedger


def _jpeg(width: int = 64, height: int = 48, *, gps: bool = False) -> bytes:
    image = Image.new("RGB", (width, height), (10, 120, 200))
    out = io.BytesIO()
    if gps:
        exif = Image.Exif()
        exif[0x8825] = {2: (40.0, 1.0, 2.0)}
        image.save(out, format="JPEG", exif=exif)
    else:
        image.save(out, format="JPEG")
    return out.getvalue()


class _FakeHub:
    """Rows API and image downloads, counted, with no socket."""

    def __init__(self, labels: list[frozenset[str]]) -> None:
        self.labels = labels
        self.urls: list[str] = []

    def __call__(self, url: str) -> bytes:
        self.urls.append(url)
        if url.startswith("https://datasets-server.huggingface.co/rows?"):
            query = dict(part.split("=", 1) for part in url.split("?", 1)[1].split("&"))
            offset, length = int(query["offset"]), int(query["length"])
            rows = []
            for index in range(offset, min(offset + length, len(self.labels))):
                row: dict[str, object] = {name: name in self.labels[index] for name in LADI_CLASSES}
                row["image"] = {"src": f"https://assets.test/{index}.jpg"}
                rows.append({"row_idx": index, "row": row})
            return json.dumps({"rows": rows}).encode()
        if url.startswith("https://assets.test/"):
            return _jpeg(3000, 2000, gps=True)
        raise AssertionError(f"unexpected url {url}")


def test_samples_are_downloaded_once_shrunk_and_cached(tmp_path: Path) -> None:
    hub = _FakeHub(
        [frozenset({"flooding_any", "water_any"}), frozenset(), frozenset({"roads_any"})]
    )

    first = load_samples(2, offset=1, cache_dir=tmp_path, fetch=hub)
    calls_after_first = len(hub.urls)
    second = load_samples(2, offset=1, cache_dir=tmp_path, fetch=hub)

    assert [sample.index for sample in first] == [1, 2]
    assert first[1].labels == frozenset({"roads_any"})
    assert "config=default" in hub.urls[0] and "split=test" in hub.urls[0]
    assert len(hub.urls) == calls_after_first  # the second load used the cache
    assert second == first
    with Image.open(io.BytesIO(first[0].jpeg)) as image:
        assert max(image.size) == 1024
        assert 0x8825 not in image.getexif()  # GPS tags are not kept


def test_shrink_rejects_bytes_that_are_not_an_image() -> None:
    with pytest.raises(LadiError):
        shrink_jpeg(b"not an image")


class _FakeMeta:
    def __init__(self, text: str) -> None:
        self.text = text
        self.bodies: list[Mapping[str, object]] = []
        self.headers: list[Mapping[str, str]] = []

    def post_json(
        self, url: str, headers: Mapping[str, str], body: Mapping[str, object]
    ) -> Mapping[str, object]:
        assert url == "https://api.meta.ai/v1/responses"
        self.bodies.append(body)
        self.headers.append(headers)
        return {
            "output": [
                {"type": "message", "content": [{"type": "output_text", "text": self.text}]}
            ],
            "usage": {"input_tokens": 900, "output_tokens": 40},
        }


def _answer(*true: str) -> str:
    return json.dumps({name: name in true for name in LADI_CLASSES})


def test_meta_uses_strict_text_format_with_every_class(tmp_path: Path) -> None:
    fake = _FakeMeta(_answer("flooding_any", "water_any"))
    ledger = UsageLedger(tmp_path / "usage.jsonl")
    classifier = MetaLadiClassifier(transport=fake, api_key="k", ledger=ledger)

    classes = classifier.classify(_jpeg())

    assert classes == frozenset({"flooding_any", "water_any"})
    body = fake.bodies[0]
    assert body["model"] == "muse-wonder-1.0"
    assert "response_format" not in body
    text = body["text"]
    assert isinstance(text, dict)
    schema_format = text["format"]
    assert schema_format["type"] == "json_schema"
    assert schema_format["strict"] is True
    assert schema_format["schema"]["required"] == list(LADI_CLASSES)
    assert schema_format["schema"]["additionalProperties"] is False
    assert fake.headers[0]["Authorization"] == "Bearer k"
    assert ledger.calls("meta") == 1


def test_meta_respects_the_call_budget(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SURMAP_BUDGET_META_CALLS", "1")
    fake = _FakeMeta(_answer())
    classifier = MetaLadiClassifier(
        transport=fake, api_key="k", ledger=UsageLedger(tmp_path / "u.jsonl")
    )
    classifier.classify(_jpeg())
    with pytest.raises(BudgetExceeded):
        classifier.classify(_jpeg())
    assert len(fake.bodies) == 1


class _FakeBaseten:
    def __init__(self, message: dict[str, object]) -> None:
        self.message = message
        self.bodies: list[dict[str, object]] = []

    def post(self, url: str, headers: Mapping[str, str], body: bytes) -> bytes:
        assert url == "https://inference.baseten.co/v1/chat/completions"
        self.bodies.append(json.loads(body))
        return json.dumps(
            {"choices": [{"message": self.message}], "usage": {"prompt_tokens": 10}}
        ).encode()


def test_baseten_reads_the_record_classes_tool_call(tmp_path: Path) -> None:
    fake = _FakeBaseten(
        {
            "content": None,
            "tool_calls": [
                {"function": {"name": "record_classes", "arguments": _answer("debris_any")}}
            ],
        }
    )
    classifier = BasetenLadiClassifier(
        transport=fake, api_key="b", ledger=UsageLedger(tmp_path / "u.jsonl")
    )

    assert classifier.classify(_jpeg()) == frozenset({"debris_any"})
    body = fake.bodies[0]
    assert body["model"] == "meta-models/muse-spark-open-1026"
    assert body["reasoning_effort"] == "low"
    assert body["tool_choice"] == "auto"
    assert "response_format" not in body


def test_baseten_falls_back_to_json_in_the_text(tmp_path: Path) -> None:
    fake = _FakeBaseten({"content": "Here: " + _answer("trees_any")})
    classifier = BasetenLadiClassifier(
        transport=fake, api_key="b", ledger=UsageLedger(tmp_path / "u.jsonl")
    )
    assert classifier.classify(_jpeg()) == frozenset({"trees_any"})


def test_per_class_f1_and_failed_calls_are_not_scored_as_false() -> None:
    truth = [frozenset({"roads_any"}), frozenset({"roads_any", "water_any"}), frozenset()]
    predicted: list[frozenset[str] | None] = [
        frozenset({"roads_any"}),
        frozenset({"water_any", "trees_any"}),
        None,
    ]

    scores = score(truth, predicted)
    by_name = {item.name: item for item in scores.classes}

    assert scores.images == 2 and scores.failures == 1
    assert by_name["roads_any"].precision == 1.0
    assert by_name["roads_any"].recall == 0.5
    assert by_name["roads_any"].f1 == pytest.approx(2 / 3)
    assert by_name["water_any"].f1 == 1.0
    assert by_name["trees_any"].false_positive == 1
    assert scores.macro_f1 == pytest.approx((2 / 3 + 1.0) / 2)
    assert scores.micro_f1 == pytest.approx(2 * 2 / (2 * 2 + 1 + 1))
    report = report_json(scores, provider="meta", model="muse-spark-1.3")
    assert report["license"] == "CC BY 4.0"


class _Fixed:
    provider = "meta"
    model = "fake"

    def __init__(self) -> None:
        self.calls = 0

    def classify(self, jpeg: bytes) -> frozenset[str]:
        self.calls += 1
        if self.calls == 2:
            raise LadiError("bad reply")
        return frozenset({"roads_any"})


def _samples(count: int) -> list[LadiSample]:
    return [LadiSample("test", i, _jpeg(), frozenset({"roads_any"})) for i in range(count)]


def test_evaluate_reports_a_failure_and_keeps_going() -> None:
    errors: list[int] = []
    scores, rows = evaluate(_samples(3), _Fixed(), on_error=lambda s, _e: errors.append(s.index))
    assert errors == [1]
    assert scores.images == 2
    assert rows[1]["predicted"] is None


def test_cli_refuses_without_the_live_flag(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("SURMAP_LIVE_META", raising=False)
    loaded: list[int] = []

    def loader(count: int, **_kwargs: object) -> list[LadiSample]:
        loaded.append(count)
        return _samples(count)

    assert cli.main(["--limit", "2"], loader=loader) == 2
    assert loaded == []
    assert "SURMAP_LIVE_META=1" in capsys.readouterr().err


def test_cli_refuses_a_limit_above_the_image_budget(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("SURMAP_LIVE_META", "1")
    monkeypatch.setenv("MODEL_API_KEY", "k")
    monkeypatch.setenv("SURMAP_EVAL_MAX_IMAGES", "5")
    assert cli.main(["--limit", "6"], loader=lambda *_a, **_k: _samples(6)) == 2
    assert "SURMAP_EVAL_MAX_IMAGES=5" in capsys.readouterr().err


def test_cli_scores_both_providers_and_writes_a_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for name, value in {
        "SURMAP_LIVE_META": "1",
        "SURMAP_LIVE_BASETEN": "1",
        "MODEL_API_KEY": "k",
        "BASETEN_API_KEY": "b",
    }.items():
        monkeypatch.setenv(name, value)

    class _Always:
        def __init__(self, provider: str) -> None:
            self.provider = provider
            self.model = f"{provider}-model"

        def classify(self, jpeg: bytes) -> frozenset[str]:
            return frozenset({"roads_any"})

    out = tmp_path / "ladi.json"
    code = cli.main(
        ["--provider", "both", "--limit", "2", "--out", str(out)],
        loader=lambda count, **_k: _samples(count),
        classifier_factory=_Always,
    )

    assert code == 0
    reports = json.loads(out.read_text())["reports"]
    assert [r["provider"] for r in reports] == ["meta", "baseten"]
    assert reports[0]["micro_f1"] == 1.0
    assert "roads_any" in capsys.readouterr().out
    assert '"b"' not in out.read_text() and "Bearer" not in out.read_text()


def test_download_only_needs_no_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SURMAP_LIVE_META", raising=False)
    assert cli.main(["--download-only", "--limit", "2"], loader=lambda c, **_k: _samples(c)) == 0


class _SequenceBaseten:
    def __init__(self, choices: list[dict[str, object]]) -> None:
        self.choices = choices
        self.bodies: list[dict[str, object]] = []

    def post(self, url: str, headers: Mapping[str, str], body: bytes) -> bytes:
        self.bodies.append(json.loads(body))
        choice = self.choices[len(self.bodies) - 1]
        return json.dumps({"choices": [choice], "usage": {"prompt_tokens": 10}}).encode()


def test_baseten_retries_once_with_double_budget_when_cut_off(tmp_path: Path) -> None:
    fake = _SequenceBaseten(
        [
            {"message": {"content": ""}, "finish_reason": "length"},
            {
                "message": {
                    "content": None,
                    "tool_calls": [
                        {"function": {"name": "record_classes", "arguments": _answer("roads_any")}}
                    ],
                },
                "finish_reason": "tool_calls",
            },
        ]
    )
    classifier = BasetenLadiClassifier(
        transport=fake, api_key="b", ledger=UsageLedger(tmp_path / "u.jsonl")
    )

    assert classifier.classify(_jpeg()) == frozenset({"roads_any"})
    assert [body["max_tokens"] for body in fake.bodies] == [4096, 8192]


def test_baseten_reports_finish_reason_when_reply_is_empty(tmp_path: Path) -> None:
    empty: dict[str, object] = {
        "message": {"content": "I see a flooded street."},
        "finish_reason": "stop",
    }
    fake = _SequenceBaseten([empty, empty])
    classifier = BasetenLadiClassifier(
        transport=fake, api_key="b", ledger=UsageLedger(tmp_path / "u.jsonl")
    )

    with pytest.raises(LadiError, match="finish_reason=stop.*flooded street"):
        classifier.classify(_jpeg())
    assert len(fake.bodies) == 2


def test_baseten_forces_the_tool_when_reply_stops_without_an_answer(tmp_path: Path) -> None:
    fake = _SequenceBaseten(
        [
            {"message": {"content": "Looks like storm damage."}, "finish_reason": "stop"},
            {
                "message": {
                    "content": None,
                    "tool_calls": [
                        {"function": {"name": "record_classes", "arguments": _answer("trees_any")}}
                    ],
                },
                "finish_reason": "tool_calls",
            },
        ]
    )
    classifier = BasetenLadiClassifier(
        transport=fake, api_key="b", ledger=UsageLedger(tmp_path / "u.jsonl")
    )

    assert classifier.classify(_jpeg()) == frozenset({"trees_any"})
    assert [body["tool_choice"] for body in fake.bodies] == ["auto", "required"]


def test_baseten_reads_json_from_list_content(tmp_path: Path) -> None:
    fake = _SequenceBaseten(
        [
            {
                "message": {"content": [{"type": "text", "text": _answer("roads_any")}]},
                "finish_reason": "stop",
            }
        ]
    )
    classifier = BasetenLadiClassifier(
        transport=fake, api_key="b", ledger=UsageLedger(tmp_path / "u.jsonl")
    )

    assert classifier.classify(_jpeg()) == frozenset({"roads_any"})


def test_meta_classifier_follows_surmap_meta_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SURMAP_META_MODEL", "muse-spark-1.3")
    classifier = MetaLadiClassifier(api_key="m", ledger=UsageLedger(tmp_path / "u.jsonl"))

    assert classifier.model == "muse-spark-1.3"
    assert classifier.request_body(_jpeg())["model"] == "muse-spark-1.3"


def test_default_classifier_passes_reasoning_effort_to_both_providers() -> None:
    from surmap.evaluation.cli import build_parser, default_classifier

    meta = default_classifier("meta", "high")
    baseten = default_classifier("baseten", "high")

    assert isinstance(meta, MetaLadiClassifier)
    assert isinstance(baseten, BasetenLadiClassifier)
    assert meta.request_body(_jpeg())["reasoning"] == {"effort": "high"}
    body = baseten.request_body(_jpeg())
    assert body["reasoning_effort"] == "high"
    assert body["max_tokens"] == 8192
    assert build_parser().parse_args([]).reasoning_effort == "low"
