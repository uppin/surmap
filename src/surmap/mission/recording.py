"""Record live model calls once, replay them offline.

``--record <dir>`` on ``scripts/mission_demo.py --live`` wraps every
model transport in a recorder. Each call is written to
``calls.jsonl`` with its role, provider, model, URL, the request with
auth headers dropped and media replaced by a size and hash, the full
response, and the UTC time it was received. Key values from the
environment are scrubbed from every string before it is written.

Replay transports hand those responses back in order, so the real
clients parse a real response without opening a socket.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

RECORDING_SCHEMA = "surmap.model_recording.v1"
CALLS_FILE = "calls.jsonl"
MANIFEST_FILE = "manifest.json"
SNAPSHOT_FILE = "semantic_map_snapshot.json"
IMPACT_FILE = "impact.json"

_SECRET_ENV = (
    "MODEL_API_KEY",
    "BASETEN_API_KEY",
    "MODAL_PROXY_TOKEN_ID",
    "MODAL_PROXY_TOKEN_SECRET",
    "HF_TOKEN",
)
_PRIVATE_URL_ENV = ("MODAL_SAM_URL", "MODAL_MUSE_URL")
_SAFE_HEADERS = frozenset({"content-type", "accept"})
_MEDIA_MIN_CHARS = 512
_REDACTED = "<redacted>"

Poster = Callable[[str, bytes], bytes]


class RecordingError(RuntimeError):
    """A recording is missing, malformed, or used up."""


@dataclass(frozen=True)
class RecordedCall:
    """One request and its response, as written to ``calls.jsonl``."""

    seq: int
    role: str
    provider: str
    model: str
    url: str
    request: Mapping[str, object]
    response: Mapping[str, object]
    recorded_at: str
    elapsed_s: float

    def to_json(self) -> dict[str, object]:
        return {
            "seq": self.seq,
            "role": self.role,
            "provider": self.provider,
            "model": self.model,
            "url": self.url,
            "request": dict(self.request),
            "response": dict(self.response),
            "recorded_at": self.recorded_at,
            "elapsed_s": self.elapsed_s,
        }

    @property
    def source(self) -> str:
        """The label the viewer and report show for this response."""
        return f"recorded live response from {self.model or self.provider} at {self.recorded_at}"


def utc_stamp(t_unix: float) -> str:
    """ISO 8601 UTC with a trailing ``Z``, to the second."""
    return datetime.fromtimestamp(t_unix, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class CallRecorder:
    """Thread-safe list of redacted calls."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.time,
        secrets: Sequence[str] | None = None,
        private_urls: Sequence[str] | None = None,
    ) -> None:
        self._clock = clock
        self._secrets = tuple(
            value
            for value in (
                secrets
                if secrets is not None
                else [os.environ.get(name, "").strip() for name in _SECRET_ENV]
            )
            if len(value) >= 4
        )
        self._private_urls = tuple(
            value
            for value in (
                private_urls
                if private_urls is not None
                else [os.environ.get(name, "").strip() for name in _PRIVATE_URL_ENV]
            )
            if value
        )
        self._calls: list[RecordedCall] = []
        self._lock = threading.Lock()

    @property
    def calls(self) -> tuple[RecordedCall, ...]:
        with self._lock:
            return tuple(self._calls)

    def add(
        self,
        *,
        role: str,
        provider: str,
        url: str,
        headers: Mapping[str, str],
        request: Mapping[str, object],
        response: Mapping[str, object],
        elapsed_s: float,
    ) -> RecordedCall:
        kept_headers = {
            name: value for name, value in headers.items() if name.casefold() in _SAFE_HEADERS
        }
        body = _summarise_media(dict(request))
        model = request.get("model")
        record_request: dict[str, object] = {"headers": kept_headers, "body": body}
        with self._lock:
            call = RecordedCall(
                seq=len(self._calls) + 1,
                role=role,
                provider=provider,
                model=self._scrub(model) if isinstance(model, str) else "",
                url=self._scrub(url),
                request=self._scrub_tree(record_request),
                response=self._scrub_tree(dict(response)),
                recorded_at=utc_stamp(self._clock()),
                elapsed_s=round(max(elapsed_s, 0.0), 4),
            )
            self._calls.append(call)
        return call

    def scrub_text(self, text: str) -> str:
        """``text`` with private endpoint URLs and known key values replaced."""
        return self._scrub(text)

    def _scrub(self, text: str) -> str:
        for url in self._private_urls:
            text = text.replace(url, "<private-endpoint>")
        for secret in self._secrets:
            text = text.replace(secret, _REDACTED)
        return text

    def _scrub_tree(self, value: dict[str, object]) -> dict[str, object]:
        scrubbed = json.loads(self._scrub(json.dumps(value)))
        if not isinstance(scrubbed, dict):
            raise RecordingError("recorded body is not a JSON object")
        return scrubbed


def _summarise_media(value: object) -> object:
    """Replace data URLs and long base64 strings with their size and hash."""
    if isinstance(value, dict):
        return {str(key): _summarise_media(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_summarise_media(item) for item in value]
    if isinstance(value, str) and len(value) >= _MEDIA_MIN_CHARS:
        kind = value.split(",", 1)[0] if value.startswith("data:") else "text"
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
        return f"<{kind} omitted: {len(value)} chars, sha256 {digest}>"
    return value


def write_calls(path: Path, calls: Sequence[RecordedCall]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(call.to_json(), sort_keys=True) for call in calls]
    path.write_text("".join(line + "\n" for line in lines), encoding="utf-8")


def read_calls(path: Path) -> tuple[RecordedCall, ...]:
    if not path.is_file():
        raise RecordingError(f"no recorded calls at {path}")
    calls: list[RecordedCall] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        raw = json.loads(line)
        if not isinstance(raw, dict):
            raise RecordingError(f"{path}:{number} is not a JSON object")
        calls.append(_call_from_json(raw, f"{path}:{number}"))
    return tuple(calls)


def _call_from_json(raw: Mapping[str, object], where: str) -> RecordedCall:
    def text(name: str) -> str:
        value = raw.get(name)
        if not isinstance(value, str):
            raise RecordingError(f"{where}: {name} must be a string")
        return value

    def mapping(name: str) -> Mapping[str, object]:
        value = raw.get(name)
        if not isinstance(value, dict):
            raise RecordingError(f"{where}: {name} must be an object")
        return value

    seq = raw.get("seq")
    elapsed = raw.get("elapsed_s")
    if not isinstance(seq, int) or isinstance(seq, bool):
        raise RecordingError(f"{where}: seq must be an integer")
    if not isinstance(elapsed, int | float) or isinstance(elapsed, bool):
        raise RecordingError(f"{where}: elapsed_s must be a number")
    return RecordedCall(
        seq=seq,
        role=text("role"),
        provider=text("provider"),
        model=text("model"),
        url=text("url"),
        request=mapping("request"),
        response=mapping("response"),
        recorded_at=text("recorded_at"),
        elapsed_s=float(elapsed),
    )


class ReplayQueue:
    """Responses for one role, handed back in recorded order."""

    def __init__(self, calls: Sequence[RecordedCall], role: str) -> None:
        self.role = role
        self._pending = [call for call in calls if call.role == role]
        self._lock = threading.Lock()
        self.used: list[RecordedCall] = []

    def next(self) -> RecordedCall:
        with self._lock:
            if not self._pending:
                raise RecordingError(f"recording has no more {self.role!r} responses")
            call = self._pending.pop(0)
            self.used.append(call)
            return call


def _json_object(raw: bytes) -> dict[str, object]:
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"non_json_bytes": len(raw)}
    return parsed if isinstance(parsed, dict) else {"json": parsed}


class _MetaMusePost(Protocol):
    def post_json(
        self, url: str, headers: Mapping[str, str], body: Mapping[str, object]
    ) -> Mapping[str, object]: ...


class _MetaResponsesPost(Protocol):
    def post(
        self, url: str, headers: Mapping[str, str], payload: Mapping[str, object]
    ) -> Mapping[str, object]: ...


class _ChatPost(Protocol):
    def post(self, url: str, headers: Mapping[str, str], body: bytes) -> bytes: ...


class RecordingMetaMuseTransport:
    """``MetaMuseTransport`` that records each call it forwards."""

    def __init__(
        self, inner: _MetaMusePost, recorder: CallRecorder, *, role: str, provider: str = "meta"
    ) -> None:
        self._inner = inner
        self._recorder = recorder
        self._role = role
        self._provider = provider

    def post_json(
        self, url: str, headers: Mapping[str, str], body: Mapping[str, object]
    ) -> Mapping[str, object]:
        started = time.perf_counter()
        response = self._inner.post_json(url, headers, body)
        self._recorder.add(
            role=self._role,
            provider=self._provider,
            url=url,
            headers=headers,
            request=body,
            response=response,
            elapsed_s=time.perf_counter() - started,
        )
        return response


class RecordingMetaResponsesTransport:
    """``MetaResponsesTransport`` (SAM) that records each call it forwards."""

    def __init__(self, inner: _MetaResponsesPost, recorder: CallRecorder, *, role: str) -> None:
        self._inner = inner
        self._recorder = recorder
        self._role = role

    def post(
        self, url: str, headers: Mapping[str, str], payload: Mapping[str, object]
    ) -> Mapping[str, object]:
        started = time.perf_counter()
        response = self._inner.post(url, headers, payload)
        self._recorder.add(
            role=self._role,
            provider="meta",
            url=url,
            headers=headers,
            request=payload,
            response=response,
            elapsed_s=time.perf_counter() - started,
        )
        return response


class RecordingChatTransport:
    """Baseten ``ChatTransport`` that records each call it forwards."""

    def __init__(
        self, inner: _ChatPost, recorder: CallRecorder, *, role: str, provider: str = "baseten"
    ) -> None:
        self._inner = inner
        self._recorder = recorder
        self._role = role
        self._provider = provider

    def post(self, url: str, headers: Mapping[str, str], body: bytes) -> bytes:
        started = time.perf_counter()
        raw = self._inner.post(url, headers, body)
        self._recorder.add(
            role=self._role,
            provider=self._provider,
            url=url,
            headers=headers,
            request=_json_object(body),
            response=_json_object(raw),
            elapsed_s=time.perf_counter() - started,
        )
        return raw


def recording_poster(inner: Poster, recorder: CallRecorder, *, role: str, model: str) -> Poster:
    """Modal SAM ``Poster`` that records each call it forwards."""

    def send(url: str, body: bytes) -> bytes:
        started = time.perf_counter()
        raw = inner(url, body)
        request = _json_object(body)
        request.setdefault("model", model)
        recorder.add(
            role=role,
            provider="modal",
            url=url,
            headers={"Content-Type": "application/json"},
            request=request,
            response=_json_object(raw),
            elapsed_s=time.perf_counter() - started,
        )
        return raw

    return send


class ReplayMetaMuseTransport:
    """``MetaMuseTransport`` that returns recorded responses."""

    def __init__(self, queue: ReplayQueue) -> None:
        self._queue = queue

    def post_json(
        self, url: str, headers: Mapping[str, str], body: Mapping[str, object]
    ) -> Mapping[str, object]:
        del url, headers, body
        return self._queue.next().response


class ReplayMetaResponsesTransport:
    """``MetaResponsesTransport`` that returns recorded responses."""

    def __init__(self, queue: ReplayQueue) -> None:
        self._queue = queue

    def post(
        self, url: str, headers: Mapping[str, str], payload: Mapping[str, object]
    ) -> Mapping[str, object]:
        del url, headers, payload
        return self._queue.next().response


class ReplayChatTransport:
    """Baseten ``ChatTransport`` that returns recorded responses."""

    def __init__(self, queue: ReplayQueue) -> None:
        self._queue = queue

    def post(self, url: str, headers: Mapping[str, str], body: bytes) -> bytes:
        del url, headers, body
        return json.dumps(dict(self._queue.next().response)).encode("utf-8")


def replay_poster(queue: ReplayQueue) -> Poster:
    def send(url: str, body: bytes) -> bytes:
        del url, body
        return json.dumps(dict(queue.next().response)).encode("utf-8")

    return send


@dataclass(frozen=True)
class Recording:
    """A recorded live mission on disk."""

    root: Path
    manifest: Mapping[str, object]
    calls: tuple[RecordedCall, ...]

    @property
    def snapshot_path(self) -> Path:
        return self.root / SNAPSHOT_FILE

    @property
    def impact_path(self) -> Path:
        return self.root / IMPACT_FILE

    @property
    def recorded_at(self) -> str:
        value = self.manifest.get("recorded_at")
        return value if isinstance(value, str) else ""


def has_recording(root: Path) -> bool:
    return (root / MANIFEST_FILE).is_file()


def load_recording(root: Path) -> Recording:
    manifest_path = root / MANIFEST_FILE
    if not manifest_path.is_file():
        raise RecordingError(f"no recording manifest at {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or manifest.get("schema") != RECORDING_SCHEMA:
        raise RecordingError(f"{manifest_path} is not a {RECORDING_SCHEMA} manifest")
    for name in (SNAPSHOT_FILE, IMPACT_FILE):
        if not (root / name).is_file():
            raise RecordingError(f"recording is missing {name}")
    return Recording(root, manifest, read_calls(root / CALLS_FILE))


def write_recording(
    root: Path,
    recorder: CallRecorder,
    *,
    snapshot_path: Path,
    impact_path: Path,
    capture_name: str,
    services: Mapping[str, str],
    clock: Callable[[], float] = time.time,
) -> Recording:
    """Write calls, manifest, and copies of the snapshot and report."""
    root.mkdir(parents=True, exist_ok=True)
    calls = recorder.calls
    write_calls(root / CALLS_FILE, calls)
    snapshot_text = recorder.scrub_text(snapshot_path.read_text(encoding="utf-8"))
    (root / SNAPSHOT_FILE).write_text(snapshot_text, encoding="utf-8")
    impact = json.loads(recorder.scrub_text(impact_path.read_text(encoding="utf-8")))
    if isinstance(impact, dict):
        impact.pop("euroc_session", None)  # a local path, not part of the result
    (root / IMPACT_FILE).write_text(json.dumps(impact, indent=2) + "\n", encoding="utf-8")
    manifest: dict[str, object] = {
        "schema": RECORDING_SCHEMA,
        "recorded_at": calls[0].recorded_at if calls else utc_stamp(clock()),
        "finished_at": utc_stamp(clock()),
        "capture": capture_name,
        "services": dict(services),
        "models": sorted({call.model for call in calls if call.model}),
        "call_count": len(calls),
        "note": "Auth headers are not recorded; media is replaced by its size and hash.",
    }
    (root / MANIFEST_FILE).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return Recording(root, manifest, calls)
