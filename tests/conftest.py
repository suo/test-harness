from __future__ import annotations

import pytest

from test_harness._schema import Outcome, TestFinished

pytest_plugins = ["pytester"]

# Deterministic epoch timestamps for snapshot tests.
FIXED_START = 1735689600.0  # 2025-01-01T00:00:00 UTC
FIXED_STOP = 1735689600.005  # 5ms later


@pytest.fixture()
def sample_results() -> list[TestFinished]:
    return [
        TestFinished(
            nodeid="tests/test_a.py::test_ok",
            outcome=Outcome.PASSED,
            when="call",
            duration=0.005,
            start=FIXED_START,
            stop=FIXED_STOP,
        ),
        TestFinished(
            nodeid="tests/test_a.py::test_fail",
            outcome=Outcome.FAILED,
            when="call",
            duration=0.123,
            start=FIXED_START,
            stop=FIXED_START + 0.123,
            longrepr="assert 1 == 2",
        ),
        TestFinished(
            nodeid="tests/test_a.py::test_skip",
            outcome=Outcome.SKIPPED,
            when="setup",
            duration=0.0,
            start=FIXED_START,
            stop=FIXED_START,
        ),
    ]
