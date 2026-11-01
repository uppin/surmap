"""The streaming sidecar's process seam: a `docker run -i` child over pipes.

`StreamProcess` is what `StreamingRtabmapBackend` drives; tests pass a
scripted double through the backend's `process_factory`.
"""

from __future__ import annotations

import subprocess
import threading
from typing import Protocol


class StreamProcess(Protocol):
    def write(self, data: bytes) -> None: ...
    def close_stdin(self) -> None: ...
    def readline(self) -> bytes: ...
    def terminate(self) -> None: ...
    def wait(self, timeout: float | None = None) -> int | None: ...


class _PopenProcess:
    def __init__(self, argv: list[str]) -> None:
        self._proc = subprocess.Popen(
            argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        self._stderr = bytearray()
        self._stderr_lock = threading.Lock()
        self._stderr_thread = threading.Thread(target=self._drain_stderr, daemon=True)
        self._stderr_thread.start()

    def _drain_stderr(self) -> None:
        """Keep the stderr pipe from filling. A full pipe stalls the sidecar."""
        stderr = self._proc.stderr
        if stderr is None:
            return
        while True:
            chunk = stderr.read(4096)
            if not chunk:
                return
            with self._stderr_lock:
                self._stderr.extend(chunk)
                if len(self._stderr) > 8000:
                    del self._stderr[:-4000]

    def write(self, data: bytes) -> None:
        assert self._proc.stdin is not None
        self._proc.stdin.write(data)
        self._proc.stdin.flush()

    def close_stdin(self) -> None:
        assert self._proc.stdin is not None
        self._proc.stdin.close()

    def readline(self) -> bytes:
        assert self._proc.stdout is not None
        return self._proc.stdout.readline()

    def terminate(self) -> None:
        self._proc.terminate()

    def wait(self, timeout: float | None = None) -> int | None:
        try:
            return self._proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            return None

    def stderr_tail(self) -> str:
        with self._stderr_lock:
            return bytes(self._stderr[-2000:]).decode(errors="replace")


def _default_factory(argv: list[str]) -> StreamProcess:
    return _PopenProcess(argv)
