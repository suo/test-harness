from __future__ import annotations

import json
import logging
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from bridle._schema import Outcome, TestEvent, TestFinished, TestStarted
from bridle.backends import (
    Backend,
    BuildkiteBackend,
    MslciBackend,
    StubBackend,
    get_backend,
)
from bridle.backends._buildkite import (
    _convert_event,
    _map_outcome,
    _parse_nodeid,
)
from bridle.backends._run_env import _detect_run_env

# Deterministic timestamps reused from conftest.
FIXED_START = 1735689600.0
FIXED_STOP = 1735689600.005


class TestRegistry:
    def test_get_stub_backend(self) -> None:
        backend = get_backend("stub")
        assert isinstance(backend, StubBackend)
        assert backend.name() == "stub"

    def test_get_buildkite_backend(self) -> None:
        backend = get_backend("buildkite")
        assert isinstance(backend, BuildkiteBackend)
        assert backend.name() == "buildkite"

    def test_get_mslci_backend(self) -> None:
        backend = get_backend("mslci")
        assert isinstance(backend, MslciBackend)
        assert backend.name() == "mslci"

    def test_unknown_backend_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown backend 'nope'"):
            get_backend("nope")


class TestStubBackend:
    def test_upload_does_not_raise(
        self, sample_results: list[TestFinished], capsys: pytest.CaptureFixture[str]
    ) -> None:
        backend = StubBackend()
        backend.upload(sample_results)
        # StubBackend prints to stderr via rich.
        captured = capsys.readouterr()
        assert "3 event(s)" in captured.err

    def test_is_backend_subclass(self) -> None:
        assert issubclass(StubBackend, Backend)


class TestMapOutcome:
    @pytest.mark.parametrize(
        ("outcome", "expected"),
        [
            (Outcome.PASSED, "passed"),
            (Outcome.FAILED, "failed"),
            (Outcome.ERROR, "failed"),
            (Outcome.SKIPPED, "skipped"),
            (Outcome.XFAILED, "skipped"),
            (Outcome.XPASSED, "passed"),
        ],
    )
    def test_all_outcomes(self, outcome: Outcome, expected: str) -> None:
        assert _map_outcome(outcome) == expected


class TestParseNodeid:
    def test_function_level(self) -> None:
        file_name, scope, name = _parse_nodeid("tests/test_a.py::test_ok")
        assert file_name == "tests/test_a.py"
        assert scope == "tests/test_a.py"
        assert name == "test_ok"

    def test_class_method(self) -> None:
        file_name, scope, name = _parse_nodeid(
            "tests/test_a.py::TestClass::test_method"
        )
        assert file_name == "tests/test_a.py"
        assert scope == "TestClass"
        assert name == "test_method"

    def test_parametrized(self) -> None:
        file_name, scope, name = _parse_nodeid(
            "tests/test_a.py::test_param[1-2]"
        )
        assert file_name == "tests/test_a.py"
        assert scope == "tests/test_a.py"
        assert name == "test_param[1-2]"


class TestConvertEvent:
    def test_passed_event(self) -> None:
        event = TestFinished(
            nodeid="tests/test_a.py::test_ok",
            outcome=Outcome.PASSED,
            when="call",
            duration=0.005,
            start=FIXED_START,
            stop=FIXED_STOP,
            location=("tests/test_a.py", 10, "test_ok"),
        )
        result = _convert_event(event)
        assert result["result"] == "passed"
        assert result["name"] == "test_ok"
        assert result["scope"] == "tests/test_a.py"
        assert result["file_name"] == "tests/test_a.py"
        assert result["identifier"] == "tests/test_a.py::test_ok"
        assert result["location"] == "tests/test_a.py:10"
        assert result["history"]["duration"] == 0.005
        assert result["history"]["start_at"] == FIXED_START
        assert result["history"]["end_at"] == FIXED_STOP
        assert "failure_reason" not in result
        assert "failure_expanded" not in result

    def test_failed_event_with_longrepr(self) -> None:
        event = TestFinished(
            nodeid="tests/test_a.py::test_fail",
            outcome=Outcome.FAILED,
            when="call",
            duration=0.123,
            start=FIXED_START,
            stop=FIXED_START + 0.123,
            longrepr="assert 1 == 2",
        )
        result = _convert_event(event)
        assert result["result"] == "failed"
        assert result["failure_reason"] == "assert 1 == 2"
        assert result["failure_expanded"] == [{"expanded": "assert 1 == 2"}]

    def test_location_without_lineno(self) -> None:
        event = TestFinished(
            nodeid="tests/test_a.py::test_ok",
            outcome=Outcome.PASSED,
            when="call",
            duration=0.0,
            start=FIXED_START,
            stop=FIXED_START,
            location=("tests/test_a.py", None, "test_ok"),
        )
        result = _convert_event(event)
        assert result["location"] == "tests/test_a.py"

    def test_no_location(self) -> None:
        event = TestFinished(
            nodeid="tests/test_a.py::test_ok",
            outcome=Outcome.PASSED,
            when="call",
            duration=0.0,
            start=FIXED_START,
            stop=FIXED_START,
        )
        result = _convert_event(event)
        assert result["location"] is None


class TestDetectRunEnv:
    def test_buildkite(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BUILDKITE_BUILD_ID", "abc-123")
        monkeypatch.setenv("BUILDKITE_BUILD_NUMBER", "42")
        monkeypatch.setenv("BUILDKITE_BRANCH", "main")
        result = _detect_run_env()
        assert result["CI"] == "buildkite"
        assert result["key"] == "abc-123"
        assert result["number"] == "42"
        assert result["branch"] == "main"

    def test_github_actions(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("BUILDKITE_BUILD_ID", raising=False)
        monkeypatch.setenv("GITHUB_ACTION", "run")
        monkeypatch.setenv("GITHUB_RUN_ID", "999")
        monkeypatch.setenv("GITHUB_RUN_NUMBER", "5")
        monkeypatch.setenv("GITHUB_SHA", "deadbeef")
        monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
        monkeypatch.setenv("GITHUB_SERVER_URL", "https://github.com")
        monkeypatch.setenv("GITHUB_REPOSITORY", "org/repo")
        monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "1")
        result = _detect_run_env()
        assert result["CI"] == "github_actions"
        assert result["key"] == "999-1"
        assert result["commit"] == "deadbeef"

    def test_circleci(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("BUILDKITE_BUILD_ID", raising=False)
        monkeypatch.delenv("GITHUB_ACTION", raising=False)
        monkeypatch.setenv("CIRCLE_BUILD_NUM", "77")
        monkeypatch.setenv("CIRCLE_BRANCH", "develop")
        monkeypatch.setenv("CIRCLE_SHA1", "cafebabe")
        result = _detect_run_env()
        assert result["CI"] == "circleci"
        assert result["number"] == "77"
        assert result["branch"] == "develop"

    def test_generic_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("BUILDKITE_BUILD_ID", raising=False)
        monkeypatch.delenv("GITHUB_ACTION", raising=False)
        monkeypatch.delenv("CIRCLE_BUILD_NUM", raising=False)
        result = _detect_run_env()
        assert result["CI"] == "generic"


class TestBuildkiteUpload:
    def test_missing_token_warns(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.delenv("BUILDKITE_ANALYTICS_TOKEN", raising=False)
        backend = BuildkiteBackend()
        with caplog.at_level(logging.WARNING):
            backend.upload([])
        assert "BUILDKITE_ANALYTICS_TOKEN not set" in caplog.text

    def test_empty_events_no_upload(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BUILDKITE_ANALYTICS_TOKEN", "fake-token")
        backend = BuildkiteBackend()
        with patch(
            "bridle.backends._buildkite._post_batch"
        ) as mock_post:
            backend.upload([])
            mock_post.assert_not_called()

    def test_correct_payload_structure(
        self, monkeypatch: pytest.MonkeyPatch, sample_results: list[TestFinished]
    ) -> None:
        monkeypatch.setenv("BUILDKITE_ANALYTICS_TOKEN", "fake-token")
        backend = BuildkiteBackend()
        with patch(
            "bridle.backends._buildkite._post_batch"
        ) as mock_post:
            backend.upload(sample_results)
            mock_post.assert_called_once()
            args = mock_post.call_args
            assert args[0][0] == "https://analytics-api.buildkite.com/v1/uploads"
            assert args[0][1] == "fake-token"
            data = args[0][3]
            assert len(data) == 3
            results = [d["result"] for d in data]
            assert results == ["passed", "failed", "skipped"]

    def test_http_error_resilience(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setenv("BUILDKITE_ANALYTICS_TOKEN", "fake-token")
        backend = BuildkiteBackend()

        mock_resp = MagicMock()
        mock_resp.read.return_value = b""
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        def raise_http_error(*args: object, **kwargs: object) -> None:
            raise urllib.error.HTTPError(
                "http://example.com", 422, "Unprocessable", {}, None  # type: ignore[arg-type]
            )

        events: list[TestEvent] = [
            TestFinished(
                nodeid="tests/test_a.py::test_ok",
                outcome=Outcome.PASSED,
                when="call",
                duration=0.0,
                start=FIXED_START,
                stop=FIXED_START,
            ),
        ]
        with (
            patch("urllib.request.urlopen", side_effect=raise_http_error),
            caplog.at_level(logging.WARNING),
        ):
            backend.upload(events)
        assert "Buildkite upload failed" in caplog.text

    def test_batching(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BUILDKITE_ANALYTICS_TOKEN", "fake-token")
        backend = BuildkiteBackend()
        events: list[TestEvent] = [
            TestFinished(
                nodeid=f"tests/test_a.py::test_{i}",
                outcome=Outcome.PASSED,
                when="call",
                duration=0.0,
                start=FIXED_START,
                stop=FIXED_START,
            )
            for i in range(250)
        ]
        with patch(
            "bridle.backends._buildkite._post_batch"
        ) as mock_post:
            backend.upload(events)
            assert mock_post.call_count == 3
            # First two batches have 100 items, last has 50.
            batch_sizes = [len(call.args[3]) for call in mock_post.call_args_list]
            assert batch_sizes == [100, 100, 50]

    def test_crash_events_become_failed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Unmatched TestStarted events are resolved as failed."""
        monkeypatch.setenv("BUILDKITE_ANALYTICS_TOKEN", "fake-token")
        backend = BuildkiteBackend()
        events: list[TestEvent] = [
            TestStarted(
                nodeid="tests/test_a.py::test_crash",
                start=FIXED_START,
            ),
        ]
        with patch(
            "bridle.backends._buildkite._post_batch"
        ) as mock_post:
            backend.upload(events)
            mock_post.assert_called_once()
            data = mock_post.call_args[0][3]
            assert len(data) == 1
            assert data[0]["result"] == "failed"
            assert data[0]["name"] == "test_crash"

    def test_custom_api_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BUILDKITE_ANALYTICS_TOKEN", "fake-token")
        monkeypatch.setenv(
            "BUILDKITE_ANALYTICS_API_URL", "https://custom.example.com/upload"
        )
        backend = BuildkiteBackend()
        events: list[TestEvent] = [
            TestFinished(
                nodeid="tests/test_a.py::test_ok",
                outcome=Outcome.PASSED,
                when="call",
                duration=0.0,
                start=FIXED_START,
                stop=FIXED_START,
            ),
        ]
        with patch(
            "bridle.backends._buildkite._post_batch"
        ) as mock_post:
            backend.upload(events)
            assert mock_post.call_args[0][0] == "https://custom.example.com/upload"


class TestMslciBackend:
    def test_missing_url_warns(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.delenv("MSLCI_API_URL", raising=False)
        backend = MslciBackend()
        with caplog.at_level(logging.WARNING):
            backend.upload([])
        assert "MSLCI_API_URL not set" in caplog.text

    def test_empty_events_no_upload(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MSLCI_API_URL", "https://mslci.example.com/api/v1/uploads")
        backend = MslciBackend()
        with patch("urllib.request.urlopen") as mock_urlopen:
            backend.upload([])
            mock_urlopen.assert_not_called()

    def test_payload_structure(
        self, monkeypatch: pytest.MonkeyPatch, sample_results: list[TestFinished]
    ) -> None:
        monkeypatch.setenv("MSLCI_API_URL", "https://mslci.example.com/api/v1/uploads")
        monkeypatch.setenv("BUILDKITE_BUILD_ID", "abc-123")
        monkeypatch.setenv("BUILDKITE_BRANCH", "main")
        monkeypatch.setenv("BUILDKITE_COMMIT", "deadbeef")
        backend = MslciBackend()

        mock_resp = MagicMock()
        mock_resp.read.return_value = b""
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
            backend.upload(sample_results)
            mock_urlopen.assert_called_once()
            req = mock_urlopen.call_args[0][0]
            payload = json.loads(req.data.decode("utf-8"))

        # Verify run_env has MSLCI schema fields
        run_env = payload["run_env"]
        assert run_env["key"] == "abc-123"
        assert run_env["branch"] == "main"
        assert run_env["commit_sha"] == "deadbeef"
        assert run_env["ci"] == "buildkite"
        assert "commit" not in run_env
        assert "CI" not in run_env

        # Verify events structure
        events = payload["events"]
        assert len(events) == 3
        assert events[0]["nodeid"] == "tests/test_a.py::test_ok"
        assert events[0]["outcome"] == "passed"
        assert events[0]["duration"] == 0.005
        assert events[0]["start"] == FIXED_START
        assert events[0]["stop"] == FIXED_STOP
        # type field must not be present
        for ev in events:
            assert "type" not in ev

    def test_auth_header(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MSLCI_API_URL", "https://mslci.example.com/api/v1/uploads")
        monkeypatch.setenv("MSLCI_API_TOKEN", "secret-token")
        backend = MslciBackend()

        events: list[TestEvent] = [
            TestFinished(
                nodeid="tests/test_a.py::test_ok",
                outcome=Outcome.PASSED,
                when="call",
                duration=0.0,
                start=FIXED_START,
                stop=FIXED_START,
            ),
        ]

        mock_resp = MagicMock()
        mock_resp.read.return_value = b""
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
            backend.upload(events)
            req = mock_urlopen.call_args[0][0]
            assert req.get_header("Authorization") == 'Token token="secret-token"'

    def test_no_auth_header(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MSLCI_API_URL", "https://mslci.example.com/api/v1/uploads")
        monkeypatch.delenv("MSLCI_API_TOKEN", raising=False)
        backend = MslciBackend()

        events: list[TestEvent] = [
            TestFinished(
                nodeid="tests/test_a.py::test_ok",
                outcome=Outcome.PASSED,
                when="call",
                duration=0.0,
                start=FIXED_START,
                stop=FIXED_START,
            ),
        ]

        mock_resp = MagicMock()
        mock_resp.read.return_value = b""
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
            backend.upload(events)
            req = mock_urlopen.call_args[0][0]
            assert not req.has_header("Authorization")

    def test_http_error_resilience(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setenv("MSLCI_API_URL", "https://mslci.example.com/api/v1/uploads")
        backend = MslciBackend()

        events: list[TestEvent] = [
            TestFinished(
                nodeid="tests/test_a.py::test_ok",
                outcome=Outcome.PASSED,
                when="call",
                duration=0.0,
                start=FIXED_START,
                stop=FIXED_START,
            ),
        ]

        def raise_http_error(*args: object, **kwargs: object) -> None:
            raise urllib.error.HTTPError(
                "http://example.com", 500, "Server Error", {}, None  # type: ignore[arg-type]
            )

        with (
            patch("urllib.request.urlopen", side_effect=raise_http_error),
            caplog.at_level(logging.WARNING),
        ):
            backend.upload(events)
        assert "MSLCI upload failed" in caplog.text

    def test_crash_events_resolved(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Unmatched TestStarted events are resolved as failed."""
        monkeypatch.setenv("MSLCI_API_URL", "https://mslci.example.com/api/v1/uploads")
        backend = MslciBackend()

        events: list[TestEvent] = [
            TestStarted(
                nodeid="tests/test_a.py::test_crash",
                start=FIXED_START,
            ),
        ]

        mock_resp = MagicMock()
        mock_resp.read.return_value = b""
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
            backend.upload(events)
            mock_urlopen.assert_called_once()
            req = mock_urlopen.call_args[0][0]
            payload = json.loads(req.data.decode("utf-8"))
            events_data = payload["events"]
            assert len(events_data) == 1
            assert events_data[0]["outcome"] == "failed"
            assert events_data[0]["nodeid"] == "tests/test_a.py::test_crash"

    def test_batching(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MSLCI_API_URL", "https://mslci.example.com/api/v1/uploads")
        backend = MslciBackend()
        events: list[TestEvent] = [
            TestFinished(
                nodeid=f"tests/test_a.py::test_{i}",
                outcome=Outcome.PASSED,
                when="call",
                duration=0.0,
                start=FIXED_START,
                stop=FIXED_START,
            )
            for i in range(12_000)
        ]

        mock_resp = MagicMock()
        mock_resp.read.return_value = b""
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
            backend.upload(events)
            assert mock_urlopen.call_count == 3
            # First two batches have 5000 items, last has 2000.
            batch_sizes = [
                len(json.loads(call.args[0].data.decode("utf-8"))["events"])
                for call in mock_urlopen.call_args_list
            ]
            assert batch_sizes == [5000, 5000, 2000]

    def test_run_env_commit_sha_mapping(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The 'commit' field from CI detection is mapped to 'commit_sha'."""
        monkeypatch.setenv("MSLCI_API_URL", "https://mslci.example.com/api/v1/uploads")
        monkeypatch.delenv("BUILDKITE_BUILD_ID", raising=False)
        monkeypatch.setenv("GITHUB_ACTION", "run")
        monkeypatch.setenv("GITHUB_RUN_ID", "999")
        monkeypatch.setenv("GITHUB_SHA", "deadbeef")
        monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
        monkeypatch.setenv("GITHUB_SERVER_URL", "https://github.com")
        monkeypatch.setenv("GITHUB_REPOSITORY", "org/repo")
        monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "1")
        backend = MslciBackend()

        events: list[TestEvent] = [
            TestFinished(
                nodeid="tests/test_a.py::test_ok",
                outcome=Outcome.PASSED,
                when="call",
                duration=0.0,
                start=FIXED_START,
                stop=FIXED_START,
            ),
        ]

        mock_resp = MagicMock()
        mock_resp.read.return_value = b""
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
            backend.upload(events)
            req = mock_urlopen.call_args[0][0]
            payload = json.loads(req.data.decode("utf-8"))
            run_env = payload["run_env"]
            assert run_env["commit_sha"] == "deadbeef"
            assert "commit" not in run_env
