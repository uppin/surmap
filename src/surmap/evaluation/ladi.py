"""Per-class F1 of Muse Spark on LADI v2 aerial disaster imagery.

LADI v2 (MIT Lincoln Laboratory, CC BY 4.0, Hugging Face
``MITLL/LADI-v2-dataset``) is a multi-label set of Civil Air Patrol
photos from US disasters. Its default (``v2a``) config has the twelve
boolean classes in ``LADI_CLASSES``.

Images are downloaded on demand from the Hugging Face dataset viewer and
cached outside the repository (``~/.cache/surmap/ladi-v2`` by default).
Each image is re-encoded at most ``MAX_SIDE`` pixels wide, which also
drops the EXIF block and its GPS tags. No data is committed.

Two classifiers are compared:

* ``MetaLadiClassifier``: hosted ``muse-spark-1.3`` on the Meta Model API,
  with structured output (``text.format`` JSON schema, strict).
* ``BasetenLadiClassifier``: open-weight ``meta-models/muse-spark-open-1026``
  on Baseten, with a ``record_classes`` tool call (Baseten has no JSON
  mode for this model) and ``reasoning_effort`` ``low``.

Both take an injectable transport, so tests never open a socket.
"""

from __future__ import annotations

import base64
import io
import json
import os
import time
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from PIL import Image

from surmap.labelling.baseten_muse import (
    DEFAULT_MODEL_ID as BASETEN_MODEL_ID,
)
from surmap.labelling.baseten_muse import (
    ChatTransport,
)
from surmap.labelling.meta_muse import (
    HOSTED_MUSE_SPARK_MODEL,
    META_MODEL_API_BASE_URL,
    MetaMuseTransport,
    UrllibMetaMuseTransport,
)
from surmap.usage import UsageLedger, UsageRecord

DATASET = "MITLL/LADI-v2-dataset"
DATASET_LICENSE = "CC BY 4.0"
ROWS_URL = "https://datasets-server.huggingface.co/rows"
MAX_SIDE = 1024
_PAGE = 100

LADI_CLASSES: tuple[str, ...] = (
    "bridges_any",
    "buildings_any",
    "buildings_affected_or_greater",
    "buildings_minor_or_greater",
    "debris_any",
    "flooding_any",
    "flooding_structures",
    "roads_any",
    "roads_damage",
    "trees_any",
    "trees_damage",
    "water_any",
)

CLASS_HINTS: Mapping[str, str] = {
    "bridges_any": "any bridge is visible",
    "buildings_any": "any building is visible",
    "buildings_affected_or_greater": "a building shows any disaster impact (affected or worse)",
    "buildings_minor_or_greater": "a building has at least minor damage",
    "debris_any": "disaster debris is visible",
    "flooding_any": "any flood water is visible",
    "flooding_structures": "flood water reaches buildings or other structures",
    "roads_any": "any road is visible",
    "roads_damage": "a road is damaged or blocked",
    "trees_any": "any trees are visible",
    "trees_damage": "trees are damaged or down",
    "water_any": "any body of water is visible (flood or normal)",
}

Fetch = Callable[[str], bytes]


class LadiError(RuntimeError):
    """The dataset or a model reply could not be used."""


@dataclass(frozen=True)
class LadiSample:
    split: str
    index: int
    jpeg: bytes
    labels: frozenset[str]


class LadiClassifier(Protocol):
    @property
    def provider(self) -> str: ...

    @property
    def model(self) -> str: ...

    def classify(self, jpeg: bytes) -> frozenset[str]: ...


def default_cache_dir() -> Path:
    """``$SURMAP_LADI_CACHE`` when set, otherwise ``~/.cache/surmap/ladi-v2``."""
    configured = os.environ.get("SURMAP_LADI_CACHE", "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".cache" / "surmap" / "ladi-v2"


def _urllib_fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "surmap-eval"})
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = response.read()
    if not isinstance(payload, bytes):
        raise LadiError("download did not return bytes")
    return payload


def rows_url(split: str, offset: int, length: int) -> str:
    query = urllib.parse.urlencode(
        {
            "dataset": DATASET,
            "config": "default",
            "split": split,
            "offset": offset,
            "length": length,
        }
    )
    return f"{ROWS_URL}?{query}"


def load_samples(
    count: int,
    *,
    split: str = "test",
    offset: int = 0,
    cache_dir: Path | None = None,
    fetch: Fetch | None = None,
) -> list[LadiSample]:
    """``count`` samples from ``split`` starting at ``offset``, cached on disk."""
    if count < 1:
        raise LadiError("count must be at least 1")
    if split not in {"train", "validation", "test"}:
        raise LadiError(f"unknown LADI v2 split {split!r}")
    root = (cache_dir if cache_dir is not None else default_cache_dir()) / split
    get = fetch if fetch is not None else _urllib_fetch
    samples: dict[int, LadiSample] = {}
    wanted = range(offset, offset + count)
    for index in wanted:
        cached = _read_cached(root, split, index)
        if cached is not None:
            samples[index] = cached
    missing = [index for index in wanted if index not in samples]
    while missing:
        start = missing[0]
        length = min(_PAGE, missing[-1] - start + 1)
        page = _json(get(rows_url(split, start, length)))
        rows = page.get("rows")
        if not isinstance(rows, list) or not rows:
            raise LadiError(f"LADI v2 rows API returned no rows at offset {start}")
        for entry in rows:
            sample = _sample_from_row(entry, split, get)
            if sample.index in wanted and sample.index not in samples:
                _write_cached(root, sample)
                samples[sample.index] = sample
        still = [index for index in missing if index not in samples]
        if still == missing:
            raise LadiError(f"LADI v2 rows API did not return index {start}")
        missing = still
    return [samples[index] for index in wanted]


def _sample_from_row(entry: object, split: str, get: Fetch) -> LadiSample:
    if not isinstance(entry, dict):
        raise LadiError("LADI v2 row was not an object")
    index = entry.get("row_idx")
    row = entry.get("row")
    if not isinstance(index, int) or not isinstance(row, dict):
        raise LadiError("LADI v2 row had no row_idx or row")
    image = row.get("image")
    src = image.get("src") if isinstance(image, dict) else None
    if not isinstance(src, str) or not src.startswith("https://"):
        raise LadiError(f"LADI v2 row {index} had no https image")
    labels = frozenset(name for name in LADI_CLASSES if row.get(name) is True)
    return LadiSample(split=split, index=index, jpeg=shrink_jpeg(get(src)), labels=labels)


def shrink_jpeg(raw: bytes, max_side: int = MAX_SIDE) -> bytes:
    """Re-encode as RGB JPEG at most ``max_side`` pixels; EXIF (with GPS) is dropped."""
    try:
        with Image.open(io.BytesIO(raw)) as opened:
            image = opened.convert("RGB")
    except (OSError, ValueError) as exc:
        raise LadiError("LADI v2 image could not be decoded") from exc
    image.thumbnail((max_side, max_side))
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=85)
    return out.getvalue()


def _read_cached(root: Path, split: str, index: int) -> LadiSample | None:
    image_path = root / f"{index:05d}.jpg"
    label_path = root / f"{index:05d}.json"
    if not image_path.is_file() or not label_path.is_file():
        return None
    labels = json.loads(label_path.read_text(encoding="utf-8"))
    if not isinstance(labels, list):
        return None
    names = frozenset(str(name) for name in labels if name in LADI_CLASSES)
    return LadiSample(split=split, index=index, jpeg=image_path.read_bytes(), labels=names)


def _write_cached(root: Path, sample: LadiSample) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{sample.index:05d}.jpg").write_bytes(sample.jpeg)
    (root / f"{sample.index:05d}.json").write_text(
        json.dumps(sorted(sample.labels)), encoding="utf-8"
    )


def _json(raw: bytes) -> dict[str, object]:
    try:
        parsed = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LadiError("reply was not JSON") from exc
    if not isinstance(parsed, dict):
        raise LadiError("reply was not a JSON object")
    return {str(key): value for key, value in parsed.items()}


def classes_schema() -> dict[str, object]:
    """Strict JSON schema: one boolean per LADI class, all required."""
    return {
        "type": "object",
        "properties": {
            name: {"type": "boolean", "description": CLASS_HINTS[name]} for name in LADI_CLASSES
        },
        "required": list(LADI_CLASSES),
        "additionalProperties": False,
    }


def classification_prompt() -> str:
    lines = "\n".join(f"- {name}: true if {CLASS_HINTS[name]}" for name in LADI_CLASSES)
    return (
        "This is an aerial photo taken for civilian disaster response. "
        "For each class, answer true or false from what is visible.\n"
        f"{lines}"
    )


def parse_classes(payload: Mapping[str, object]) -> frozenset[str]:
    """Classes set to ``true``. Missing or non-boolean values count as false."""
    return frozenset(name for name in LADI_CLASSES if payload.get(name) is True)


def _data_url(jpeg: bytes) -> str:
    if not jpeg.startswith(b"\xff\xd8"):
        raise LadiError("classifier input must be a JPEG")
    return "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")


def _key(explicit: str | None, env: str) -> str:
    key = explicit if explicit is not None else os.environ.get(env, "").strip()
    if not key:
        raise LadiError(f"{env} is not set")
    return key


class MetaLadiClassifier:
    """Hosted Muse Spark with ``text.format`` structured output."""

    provider = "meta"

    def __init__(
        self,
        *,
        transport: MetaMuseTransport | None = None,
        api_key: str | None = None,
        model: str = HOSTED_MUSE_SPARK_MODEL,
        ledger: UsageLedger | None = None,
        reasoning_effort: str = "low",
        max_output_tokens: int = 2048,
    ) -> None:
        self._transport = transport if transport is not None else UrllibMetaMuseTransport()
        self._api_key = api_key
        self._model = model
        self._ledger = ledger if ledger is not None else UsageLedger()
        self._effort = reasoning_effort
        self._max_output_tokens = max_output_tokens

    @property
    def model(self) -> str:
        return self._model

    def request_body(self, jpeg: bytes) -> dict[str, object]:
        content: list[object] = [
            {"type": "input_text", "text": classification_prompt()},
            {"type": "input_image", "image_url": _data_url(jpeg)},
        ]
        return {
            "model": self._model,
            "input": [{"type": "message", "role": "user", "content": content}],
            "stream": False,
            "reasoning": {"effort": self._effort},
            "max_output_tokens": self._max_output_tokens,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "ladi_classes",
                    "schema": classes_schema(),
                    "strict": True,
                }
            },
        }

    def classify(self, jpeg: bytes) -> frozenset[str]:
        body = self.request_body(jpeg)
        self._ledger.check(self.provider)
        headers = {
            "Authorization": f"Bearer {_key(self._api_key, 'MODEL_API_KEY')}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        url = META_MODEL_API_BASE_URL.rstrip("/") + "/responses"
        payload = self._transport.post_json(url, headers, body)
        usage = payload.get("usage")
        if isinstance(usage, dict):
            self._ledger(
                UsageRecord(
                    provider=self.provider,
                    model=self._model,
                    input_tokens=_int(usage.get("input_tokens")),
                    output_tokens=_int(usage.get("output_tokens")),
                    reasoning_tokens=None,
                    t_unix=time.time(),
                )
            )
        return parse_classes(_json(_responses_text(payload).encode("utf-8")))


def _responses_text(payload: Mapping[str, object]) -> str:
    output = payload.get("output")
    parts: list[str] = []
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict) or item.get("type") != "message":
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if isinstance(part, dict) and part.get("type") == "output_text":
                    text = part.get("text")
                    if isinstance(text, str):
                        parts.append(text)
    text = "".join(parts).strip()
    if not text:
        raise LadiError("Meta reply had no output text")
    return text


def _int(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


RECORD_CLASSES_TOOL: dict[str, object] = {
    "type": "function",
    "function": {
        "name": "record_classes",
        "description": "Record which LADI classes are visible in the aerial photo.",
        "parameters": classes_schema(),
        "strict": True,
    },
}

BASETEN_URL = "https://inference.baseten.co/v1/chat/completions"


class BasetenLadiClassifier:
    """Open-weight Muse Spark Open on Baseten with a ``record_classes`` tool call."""

    provider = "baseten"

    def __init__(
        self,
        *,
        transport: ChatTransport | None = None,
        api_key: str | None = None,
        model: str = BASETEN_MODEL_ID,
        ledger: UsageLedger | None = None,
        reasoning_effort: str = "low",
        max_tokens: int = 4096,
    ) -> None:
        self._transport = transport
        self._api_key = api_key
        self._model = model
        self._ledger = ledger if ledger is not None else UsageLedger()
        self._effort = reasoning_effort
        self._max_tokens = max_tokens

    @property
    def model(self) -> str:
        return self._model

    def request_body(self, jpeg: bytes, max_tokens: int | None = None) -> dict[str, object]:
        return {
            "model": self._model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": classification_prompt()},
                        {"type": "image_url", "image_url": {"url": _data_url(jpeg)}},
                    ],
                }
            ],
            "tools": [RECORD_CLASSES_TOOL],
            "tool_choice": "auto",
            "reasoning_effort": self._effort,
            "max_tokens": self._max_tokens if max_tokens is None else max_tokens,
        }

    def classify(self, jpeg: bytes) -> frozenset[str]:
        """One call; a reply cut off by ``max_tokens`` is retried once with double the budget."""
        try:
            return self._classify_once(jpeg, self._max_tokens)
        except _TruncatedReply:
            return self._classify_once(jpeg, self._max_tokens * 2)

    def _classify_once(self, jpeg: bytes, max_tokens: int) -> frozenset[str]:
        body = json.dumps(self.request_body(jpeg, max_tokens)).encode("utf-8")
        self._ledger.check(self.provider)
        headers = {
            "Authorization": f"Bearer {_key(self._api_key, 'BASETEN_API_KEY')}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        response = _json(self._transport_for_call().post(BASETEN_URL, headers, body))
        usage = response.get("usage")
        if isinstance(usage, dict):
            self._ledger(
                UsageRecord(
                    provider=self.provider,
                    model=self._model,
                    input_tokens=_int(usage.get("prompt_tokens")),
                    output_tokens=_int(usage.get("completion_tokens")),
                    reasoning_tokens=None,
                    t_unix=time.time(),
                )
            )
        return parse_classes(_tool_or_text(response))

    def _transport_for_call(self) -> ChatTransport:
        if self._transport is None:
            from surmap.labelling.baseten_muse import _UrllibChatTransport

            self._transport = _UrllibChatTransport(timeout_s=120.0)
        return self._transport


class _TruncatedReply(LadiError):
    """No answer because the completion hit ``max_tokens``."""


def _tool_or_text(response: Mapping[str, object]) -> Mapping[str, object]:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise LadiError("Baseten reply had no choices")
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise LadiError("Baseten reply had no message")
    calls = message.get("tool_calls")
    if isinstance(calls, list):
        for call in calls:
            function = call.get("function") if isinstance(call, dict) else None
            if isinstance(function, dict) and function.get("name") == "record_classes":
                arguments = function.get("arguments")
                if isinstance(arguments, str):
                    return _json(arguments.encode("utf-8"))
                if isinstance(arguments, dict):
                    return {str(key): value for key, value in arguments.items()}
    content = message.get("content")
    if isinstance(content, str) and "{" in content:
        return _json(content[content.index("{") : content.rindex("}") + 1].encode("utf-8"))
    finish_reason = choices[0].get("finish_reason")
    if finish_reason == "length":
        raise _TruncatedReply("Baseten reply hit max_tokens before a record_classes call")
    raise LadiError(
        f"Baseten reply had neither a record_classes call nor JSON text "
        f"(finish_reason={finish_reason})"
    )


@dataclass(frozen=True)
class ClassScore:
    name: str
    support: int
    true_positive: int
    false_positive: int
    false_negative: int

    @property
    def precision(self) -> float:
        predicted = self.true_positive + self.false_positive
        return self.true_positive / predicted if predicted else 0.0

    @property
    def recall(self) -> float:
        return self.true_positive / self.support if self.support else 0.0

    @property
    def f1(self) -> float:
        denominator = 2 * self.true_positive + self.false_positive + self.false_negative
        return 2 * self.true_positive / denominator if denominator else 0.0


@dataclass(frozen=True)
class Scores:
    classes: tuple[ClassScore, ...]
    images: int
    failures: int

    @property
    def macro_f1(self) -> float:
        scored = [score for score in self.classes if score.support]
        return sum(score.f1 for score in scored) / len(scored) if scored else 0.0

    @property
    def micro_f1(self) -> float:
        tp = sum(score.true_positive for score in self.classes)
        fp = sum(score.false_positive for score in self.classes)
        fn = sum(score.false_negative for score in self.classes)
        return 2 * tp / (2 * tp + fp + fn) if (tp + fp + fn) else 0.0


def score(
    truth: Sequence[frozenset[str]],
    predicted: Sequence[frozenset[str] | None],
) -> Scores:
    """Per-class counts. A ``None`` prediction is a failed call and is not scored."""
    if len(truth) != len(predicted):
        raise LadiError("truth and predictions differ in length")
    pairs = [(t, p) for t, p in zip(truth, predicted, strict=True) if p is not None]
    classes = tuple(
        ClassScore(
            name=name,
            support=sum(1 for t, _ in pairs if name in t),
            true_positive=sum(1 for t, p in pairs if name in t and name in p),
            false_positive=sum(1 for t, p in pairs if name not in t and name in p),
            false_negative=sum(1 for t, p in pairs if name in t and name not in p),
        )
        for name in LADI_CLASSES
    )
    return Scores(classes=classes, images=len(pairs), failures=len(truth) - len(pairs))


def evaluate(
    samples: Iterable[LadiSample],
    classifier: LadiClassifier,
    *,
    on_error: Callable[[LadiSample, Exception], None] | None = None,
) -> tuple[Scores, list[dict[str, object]]]:
    """Classify each sample; a failed call is reported and skipped, not scored as false."""
    truth: list[frozenset[str]] = []
    predicted: list[frozenset[str] | None] = []
    rows: list[dict[str, object]] = []
    for sample in samples:
        truth.append(sample.labels)
        try:
            guess: frozenset[str] | None = classifier.classify(sample.jpeg)
        except (LadiError, RuntimeError, OSError, ValueError) as exc:
            if on_error is not None:
                on_error(sample, exc)
            guess = None
        predicted.append(guess)
        rows.append(
            {
                "split": sample.split,
                "index": sample.index,
                "truth": sorted(sample.labels),
                "predicted": None if guess is None else sorted(guess),
            }
        )
    return score(truth, predicted), rows


def report_json(scores: Scores, *, provider: str, model: str) -> dict[str, object]:
    return {
        "dataset": DATASET,
        "license": DATASET_LICENSE,
        "provider": provider,
        "model": model,
        "images": scores.images,
        "failures": scores.failures,
        "macro_f1": round(scores.macro_f1, 4),
        "micro_f1": round(scores.micro_f1, 4),
        "classes": [
            {
                "name": item.name,
                "support": item.support,
                "precision": round(item.precision, 4),
                "recall": round(item.recall, 4),
                "f1": round(item.f1, 4),
            }
            for item in scores.classes
        ],
    }


def render_table(scores: Scores, *, provider: str, model: str) -> str:
    lines = [
        f"LADI v2 ({DATASET_LICENSE}) - {provider} {model}",
        f"images scored: {scores.images}, failed calls: {scores.failures}",
        f"{'class':<32}{'support':>8}{'prec':>8}{'recall':>8}{'f1':>8}",
    ]
    for item in scores.classes:
        lines.append(
            f"{item.name:<32}{item.support:>8}{item.precision:>8.2f}"
            f"{item.recall:>8.2f}{item.f1:>8.2f}"
        )
    lines.append(f"macro F1 (classes with support): {scores.macro_f1:.3f}")
    lines.append(f"micro F1: {scores.micro_f1:.3f}")
    return "\n".join(lines)
