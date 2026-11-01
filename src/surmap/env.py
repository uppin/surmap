"""Project `.env` support: fill `os.environ` gaps from the nearest `.env`.

A deliberately small loader (no `python-dotenv` dependency): it walks
up from `start` (default: the working directory) to the first `.env`,
parses `KEY=value` lines (`export` prefix, `#` comments and single or
double quotes handled), and sets only keys the real environment does
not already define — a shell export always wins over the file. Values
are never returned or logged; the result is the names that were set.
Secrets such as `HF_TOKEN` live in the (git-ignored) file, code reads
them from `os.environ` as usual.
"""

from __future__ import annotations

import os
from pathlib import Path


def _parse(text: str) -> dict[str, str]:
    entries: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        if stripped.startswith("export "):
            stripped = stripped[len("export ") :].lstrip()
        key, _, value = stripped.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if key:
            entries[key] = value
    return entries


def load_env(start: Path | None = None) -> tuple[str, ...]:
    """Set missing env keys from the nearest `.env` at or above `start`.

    Returns the names of the keys that were set (never their values);
    an empty tuple when no `.env` exists.
    """
    directory = (start or Path.cwd()).resolve()
    for candidate in (directory, *directory.parents):
        env_file = candidate / ".env"
        if env_file.is_file():
            loaded: list[str] = []
            for key, value in _parse(env_file.read_text()).items():
                if key not in os.environ:
                    os.environ[key] = value
                    loaded.append(key)
            return tuple(loaded)
    return ()
