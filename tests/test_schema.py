from __future__ import annotations

import pytest
from syrupy.assertion import SnapshotAssertion

from bridle._schema import (
    CRASH_REPR,
    Outcome,
    TestFinished,
    TestStarted,
    read_events,
    resolve_events,
)

from conftest import FIXED_START, FIXED_STOP


class TestTestFinished:
    def test_to_json_snapshot(
        self, sample_results: list[TestFinished], snapshot: SnapshotAssertion
    ) -> None:
        for result in sample_results:
            assert result.model_dump_json() == snapshot

    def test_roundtrip(self, sample_results: list[TestFinished]) -> None:
        for result in sample_results:
            line = result.model_dump_json()
            restored = TestFinished.model_validate_json(line)
            assert restored == result

    def test_outcome_values(self) -> None:
        assert Outcome.PASSED.value == "passed"
        assert Outcome.XPASSED.value == "xpassed"


class TestReadEvents:
    def test_reads_valid_jsonl(self, tmp_path) -> None:
        f = tmp_path / "results.jsonl"
        started = TestStarted(nodeid="t::a", start=FIXED_START)
        finished = TestFinished(
            nodeid="t::a",
            outcome=Outcome.PASSED,
            when="call",
            duration=0.001,
            start=FIXED_START,
            stop=FIXED_STOP,
        )
        f.write_text(started.model_dump_json() + "\n" + finished.model_dump_json() + "\n")
        events = read_events(f)
        assert len(events) == 2
        assert isinstance(events[0], TestStarted)
        assert isinstance(events[1], TestFinished)

    def test_skips_malformed_lines(self, tmp_path) -> None:
        f = tmp_path / "results.jsonl"
        finished = TestFinished(
            nodeid="t::a",
            outcome=Outcome.PASSED,
            when="call",
            duration=0.001,
            start=FIXED_START,
            stop=FIXED_STOP,
        )
        content = finished.model_dump_json() + "\n" + "NOT JSON\n" + '{"truncated": true}\n'
        f.write_text(content)
        events = read_events(f)
        assert len(events) == 1

    def test_missing_file(self, tmp_path) -> None:
        events = read_events(tmp_path / "nonexistent.jsonl")
        assert events == []

    def test_empty_file(self, tmp_path) -> None:
        f = tmp_path / "results.jsonl"
        f.write_text("")
        events = read_events(f)
        assert events == []


class TestResolveEvents:
    def test_unmatched_start_becomes_crash(self, tmp_path) -> None:
        started = TestStarted(nodeid="t::crashed", start=FIXED_START, location=("test.py", 1, "t::crashed"))
        resolved = resolve_events([started])
        assert len(resolved) == 1
        assert resolved[0].outcome == Outcome.FAILED
        assert resolved[0].longrepr == CRASH_REPR
        assert resolved[0].location == ("test.py", 1, "t::crashed")

    def test_matched_start_is_dropped(self) -> None:
        started = TestStarted(nodeid="t::ok", start=FIXED_START)
        finished = TestFinished(
            nodeid="t::ok",
            outcome=Outcome.PASSED,
            when="call",
            duration=0.001,
            start=FIXED_START,
            stop=FIXED_STOP,
        )
        resolved = resolve_events([started, finished])
        assert len(resolved) == 1
        assert resolved[0].outcome == Outcome.PASSED

    def test_mixed_crash_and_complete(self) -> None:
        """One test completes, another crashes — only the crashed start becomes a failure."""
        started_a = TestStarted(nodeid="t::a", start=FIXED_START)
        finished_a = TestFinished(
            nodeid="t::a",
            outcome=Outcome.PASSED,
            when="call",
            duration=0.001,
            start=FIXED_START,
            stop=FIXED_STOP,
        )
        started_b = TestStarted(nodeid="t::b", start=FIXED_START)

        resolved = resolve_events([started_a, finished_a, started_b])
        assert len(resolved) == 2
        assert resolved[0].nodeid == "t::a"
        assert resolved[0].outcome == Outcome.PASSED
        assert resolved[1].nodeid == "t::b"
        assert resolved[1].outcome == Outcome.FAILED
        assert resolved[1].longrepr == CRASH_REPR
