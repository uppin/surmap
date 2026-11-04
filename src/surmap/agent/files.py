"""`read_file` and `grep_files`: the agent reads and searches its saved tool outputs and the
folders a deployment allows, and nothing else.

The **read roots** are the runner's output folder (`surmap.agent.runtime.outputs`) plus
`extra_roots`, which the deployment supplies (`SURMAP_AGENT_READ_ROOTS`) and a caller never
does. A path arrives from a model, so it is guarded the way `surmap.agent.skills` guards a
skill name. A relative path resolves against the output folder. Every path is `resolve()`d,
symlinks included, and must land inside a root. Grep walks with `os.walk(followlinks=False)`
and checks each file the same way, so a link can lead the search nowhere outside.

Grep is Python's `re`, run in a worker thread so a long search does not block the event loop.
It needs no ripgrep binary or native wheel, so it runs on every OS and architecture the agent
does. Binary files (a NUL in the first 8 KiB) and files over `MAX_GREP_FILE_BYTES` are skipped.

Each result is kept under the runner's inline limit and says when it was cut short. These two
tools are bound with `saves_large_results=False`, so reading a saved file never saves another.
"""

from __future__ import annotations

import asyncio
import fnmatch
import os
import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from surmap.agent.contracts import (
    ExecutionMode,
    ExecutionPolicy,
    OnTimeout,
    ToolContract,
    tool_input_schema,
)
from surmap.agent.runtime.jobs import JobRunner
from surmap.agent.runtime.tools import BoundTool, bind_contract_tool

__all__ = [
    "MAX_GREP_FILE_BYTES",
    "MAX_LINE_CHARS",
    "FileAccessError",
    "ReadRoots",
    "file_contracts",
    "file_tools",
]

MAX_LINE_CHARS = 2_000
"""Characters of one line a read or a match shows; the rest is cut and marked."""

MAX_GREP_FILE_BYTES = 16 * 1024 * 1024
"""Files bigger than this are not searched."""

_DEFAULT_READ_LINES = 200
_MAX_READ_LINES = 2_000
_DEFAULT_MATCHES = 100
_MAX_MATCHES = 1_000
_BINARY_PROBE_BYTES = 8 * 1024
_RESULT_OVERHEAD_BYTES = 512
"""What a result's own fields take beside its content, kept out of the content's budget."""


class FileAccessError(ValueError):
    """A path is outside the read roots, missing, or not a readable text file."""


class ReadRoots:
    """The folders the file tools may read, the first being where relative paths start."""

    def __init__(self, roots: Sequence[Path]) -> None:
        self._roots = tuple(roots)

    @property
    def roots(self) -> tuple[Path, ...]:
        return self._roots

    def resolve(self, path: str) -> Path:
        """`path` resolved, symlinks followed, and proven inside a root.

        Raises `FileAccessError` when there is no root, or when the path lands outside them.
        """
        if not self._roots:
            raise FileAccessError("no readable directories are configured")
        if "\0" in path:
            raise FileAccessError(f"{path!r} is outside the readable directories")
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = self._roots[0] / candidate
        resolved = candidate.resolve()
        if not self.contains(resolved):
            raise FileAccessError(f"{path} is outside the readable directories")
        return resolved

    def contains(self, resolved: Path) -> bool:
        """Whether an already resolved path is inside one of the roots."""
        return any(resolved.is_relative_to(root.resolve()) for root in self._roots)


def file_contracts() -> tuple[ToolContract, ToolContract]:
    """The `read_file` and `grep_files` contracts, in the order the model sees them."""
    return (
        ToolContract(
            name="read_file",
            service="surmap.agent.files",
            method="ReadFile",
            description=(
                "Reads lines of a text file: a tool result that was saved to a file (give the "
                "path its reference names), or a file in a folder this deployment allows. Lines "
                "come numbered; give offset and limit to read a window of a long file."
            ),
            input_schema=tool_input_schema(
                {
                    "path": {
                        "type": "string",
                        "description": "The file: absolute, or relative to your saved outputs.",
                    },
                    "offset": {
                        "type": "integer",
                        "minimum": 1,
                        "description": "The first line to read, from 1; the default is 1.",
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": _MAX_READ_LINES,
                        "description": f"How many lines to read; the default is "
                        f"{_DEFAULT_READ_LINES}.",
                    },
                },
                required=("path",),
            ),
            default_execution=_DEFAULT_EXECUTION,
        ),
        ToolContract(
            name="grep_files",
            service="surmap.agent.files",
            method="GrepFiles",
            description=(
                "Searches text files for lines matching a regular expression (Python syntax): "
                "your saved tool results and the folders this deployment allows. Each match "
                "gives its file, line number and text; read around it with read_file."
            ),
            input_schema=tool_input_schema(
                {
                    "pattern": {"type": "string", "description": "The regular expression."},
                    "path": {
                        "type": "string",
                        "description": "A file or folder to search; every readable folder "
                        "when left out.",
                    },
                    "glob": {
                        "type": "string",
                        "description": "Only files whose name matches, e.g. *.json.",
                    },
                    "ignore_case": {"type": "boolean", "description": "Match case-insensitively."},
                    "max_matches": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": _MAX_MATCHES,
                        "description": f"Stop after this many matches; the default is "
                        f"{_DEFAULT_MATCHES}.",
                    },
                },
                required=("pattern",),
            ),
            default_execution=_DEFAULT_EXECUTION,
        ),
    )


_DEFAULT_EXECUTION = ExecutionPolicy(
    mode=ExecutionMode.SYNC, timeout_s=30, on_timeout=OnTimeout.FAIL
)


def file_tools(runner: JobRunner, *, extra_roots: Sequence[Path] = ()) -> tuple[BoundTool, ...]:
    """`read_file` and `grep_files` over the runner's output folder and `extra_roots`."""
    own = runner.outputs.directory
    roots = ReadRoots((*((own,) if own is not None else ()), *extra_roots))
    budget = max(runner.outputs.max_inline_bytes - _RESULT_OVERHEAD_BYTES, 256)

    async def read_file(arguments: Mapping[str, object]) -> Mapping[str, object]:
        path = _string(arguments, "path")
        offset = _count(arguments, "offset", 1, maximum=None)
        limit = _count(arguments, "limit", _DEFAULT_READ_LINES, maximum=_MAX_READ_LINES)
        return await asyncio.to_thread(_read, roots, path, offset, limit, budget)

    async def grep_files(arguments: Mapping[str, object]) -> Mapping[str, object]:
        search = _Search(
            pattern=_pattern(arguments),
            path=_optional_string(arguments, "path"),
            glob=_optional_string(arguments, "glob"),
            max_matches=_count(arguments, "max_matches", _DEFAULT_MATCHES, maximum=_MAX_MATCHES),
            budget=budget,
        )
        return await asyncio.to_thread(_grep, roots, search)

    contracts = {contract.name: contract for contract in file_contracts()}
    return (
        bind_contract_tool(contracts["read_file"], read_file, runner, saves_large_results=False),
        bind_contract_tool(contracts["grep_files"], grep_files, runner, saves_large_results=False),
    )


@dataclass(frozen=True)
class _Search:
    pattern: re.Pattern[str]
    path: str | None
    glob: str | None
    max_matches: int
    budget: int


def _read(roots: ReadRoots, path: str, offset: int, limit: int, budget: int) -> dict[str, object]:
    file = _text_file(roots.resolve(path), path)
    shown: list[str] = []
    used = 0
    total = 0
    truncated = False
    with file.open(encoding="utf-8", errors="replace") as lines:
        for number, line in enumerate(lines, start=1):
            total = number
            if number < offset or truncated:
                continue
            if len(shown) == limit:
                continue
            text = f"{number}\t" + _clip(line.rstrip("\r\n"))
            cost = len(text.encode("utf-8")) + 1
            if used + cost > budget:
                truncated = True
                continue
            shown.append(text)
            used += cost
    start = offset if shown else 0
    return {
        "path": str(file),
        "start_line": start,
        "end_line": start + len(shown) - 1 if shown else 0,
        "total_lines": total,
        "content": "\n".join(shown),
        "truncated": truncated,
    }


def _grep(roots: ReadRoots, search: _Search) -> dict[str, object]:
    starts = [roots.resolve(search.path)] if search.path is not None else list(roots.roots)
    matches: list[dict[str, object]] = []
    used = 0
    searched = 0
    truncated = False
    for file in _files(roots, starts, search.glob):
        if not _searchable(file):
            continue
        searched += 1
        with file.open(encoding="utf-8", errors="replace") as lines:
            for number, line in enumerate(lines, start=1):
                if not search.pattern.search(line):
                    continue
                match: dict[str, object] = {
                    "path": str(file),
                    "line": number,
                    "text": _clip(line.rstrip("\r\n")),
                }
                cost = len(str(match).encode("utf-8"))
                if len(matches) == search.max_matches or used + cost > search.budget:
                    truncated = True
                    break
                matches.append(match)
                used += cost
        if truncated:
            break
    return {"matches": matches, "files_searched": searched, "truncated": truncated}


def _files(roots: ReadRoots, starts: Sequence[Path], glob: str | None) -> Iterator[Path]:
    """Every regular file under `starts` inside the roots, in path order, each once."""
    seen: set[Path] = set()
    for start in starts:
        for file in _walk(start):
            resolved = file.resolve()
            if resolved in seen or not roots.contains(resolved) or not resolved.is_file():
                continue
            if glob is not None and not fnmatch.fnmatch(file.name, glob):
                continue
            seen.add(resolved)
            yield resolved


def _walk(start: Path) -> Iterator[Path]:
    if start.is_file():
        yield start
        return
    for directory, subdirectories, names in os.walk(start, followlinks=False):
        subdirectories.sort()
        for name in sorted(names):
            yield Path(directory) / name


def _text_file(file: Path, asked: str) -> Path:
    if not file.is_file():
        raise FileAccessError(f"no file {asked}")
    if _binary(file):
        raise FileAccessError(f"{asked} is a binary file")
    return file


def _searchable(file: Path) -> bool:
    return file.stat().st_size <= MAX_GREP_FILE_BYTES and not _binary(file)


def _binary(file: Path) -> bool:
    with file.open("rb") as stream:
        return b"\0" in stream.read(_BINARY_PROBE_BYTES)


def _clip(line: str) -> str:
    return line if len(line) <= MAX_LINE_CHARS else line[:MAX_LINE_CHARS] + " …"


def _string(arguments: Mapping[str, object], name: str) -> str:
    value = arguments.get(name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _optional_string(arguments: Mapping[str, object], name: str) -> str | None:
    return _string(arguments, name) if arguments.get(name) is not None else None


def _count(arguments: Mapping[str, object], name: str, default: int, *, maximum: int | None) -> int:
    value = arguments.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive whole number")
    return value if maximum is None else min(value, maximum)


def _pattern(arguments: Mapping[str, object]) -> re.Pattern[str]:
    pattern = _string(arguments, "pattern")
    flags = re.IGNORECASE if arguments.get("ignore_case") is True else 0
    try:
        return re.compile(pattern, flags)
    except re.error as error:
        raise ValueError(f"invalid pattern {pattern!r}: {error}") from error
