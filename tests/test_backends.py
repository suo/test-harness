from __future__ import annotations

import pytest

from test_harness._schema import TestEvent, TestFinished
from test_harness.backends import Backend, StubBackend, get_backend


class TestRegistry:
    def test_get_stub_backend(self) -> None:
        backend = get_backend("stub")
        assert isinstance(backend, StubBackend)
        assert backend.name() == "stub"

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
