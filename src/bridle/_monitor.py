from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from bridle._schema import (
    Outcome,
    TestFinished,
    TestStarted,
    _event_adapter,
    append_event,
    test_timeout_repr,
    total_timeout_repr,
)

logger = logging.getLogger(__name__)


@runtime_checkable
class Clock(Protocol):
    def monotonic(self) -> float: ...
    def sleep(self, seconds: float) -> None: ...


class WallClock:
    """Production clock using time.monotonic / time.sleep."""

    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


@runtime_checkable
class Process(Protocol):
    def poll(self) -> int | None: ...
    def kill(self) -> None: ...
    def wait(self, timeout: float | None = None) -> int: ...


@dataclass
class TimeoutResult:
    """Information about a timeout that caused a process kill."""

    kind: str  # "test" or "total"
    nodeid: str | None  # set for per-test timeout
    limit: float
    elapsed: float


def monitor_subprocess(
    proc: Process,
    results_path: Path,
    *,
    test_timeout_sec: float | None = None,
    total_timeout_sec: float | None = None,
    clock: Clock | None = None,
    poll_interval: float = 0.5,
) -> tuple[int, TimeoutResult | None]:
    """Monitor a subprocess, enforcing per-test and total timeouts.

    Returns (exit_code, timeout_result). timeout_result is None if the process
    exited normally without hitting a timeout.
    """
    if clock is None:
        clock = WallClock()

    run_start = clock.monotonic()
    file_offset = 0  # byte offset for tailing the JSONL file

    # Track active tests: nodeid -> (TestStarted, monotonic start time)
    active_tests: dict[str, tuple[TestStarted, float]] = {}

    while True:
        # Check if the process has exited.
        exit_code = proc.poll()
        if exit_code is not None:
            return exit_code, None

        # Tail new events from the JSONL file.
        file_offset = _read_new_events(results_path, file_offset, active_tests, clock)

        now = clock.monotonic()

        # Check per-test timeout.
        if test_timeout_sec is not None:
            for nodeid, (started, mono_start) in list(active_tests.items()):
                elapsed = now - mono_start
                if elapsed >= test_timeout_sec:
                    timeout = TimeoutResult(
                        kind="test",
                        nodeid=nodeid,
                        limit=test_timeout_sec,
                        elapsed=elapsed,
                    )
                    return _kill_and_record(
                        proc, results_path, active_tests, timeout, clock
                    )

        # Check total timeout.
        if total_timeout_sec is not None:
            total_elapsed = now - run_start
            if total_elapsed >= total_timeout_sec:
                timeout = TimeoutResult(
                    kind="total",
                    nodeid=None,
                    limit=total_timeout_sec,
                    elapsed=total_elapsed,
                )
                return _kill_and_record(
                    proc, results_path, active_tests, timeout, clock
                )

        clock.sleep(poll_interval)


def _read_new_events(
    path: Path,
    offset: int,
    active_tests: dict[str, tuple[TestStarted, float]],
    clock: Clock,
) -> int:
    """Read new JSONL lines from offset, update active_tests. Returns new offset."""
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return offset

    if len(data) <= offset:
        return offset

    new_bytes = data[offset:]
    new_offset = len(data)

    for line in new_bytes.decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = _event_adapter.validate_json(line)
        except Exception:
            continue

        if isinstance(event, TestStarted):
            active_tests[event.nodeid] = (event, clock.monotonic())
        elif isinstance(event, TestFinished):
            active_tests.pop(event.nodeid, None)

    return new_offset


def _kill_and_record(
    proc: Process,
    results_path: Path,
    active_tests: dict[str, tuple[TestStarted, float]],
    timeout: TimeoutResult,
    clock: Clock,
) -> tuple[int, TimeoutResult]:
    """Kill the process and write TestFinished events for all active tests."""
    proc.kill()
    try:
        exit_code = proc.wait(timeout=5.0)
    except Exception:
        exit_code = -9

    now = clock.monotonic()

    for nodeid, (started, mono_start) in active_tests.items():
        elapsed = now - mono_start
        stop = started.start + elapsed

        if timeout.kind == "test":
            longrepr = test_timeout_repr(timeout.limit, elapsed)
        else:
            longrepr = total_timeout_repr(timeout.limit, elapsed)

        finished = TestFinished(
            nodeid=nodeid,
            outcome=Outcome.FAILED,
            when="call",
            duration=elapsed,
            start=started.start,
            stop=stop,
            location=started.location,
            longrepr=longrepr,
        )
        append_event(results_path, finished)

    return exit_code, timeout
