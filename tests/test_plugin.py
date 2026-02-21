from __future__ import annotations

import pytest

from test_harness._schema import Outcome, TestFinished, read_events, resolve_events


@pytest.fixture()
def harness_pytester(pytester: pytest.Pytester) -> pytest.Pytester:
    """A pytester that registers the plugin via conftest, pointing at a local results file."""
    results_file = pytester.path / "results.jsonl"
    pytester.makeconftest(
        f"""
from pathlib import Path
from test_harness._plugin import TestResultPlugin

def pytest_configure(config):
    plugin = TestResultPlugin(Path({str(results_file)!r}))
    config.pluginmanager.register(plugin, "test_harness_plugin")
"""
    )
    return pytester


def _resolved_results(pytester: pytest.Pytester) -> list[TestFinished]:
    """Read events and resolve to TestFinished list."""
    return resolve_events(read_events(pytester.path / "results.jsonl"))


class TestPluginIntegration:
    def test_passed_test_recorded(self, harness_pytester: pytest.Pytester) -> None:
        harness_pytester.makepyfile(
            """
def test_ok():
    assert True
"""
        )
        result = harness_pytester.runpytest()
        result.assert_outcomes(passed=1)

        results = _resolved_results(harness_pytester)
        assert len(results) == 1
        r = results[0]
        assert r.outcome == Outcome.PASSED
        assert "test_ok" in r.nodeid
        assert r.when == "call"
        assert isinstance(r.start, float)
        assert isinstance(r.stop, float)
        assert isinstance(r.duration, float)
        assert r.location is not None

    def test_failed_test_recorded(self, harness_pytester: pytest.Pytester) -> None:
        harness_pytester.makepyfile(
            """
def test_fail():
    assert 1 == 2
"""
        )
        result = harness_pytester.runpytest()
        result.assert_outcomes(failed=1)

        results = _resolved_results(harness_pytester)
        assert len(results) == 1
        assert results[0].outcome == Outcome.FAILED
        assert results[0].longrepr is not None

    def test_skipped_test_recorded(self, harness_pytester: pytest.Pytester) -> None:
        harness_pytester.makepyfile(
            """
import pytest

@pytest.mark.skip(reason="not today")
def test_skip():
    pass
"""
        )
        result = harness_pytester.runpytest()
        result.assert_outcomes(skipped=1)

        results = _resolved_results(harness_pytester)
        assert len(results) == 1
        assert results[0].outcome == Outcome.SKIPPED

    def test_xfail_recorded(self, harness_pytester: pytest.Pytester) -> None:
        harness_pytester.makepyfile(
            """
import pytest

@pytest.mark.xfail
def test_expected_failure():
    assert False
"""
        )
        result = harness_pytester.runpytest()
        result.assert_outcomes(xfailed=1)

        results = _resolved_results(harness_pytester)
        assert len(results) == 1
        assert results[0].outcome == Outcome.XFAILED
        assert results[0].wasxfail is not None

    def test_multiple_tests(self, harness_pytester: pytest.Pytester) -> None:
        harness_pytester.makepyfile(
            """
import pytest

def test_a():
    pass

def test_b():
    assert False

@pytest.mark.skip
def test_c():
    pass
"""
        )
        result = harness_pytester.runpytest()
        result.assert_outcomes(passed=1, failed=1, skipped=1)

        results = _resolved_results(harness_pytester)
        assert len(results) == 3
        outcomes = {r.outcome for r in results}
        assert outcomes == {Outcome.PASSED, Outcome.FAILED, Outcome.SKIPPED}

    def test_setup_error_recorded(self, harness_pytester: pytest.Pytester) -> None:
        harness_pytester.makepyfile(
            """
import pytest

@pytest.fixture
def bad_fixture():
    raise RuntimeError("setup boom")

def test_with_bad_fixture(bad_fixture):
    pass
"""
        )
        result = harness_pytester.runpytest()
        result.assert_outcomes(errors=1)

        results = _resolved_results(harness_pytester)
        assert len(results) == 1
        assert results[0].outcome == Outcome.ERROR
        assert results[0].when == "setup"
        assert "setup boom" in results[0].longrepr

    def test_crashed_test_recorded(self, harness_pytester: pytest.Pytester) -> None:
        """A test that crashes the process (os._exit) is recorded as failed."""
        harness_pytester.makepyfile(
            """
import os

def test_before():
    pass

def test_crash():
    os._exit(1)

def test_after():
    pass
"""
        )
        harness_pytester.runpytest_subprocess()

        results = _resolved_results(harness_pytester)
        by_name = {r.nodeid.split("::")[-1]: r for r in results}

        # test_before completed normally
        assert by_name["test_before"].outcome == Outcome.PASSED

        # test_crash started but the process died — resolved as failed
        assert "test_crash" in by_name
        assert by_name["test_crash"].outcome == Outcome.FAILED

        # test_after never ran
        assert "test_after" not in by_name

    def test_raw_events_contain_both_types(self, harness_pytester: pytest.Pytester) -> None:
        """Verify the JSONL file contains both TestStarted and TestFinished events."""
        harness_pytester.makepyfile(
            """
def test_ok():
    assert True
"""
        )
        harness_pytester.runpytest()

        from test_harness._schema import TestStarted
        events = read_events(harness_pytester.path / "results.jsonl")
        started = [e for e in events if isinstance(e, TestStarted)]
        finished = [e for e in events if isinstance(e, TestFinished)]
        assert len(started) == 1
        assert len(finished) == 1
        assert started[0].nodeid == finished[0].nodeid
