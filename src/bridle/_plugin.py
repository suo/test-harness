from __future__ import annotations

import time
from pathlib import Path
from typing import IO

import pytest

from bridle._schema import Outcome, TestFinished, TestStarted

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
    """Pytest plugin that writes one JSONL line per test event, flushing immediately."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._file: IO[str] | None = None

    def open(self) -> None:
        self._file = self.path.open("w", encoding="utf-8")

    def close(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None

    def _write(self, event: TestStarted | TestFinished) -> None:
        assert self._file is not None
        self._file.write(event.model_dump_json() + "\n")
        self._file.flush()

    # ---- pytest hooks ----

    def pytest_sessionstart(self) -> None:
        self.open()

    def pytest_runtest_logstart(self, nodeid: str, location: tuple[str, int | None, str]) -> None:
        """Write a TestStarted event before each test runs.

        If the process crashes mid-test, resolve_events() will synthesize a
        failed TestFinished from this unmatched start event.
        """
        event = TestStarted(
            nodeid=nodeid,
            start=time.time(),
            location=location,
        )
        self._write(event)

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

        event = TestFinished(
            nodeid=report.nodeid,
            outcome=outcome,
            when=report.when,
            duration=round(report.duration, 6),
            start=report.start,
            stop=report.stop,
            location=report.location,
            longrepr=longrepr,
            sections=report.sections if report.sections else None,
            wasxfail=getattr(report, "wasxfail", None),
        )
        self._write(event)
