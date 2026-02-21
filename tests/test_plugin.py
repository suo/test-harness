from __future__ import annotations

import json

import pytest


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

        results_file = harness_pytester.path / "results.jsonl"
        lines = results_file.read_text().strip().splitlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["outcome"] == "passed"
        assert "test_ok" in data["node_id"]

    def test_failed_test_recorded(self, harness_pytester: pytest.Pytester) -> None:
        harness_pytester.makepyfile(
            """
def test_fail():
    assert 1 == 2
"""
        )
        result = harness_pytester.runpytest()
        result.assert_outcomes(failed=1)

        results_file = harness_pytester.path / "results.jsonl"
        lines = results_file.read_text().strip().splitlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["outcome"] == "failed"
        assert data["longrepr"] is not None

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

        results_file = harness_pytester.path / "results.jsonl"
        lines = results_file.read_text().strip().splitlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["outcome"] == "skipped"

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

        results_file = harness_pytester.path / "results.jsonl"
        lines = results_file.read_text().strip().splitlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["outcome"] == "xfailed"

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

        results_file = harness_pytester.path / "results.jsonl"
        lines = results_file.read_text().strip().splitlines()
        assert len(lines) == 3
        outcomes = {json.loads(line)["outcome"] for line in lines}
        assert outcomes == {"passed", "failed", "skipped"}

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

        results_file = harness_pytester.path / "results.jsonl"
        lines = results_file.read_text().strip().splitlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["outcome"] == "error"
        assert "setup boom" in data["longrepr"]
