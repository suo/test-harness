from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import IO

import pytest

from test_harness._schema import Outcome, TestResult

# Map pytest outcome strings to our Outcome enum.
_OUTCOME_MAP: dict[str, Outcome] = {
    "passed": Outcome.PASSED,
    "failed": Outcome.FAILED,
    "skipped": Outcome.SKIPPED,
}


def _map_outcome(report: pytest.TestReport) -> Outcome:
    if hasattr(report, "wasxfail"):
        if report.passed:
            return Outcome.XPASSED
        return Outcome.XFAILED
    return _OUTCOME_MAP.get(report.outcome, Outcome.ERROR)


class TestResultPlugin:
    """Pytest plugin that writes one JSONL line per test result, flushing immediately."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._file: IO[str] | None = None

    def open(self) -> None:
        self._file = self.path.open("w", encoding="utf-8")

    def close(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None

    def _write(self, result: TestResult) -> None:
        assert self._file is not None
        self._file.write(result.to_json_line() + "\n")
        self._file.flush()

    # ---- pytest hooks ----

    def pytest_sessionstart(self) -> None:
        self.open()

    def pytest_sessionfinish(self) -> None:
        self.close()

    @pytest.hookimpl(tryfirst=True)
    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        # Record the "call" phase for normal results.
        if report.when == "call":
            outcome = _map_outcome(report)
        elif report.when == "setup" and report.skipped:
            # Skips (and xfails) are reported during setup with skipped outcome.
            outcome = _map_outcome(report)
        elif report.failed:
            # setup or teardown error
            outcome = Outcome.ERROR
        else:
            return

        longrepr: str | None = None
        if report.failed or outcome in (Outcome.ERROR,):
            longrepr = str(report.longrepr) if report.longrepr else None

        result = TestResult(
            node_id=report.nodeid,
            outcome=outcome,
            duration_seconds=round(report.duration, 6),
            timestamp=datetime.now(timezone.utc),
            longrepr=longrepr,
        )
        self._write(result)
