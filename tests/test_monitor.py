from __future__ import annotations

from pathlib import Path

from test_harness._monitor import (
    Clock,
    Process,
    TimeoutResult,
    monitor_subprocess,
)
from test_harness._schema import (
    CRASH_REPR,
    Outcome,
    TestFinished,
    TestStarted,
    append_event,
    read_events,
    resolve_events,
    test_timeout_repr as _test_timeout_repr,
    total_timeout_repr as _total_timeout_repr,
)

from conftest import FIXED_START


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

class MockClock:
    """Clock with manually controlled time."""

    def __init__(self, start: float = 0.0) -> None:
        self._now = start

    def monotonic(self) -> float:
        return self._now

    def sleep(self, seconds: float) -> None:
        self._now += seconds

    def advance(self, seconds: float) -> None:
        self._now += seconds


class MockProcess:
    """Simulates a subprocess for monitor_subprocess tests.

    - schedule_events(at_poll, events): write events to JSONL at poll N
    - schedule_exit(after_polls, exit_code): process exits at poll N
    """

    def __init__(self, results_path: Path) -> None:
        self._results_path = results_path
        self._poll_count = 0
        self._scheduled_events: dict[int, list[TestStarted | TestFinished]] = {}
        self._exit_at: int | None = None
        self._exit_code: int = 0
        self._killed = False

    def schedule_events(
        self, at_poll: int, events: list[TestStarted | TestFinished]
    ) -> None:
        self._scheduled_events.setdefault(at_poll, []).extend(events)

    def schedule_exit(self, after_polls: int, exit_code: int = 0) -> None:
        self._exit_at = after_polls
        self._exit_code = exit_code

    def poll(self) -> int | None:
        self._poll_count += 1

        # Write scheduled events for this poll iteration.
        for event in self._scheduled_events.get(self._poll_count, []):
            append_event(self._results_path, event)

        if self._killed:
            return -9

        if self._exit_at is not None and self._poll_count >= self._exit_at:
            return self._exit_code

        return None

    def kill(self) -> None:
        self._killed = True

    def wait(self, timeout: float | None = None) -> int:
        if self._killed:
            return -9
        return self._exit_code


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestMonitorNormalExit:
    def test_returns_exit_code_no_timeout(self, tmp_path: Path) -> None:
        results = tmp_path / "results.jsonl"
        results.touch()

        clock = MockClock()
        proc = MockProcess(results)
        proc.schedule_exit(after_polls=2, exit_code=0)

        exit_code, timeout = monitor_subprocess(
            proc,
            results,
            clock=clock,
            poll_interval=0.1,
        )
        assert exit_code == 0
        assert timeout is None

    def test_nonzero_exit_code(self, tmp_path: Path) -> None:
        results = tmp_path / "results.jsonl"
        results.touch()

        clock = MockClock()
        proc = MockProcess(results)
        proc.schedule_exit(after_polls=1, exit_code=1)

        exit_code, timeout = monitor_subprocess(
            proc,
            results,
            clock=clock,
            poll_interval=0.1,
        )
        assert exit_code == 1
        assert timeout is None


class TestMonitorNoTimeoutArgs:
    def test_no_timeout_still_works(self, tmp_path: Path) -> None:
        """Monitor with no timeout args just polls until process exits."""
        results = tmp_path / "results.jsonl"
        results.touch()

        started = TestStarted(nodeid="t::a", start=FIXED_START)
        finished = TestFinished(
            nodeid="t::a",
            outcome=Outcome.PASSED,
            when="call",
            duration=1.0,
            start=FIXED_START,
            stop=FIXED_START + 1.0,
        )

        clock = MockClock()
        proc = MockProcess(results)
        proc.schedule_events(1, [started])
        proc.schedule_events(2, [finished])
        proc.schedule_exit(after_polls=3, exit_code=0)

        exit_code, timeout = monitor_subprocess(
            proc,
            results,
            clock=clock,
            poll_interval=1.0,
        )
        assert exit_code == 0
        assert timeout is None


class TestMonitorPerTestTimeout:
    def test_slow_test_is_killed(self, tmp_path: Path) -> None:
        results = tmp_path / "results.jsonl"
        results.touch()

        started = TestStarted(
            nodeid="t::slow",
            start=FIXED_START,
            location=("test.py", 10, "t::slow"),
        )

        clock = MockClock()
        proc = MockProcess(results)
        # Poll 1: test starts
        proc.schedule_events(1, [started])
        # Process never exits on its own
        proc.schedule_exit(after_polls=999)

        exit_code, timeout = monitor_subprocess(
            proc,
            results,
            test_timeout_sec=5.0,
            clock=clock,
            poll_interval=2.0,  # each sleep advances 2s
        )

        # After poll 1 (time=0): read started, check timeout (elapsed=0), sleep 2s -> time=2
        # After poll 2 (time=2): no new events, check timeout (elapsed=2), sleep 2s -> time=4
        # After poll 3 (time=4): no new events, check timeout (elapsed=4), sleep 2s -> time=6
        # After poll 4 (time=6): elapsed=6 >= 5, timeout fires
        assert timeout is not None
        assert timeout.kind == "test"
        assert timeout.nodeid == "t::slow"
        assert timeout.limit == 5.0

        # Check that a TestFinished was written to the JSONL.
        events = read_events(results)
        finished_events = [e for e in events if isinstance(e, TestFinished)]
        assert len(finished_events) == 1
        assert finished_events[0].nodeid == "t::slow"
        assert finished_events[0].outcome == Outcome.FAILED
        assert "per-test timeout" in (finished_events[0].longrepr or "")
        assert finished_events[0].location == ("test.py", 10, "t::slow")

    def test_fast_test_is_not_killed(self, tmp_path: Path) -> None:
        results = tmp_path / "results.jsonl"
        results.touch()

        started = TestStarted(nodeid="t::fast", start=FIXED_START)
        finished = TestFinished(
            nodeid="t::fast",
            outcome=Outcome.PASSED,
            when="call",
            duration=0.5,
            start=FIXED_START,
            stop=FIXED_START + 0.5,
        )

        clock = MockClock()
        proc = MockProcess(results)
        proc.schedule_events(1, [started])
        proc.schedule_events(2, [finished])
        proc.schedule_exit(after_polls=3, exit_code=0)

        exit_code, timeout = monitor_subprocess(
            proc,
            results,
            test_timeout_sec=10.0,
            clock=clock,
            poll_interval=0.5,
        )
        assert exit_code == 0
        assert timeout is None


class TestMonitorTotalTimeout:
    def test_total_timeout_kills(self, tmp_path: Path) -> None:
        results = tmp_path / "results.jsonl"
        results.touch()

        started = TestStarted(
            nodeid="t::a",
            start=FIXED_START,
            location=("test.py", 1, "t::a"),
        )

        clock = MockClock()
        proc = MockProcess(results)
        proc.schedule_events(1, [started])
        proc.schedule_exit(after_polls=999)

        exit_code, timeout = monitor_subprocess(
            proc,
            results,
            total_timeout_sec=3.0,
            clock=clock,
            poll_interval=1.0,
        )

        # time starts at 0. After poll 1 (0): read start, total_elapsed=0, sleep -> 1
        # After poll 2 (1): total_elapsed=1, sleep -> 2
        # After poll 3 (2): total_elapsed=2, sleep -> 3
        # After poll 4 (3): total_elapsed=3 >= 3, timeout fires
        assert timeout is not None
        assert timeout.kind == "total"
        assert timeout.limit == 3.0

        events = read_events(results)
        finished_events = [e for e in events if isinstance(e, TestFinished)]
        assert len(finished_events) == 1
        assert "total run exceeded timeout" in (finished_events[0].longrepr or "")


class TestMonitorBothTimeouts:
    def test_per_test_fires_before_total(self, tmp_path: Path) -> None:
        """When both are set, per-test fires first if a single test hangs."""
        results = tmp_path / "results.jsonl"
        results.touch()

        started = TestStarted(nodeid="t::hang", start=FIXED_START)

        clock = MockClock()
        proc = MockProcess(results)
        proc.schedule_events(1, [started])
        proc.schedule_exit(after_polls=999)

        exit_code, timeout = monitor_subprocess(
            proc,
            results,
            test_timeout_sec=5.0,
            total_timeout_sec=100.0,
            clock=clock,
            poll_interval=2.0,
        )

        assert timeout is not None
        assert timeout.kind == "test"


class TestMonitorResolveIntegration:
    def test_timeout_events_integrate_with_resolve(self, tmp_path: Path) -> None:
        """Monitor-written TestFinished events are processed by resolve_events
        without producing crash reprs."""
        results = tmp_path / "results.jsonl"
        results.touch()

        started = TestStarted(
            nodeid="t::timeout",
            start=FIXED_START,
            location=("test.py", 5, "t::timeout"),
        )

        clock = MockClock()
        proc = MockProcess(results)
        proc.schedule_events(1, [started])
        proc.schedule_exit(after_polls=999)

        monitor_subprocess(
            proc,
            results,
            test_timeout_sec=3.0,
            clock=clock,
            poll_interval=1.0,
        )

        events = read_events(results)
        resolved = resolve_events(events)

        # Should have exactly one resolved result.
        assert len(resolved) == 1
        r = resolved[0]
        assert r.nodeid == "t::timeout"
        assert r.outcome == Outcome.FAILED
        # Must NOT be the crash repr — it should be the timeout repr.
        assert r.longrepr != CRASH_REPR
        assert "timeout" in (r.longrepr or "").lower()


class TestTimeoutReprHelpers:
    def test_test_timeout_repr(self) -> None:
        s = _test_timeout_repr(10.0, 12.5)
        assert "per-test timeout" in s
        assert "10.0s" in s
        assert "12.5s" in s

    def test_total_timeout_repr(self) -> None:
        s = _total_timeout_repr(60.0, 65.3)
        assert "total run exceeded timeout" in s
        assert "60.0s" in s
        assert "65.3s" in s
