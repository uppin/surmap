"""Credit-usage ledger: one JSON line per call, process totals, optional budgets."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from surmap.usage import (
    BudgetExceeded,
    UsageLedger,
    UsageRecord,
    UsageSink,
    default_usage_log_path,
    render_usage_report,
)

_MODEL = "meta-models/muse-spark-open-1026"
_DAY = datetime(2026, 10, 28, 15, 0, tzinfo=UTC)


def a_record(
    *,
    provider: str = "baseten",
    model: str = _MODEL,
    input_tokens: int = 11,
    output_tokens: int = 7,
    reasoning_tokens: int | None = 5,
    t_unix: float | None = None,
) -> UsageRecord:
    return UsageRecord(
        provider,
        model,
        input_tokens,
        output_tokens,
        reasoning_tokens,
        _DAY.timestamp() if t_unix is None else t_unix,
    )


def test_ledger_appends_one_json_line_and_updates_provider_totals(tmp_path: Path) -> None:
    # Given an empty ledger file
    log = tmp_path / "usage.jsonl"
    ledger = UsageLedger(log)
    sink: UsageSink = ledger
    record = a_record()

    # When one record is handed to the sink
    sink(record)

    # Then the file has that JSON object and the process total matches it
    line = json.loads(log.read_text(encoding="utf-8"))
    assert line == {
        "provider": "baseten",
        "model": _MODEL,
        "input_tokens": 11,
        "output_tokens": 7,
        "reasoning_tokens": 5,
        "t_unix": _DAY.timestamp(),
    }
    assert ledger.calls("baseten") == 1
    assert ledger.total_tokens("baseten") == 18


def test_ledger_totals_stay_separate_per_provider(tmp_path: Path) -> None:
    # Given one Baseten call and one Meta call
    ledger = UsageLedger(tmp_path / "usage.jsonl")
    ledger(a_record(provider="baseten", input_tokens=10, output_tokens=1, reasoning_tokens=None))
    ledger(a_record(provider="meta", input_tokens=3, output_tokens=4, reasoning_tokens=None))

    # When the totals are read
    baseten_tokens = ledger.total_tokens("baseten")
    meta_tokens = ledger.total_tokens("meta")

    # Then each provider keeps its own count and a third provider is still zero
    assert ledger.calls("baseten") == 1
    assert ledger.calls("meta") == 1
    assert baseten_tokens == 11
    assert meta_tokens == 7
    assert ledger.calls("modal") == 0
    assert ledger.total_tokens("modal") == 0


def test_a_second_record_appends_instead_of_replacing_the_file(tmp_path: Path) -> None:
    # Given a ledger that already stored one call
    log = tmp_path / "usage.jsonl"
    ledger = UsageLedger(log)
    ledger(a_record(input_tokens=1, output_tokens=1))

    # When a second call is stored
    ledger(a_record(input_tokens=2, output_tokens=3))

    # Then both lines are in the file and the total is their sum
    assert len(log.read_text(encoding="utf-8").splitlines()) == 2
    assert ledger.calls("baseten") == 2
    assert ledger.total_tokens("baseten") == 7


def test_call_budget_raises_when_the_process_is_at_the_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given a Baseten call budget of one and one call already recorded
    ledger = UsageLedger(tmp_path / "usage.jsonl")
    ledger(a_record())
    monkeypatch.setenv("SURMAP_BUDGET_BASETEN_CALLS", "1")

    # When the next Baseten call is checked
    with pytest.raises(BudgetExceeded) as caught:
        ledger.check("baseten")

    # Then the budget names the provider and the calls limit
    assert caught.value.provider == "baseten"
    assert caught.value.kind == "calls"
    assert caught.value.limit == 1
    assert caught.value.used == 1


def test_token_budget_counts_input_plus_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given 110 tokens already recorded and a budget of 100
    ledger = UsageLedger(tmp_path / "usage.jsonl")
    ledger(a_record(input_tokens=80, output_tokens=30, reasoning_tokens=200))
    monkeypatch.setenv("SURMAP_BUDGET_BASETEN_TOKENS", "100")

    # When the next call is checked
    with pytest.raises(BudgetExceeded) as caught:
        ledger.check("baseten")

    # Then reasoning tokens are not added on top of output tokens
    assert caught.value.kind == "tokens"
    assert caught.value.used == 110
    assert caught.value.limit == 100


def test_meta_call_budget_does_not_block_baseten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given a zero call budget for Meta and no Baseten budget
    ledger = UsageLedger(tmp_path / "usage.jsonl")
    monkeypatch.setenv("SURMAP_BUDGET_META_CALLS", "0")
    monkeypatch.delenv("SURMAP_BUDGET_BASETEN_CALLS", raising=False)

    # When Baseten is checked
    ledger.check("baseten")

    # Then the Baseten ledger is still empty
    assert ledger.calls("baseten") == 0


def test_zero_call_budget_blocks_the_provider_before_any_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given a Meta call budget of zero and no recorded calls
    ledger = UsageLedger(tmp_path / "usage.jsonl")
    monkeypatch.setenv("SURMAP_BUDGET_META_CALLS", "0")

    # When Meta is checked
    with pytest.raises(BudgetExceeded) as caught:
        ledger.check("meta")

    # Then the check names Meta and does not create a log
    assert caught.value.provider == "meta"
    assert caught.value.limit == 0
    assert not (tmp_path / "usage.jsonl").exists()


def test_unset_budget_does_not_block(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given no budget variables
    ledger = UsageLedger(tmp_path / "usage.jsonl")
    monkeypatch.delenv("SURMAP_BUDGET_BASETEN_CALLS", raising=False)
    monkeypatch.delenv("SURMAP_BUDGET_BASETEN_TOKENS", raising=False)

    # When Baseten is checked before any call
    ledger.check("baseten")

    # Then the ledger is still empty
    assert ledger.calls("baseten") == 0


def test_non_integer_budget_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given a budget value that is not an integer
    ledger = UsageLedger(tmp_path / "usage.jsonl")
    monkeypatch.setenv("SURMAP_BUDGET_MODAL_TOKENS", "many")

    # When Modal is checked
    with pytest.raises(ValueError, match="SURMAP_BUDGET_MODAL_TOKENS"):
        ledger.check("modal")

    # Then no usage file is created by the failed check
    assert not (tmp_path / "usage.jsonl").exists()


def test_log_path_follows_surmap_usage_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given SURMAP_USAGE_LOG pointing at a file in the test directory
    configured = tmp_path / "credits.jsonl"
    monkeypatch.setenv("SURMAP_USAGE_LOG", str(configured))

    # When a ledger is built without an explicit path
    ledger = UsageLedger()

    # Then that file is where records will be appended
    assert ledger.path == configured


def test_default_log_path_is_under_the_home_surmap_directory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given no path override
    monkeypatch.delenv("SURMAP_USAGE_LOG", raising=False)

    # When the default path is resolved
    path = default_usage_log_path()

    # Then it is ~/.surmap/usage.jsonl
    assert path == Path.home() / ".surmap" / "usage.jsonl"


def test_usage_report_totals_each_provider_model_and_day(tmp_path: Path) -> None:
    # Given two Baseten calls on 28 Oct and one Meta call the same day
    log = tmp_path / "usage.jsonl"
    ledger = UsageLedger(log)
    ledger(a_record(input_tokens=10, output_tokens=5, reasoning_tokens=3))
    ledger(a_record(input_tokens=1, output_tokens=1, reasoning_tokens=None))
    ledger(
        a_record(
            provider="meta",
            model="muse-spark-1.3",
            input_tokens=4,
            output_tokens=4,
            reasoning_tokens=2,
        )
    )
    next_day = datetime(2026, 10, 29, 1, 0, tzinfo=UTC).timestamp()
    ledger(a_record(input_tokens=8, output_tokens=2, reasoning_tokens=1, t_unix=next_day))

    # When the log is rendered
    report = render_usage_report(log)

    # Then each provider, model, and UTC day is its own summed row
    assert report == (
        "day provider model calls input_tokens output_tokens reasoning_tokens\n"
        "2026-10-28 baseten meta-models/muse-spark-open-1026 2 11 6 3\n"
        "2026-10-28 meta muse-spark-1.3 1 4 4 2\n"
        "2026-10-29 baseten meta-models/muse-spark-open-1026 1 8 2 1\n"
    )


def test_usage_report_says_when_the_log_is_missing(tmp_path: Path) -> None:
    # Given no log file
    missing = tmp_path / "missing.jsonl"

    # When the report is rendered
    report = render_usage_report(missing)

    # Then it says nothing was recorded
    assert report == "No credit usage recorded.\n"


def test_usage_report_script_prints_the_log_summary(tmp_path: Path) -> None:
    # Given one recorded call
    log = tmp_path / "usage.jsonl"
    UsageLedger(log)(a_record())
    expected = render_usage_report(log)

    # When the report script is run on that file
    completed = subprocess.run(
        [sys.executable, "scripts/usage_report.py", "--log", str(log)],
        check=True,
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[1],
    )

    # Then its stdout is the same summary
    assert completed.stdout == expected
