"""Pytest plugin that writes JSONL test events.

This module intentionally avoids importing pydantic so that the subprocess
only needs pytest installed.  Plain dicts + stdlib json are used instead.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import IO

import pytest

# Map pytest outcome strings to plain strings.
_OUTCOME_MAP: dict[str, str] = {
    "passed": "passed",
    "failed": "failed",
    "skipped": "skipped",
}


def _map_outcome(report: pytest.TestReport) -> str:
    if hasattr(report, "wasxfail"):
        if report.passed:
            return "xpassed"
        return "xfailed"
    return _OUTCOME_MAP.get(report.outcome, "error")


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

    def _write(self, event: dict) -> None:
        assert self._file is not None
        self._file.write(json.dumps(event) + "\n")
        self._file.flush()

    # ---- pytest hooks ----

    def pytest_sessionstart(self) -> None:
        self.open()

    def pytest_runtest_logstart(self, nodeid: str, location: tuple[str, int | None, str]) -> None:
        """Write a TestStarted event before each test runs.

        If the process crashes mid-test, resolve_events() will synthesize a
        failed TestFinished from this unmatched start event.
        """
        event = {
            "type": "test_started",
            "nodeid": nodeid,
            "start": time.time(),
            "location": list(location) if location is not None else None,
        }
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
            outcome = "error"
        else:
            return

        longrepr: str | None = None
        if report.failed or outcome == "error":
            longrepr = str(report.longrepr) if report.longrepr else None

        event = {
            "type": "test_finished",
            "nodeid": report.nodeid,
            "outcome": outcome,
            "when": report.when,
            "duration": round(report.duration, 6),
            "start": report.start,
            "stop": report.stop,
            "location": list(report.location) if report.location is not None else None,
            "longrepr": longrepr,
            "sections": report.sections if report.sections else None,
            "wasxfail": getattr(report, "wasxfail", None),
        }
        self._write(event)
