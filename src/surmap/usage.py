"""Process-local credit ledger shared by hosted-model clients.

Other agents call an instance as a plain callback. ``check`` refuses the
next request before it is sent when an optional per-provider budget,
read from the environment, is already spent. Totals live in this process;
the JSONL file is the history a later process can report.
"""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast


@dataclass(frozen=True)
class UsageRecord:
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int | None
    t_unix: float


UsageSink = Callable[[UsageRecord], None]


class BudgetExceeded(RuntimeError):
    """The process has already spent this provider's per-run budget."""

    def __init__(self, provider: str, kind: str, limit: int, used: int) -> None:
        self.provider = provider
        self.kind = kind
        self.limit = limit
        self.used = used
        super().__init__(
            f"SurMap {kind} budget for {provider} is {limit}; this process has already used {used}"
        )


@dataclass
class _ProviderTotals:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


def default_usage_log_path() -> Path:
    """``$SURMAP_USAGE_LOG`` when set, otherwise ``~/.surmap/usage.jsonl``."""
    configured = os.environ.get("SURMAP_USAGE_LOG", "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".surmap" / "usage.jsonl"


class UsageLedger:
    """Append-only JSONL sink with in-process per-provider totals."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path).expanduser() if path is not None else default_usage_log_path()
        self._totals: dict[str, _ProviderTotals] = {}
        self._lock = threading.Lock()

    def __call__(self, record: UsageRecord) -> None:
        line = json.dumps(
            {
                "provider": record.provider,
                "model": record.model,
                "input_tokens": record.input_tokens,
                "output_tokens": record.output_tokens,
                "reasoning_tokens": record.reasoning_tokens,
                "t_unix": record.t_unix,
            },
            separators=(",", ":"),
        )
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
            running = self._totals.setdefault(record.provider, _ProviderTotals())
            running.calls += 1
            running.input_tokens += record.input_tokens
            running.output_tokens += record.output_tokens

    def check(self, provider: str) -> None:
        """Raise ``BudgetExceeded`` when this provider's budget is already spent.

        Budgets come from ``SURMAP_BUDGET_<PROVIDER>_CALLS`` and
        ``SURMAP_BUDGET_<PROVIDER>_TOKENS`` (provider upper-cased). An unset
        variable means no limit. Token totals are input plus output;
        reasoning tokens are a subset of output and are not added again.
        """
        calls_limit = _budget_limit(provider, "CALLS")
        tokens_limit = _budget_limit(provider, "TOKENS")
        with self._lock:
            running = self._totals.get(provider, _ProviderTotals())
            calls = running.calls
            tokens = running.input_tokens + running.output_tokens
        if calls_limit is not None and calls >= calls_limit:
            raise BudgetExceeded(provider, "calls", calls_limit, calls)
        if tokens_limit is not None and tokens >= tokens_limit:
            raise BudgetExceeded(provider, "tokens", tokens_limit, tokens)

    def calls(self, provider: str) -> int:
        with self._lock:
            return self._totals.get(provider, _ProviderTotals()).calls

    def total_tokens(self, provider: str) -> int:
        with self._lock:
            running = self._totals.get(provider, _ProviderTotals())
            return running.input_tokens + running.output_tokens


def _budget_limit(provider: str, suffix: str) -> int | None:
    name = f"SURMAP_BUDGET_{provider.upper()}_{suffix}"
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return None
    try:
        value = int(raw.strip())
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from exc
    if value < 0:
        raise ValueError(f"{name} must be zero or positive, got {value}")
    return value


def render_usage_report(path: Path) -> str:
    """Totals per UTC day, provider, and model. Missing logs say so."""
    if not path.is_file():
        return "No credit usage recorded.\n"
    buckets: dict[tuple[str, str, str], _ProviderTotals] = {}
    reasoning: dict[tuple[str, str, str], int] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        row = _load_usage_line(line, line_number)
        key = (_day(row), _text(row, "provider", line_number), _text(row, "model", line_number))
        running = buckets.setdefault(key, _ProviderTotals())
        running.calls += 1
        running.input_tokens += _int_field(row, "input_tokens", line_number)
        running.output_tokens += _int_field(row, "output_tokens", line_number)
        reasoning[key] = reasoning.get(key, 0) + _optional_int_field(
            row, "reasoning_tokens", line_number
        )
    if not buckets:
        return "No credit usage recorded.\n"
    lines = ["day provider model calls input_tokens output_tokens reasoning_tokens"]
    for key in sorted(buckets):
        day, provider, model = key
        running = buckets[key]
        lines.append(
            f"{day} {provider} {model} {running.calls} "
            f"{running.input_tokens} {running.output_tokens} {reasoning.get(key, 0)}"
        )
    return "\n".join(lines) + "\n"


def _load_usage_line(line: str, line_number: int) -> dict[str, object]:
    try:
        parsed: object = cast(object, json.loads(line))
    except json.JSONDecodeError as exc:
        raise ValueError(f"usage log line {line_number} is not JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"usage log line {line_number} is not an object")
    return {str(key): value for key, value in parsed.items()}


def _day(row: dict[str, object]) -> str:
    value = row.get("t_unix")
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError("usage log line is missing t_unix")
    return datetime.fromtimestamp(float(value), tz=UTC).date().isoformat()


def _text(row: dict[str, object], field: str, line_number: int) -> str:
    value = row.get(field)
    if not isinstance(value, str):
        raise ValueError(f"usage log line {line_number} field {field} was not text")
    return value


def _int_field(row: dict[str, object], field: str, line_number: int) -> int:
    value = row.get(field, 0)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"usage log line {line_number} field {field} was not an integer")
    return value


def _optional_int_field(row: dict[str, object], field: str, line_number: int) -> int:
    value = row.get(field)
    if value is None:
        return 0
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"usage log line {line_number} field {field} was not an integer")
    return value
