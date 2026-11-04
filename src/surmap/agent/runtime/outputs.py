"""`ToolOutputs`: where a tool result goes when it is too big for the model's context, or when the
call asked for a file.

A result goes to the model as compact JSON when it fits under `max_inline_bytes`. Otherwise, or
when the call's `output.to_file` asked for it, the result is saved as pretty-printed JSON (one
value per line, so `read_file` and `grep_files` work on it by line). The model then reads a short
reference instead: the file's path, its size and line count, why it was saved, and a preview. A
`ToolOutputs` with no directory keeps every result inline.

Each conversation saves into its own folder under the server's root (`child`), and each subagent
into a folder under its conversation's. File names carry a random suffix: job ids restart at `j-1`
when a conversation is restored, and an older reference must keep pointing at its own file.
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

__all__ = ["DEFAULT_MAX_INLINE_BYTES", "PREVIEW_CHARS", "ToolOutputs"]

DEFAULT_MAX_INLINE_BYTES = 16 * 1024
"""Bytes of compact JSON a result may be and still go to the model whole."""

PREVIEW_CHARS = 600
"""How much of a saved file the reference shows."""

_HINT = "Read it with read_file (offset and limit by line) or search it with grep_files."
_UNSAFE = re.compile(r"[^A-Za-z0-9_-]")


@dataclass(frozen=True)
class ToolOutputs:
    """The folder a runner saves large or requested results into, and the inline limit."""

    directory: Path | None = None
    """Where results are saved; None keeps every result inline."""
    max_inline_bytes: int = DEFAULT_MAX_INLINE_BYTES

    def child(self, name: str) -> ToolOutputs:
        """The outputs of a conversation or subagent `name`, in a folder directly under this one.

        Any character other than a letter, digit, `_` or `-` becomes `_`, so `name` can never
        climb out of this folder.
        """
        if self.directory is None:
            return self
        return ToolOutputs(self.directory / _safe(name), self.max_inline_bytes)

    def render(
        self,
        job_id: str,
        tool: str,
        result: Mapping[str, object],
        *,
        to_file: bool,
        auto: bool = True,
    ) -> str:
        """What the model reads for `result`: the result itself, or a reference to its file.

        The result is saved when `to_file` asks for it, or when `auto` is set and its compact
        JSON is over `max_inline_bytes`; never when this has no directory.
        """
        inline = json.dumps(result, default=str)
        over = auto and len(inline.encode("utf-8")) > self.max_inline_bytes
        if self.directory is None or not (to_file or over):
            return inline
        reason = (
            "requested" if to_file else f"over the inline limit of {self.max_inline_bytes} bytes"
        )
        return json.dumps(self._save(job_id, tool, result, reason))

    def _save(
        self, job_id: str, tool: str, result: Mapping[str, object], reason: str
    ) -> dict[str, object]:
        assert self.directory is not None
        pretty = json.dumps(result, indent=2, default=str, ensure_ascii=False) + "\n"
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{_safe(job_id)}-{_safe(tool)}-{uuid.uuid4().hex[:8]}.json"
        path.write_text(pretty, encoding="utf-8")
        return {
            "saved_to_file": str(path),
            "reason": reason,
            "bytes": len(pretty.encode("utf-8")),
            "lines": len(pretty.splitlines()),
            "preview": pretty[:PREVIEW_CHARS],
            "hint": _HINT,
        }


def _safe(name: str) -> str:
    return _UNSAFE.sub("_", name) or "_"
