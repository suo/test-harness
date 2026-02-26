from __future__ import annotations

import os
import subprocess
import sys
import textwrap

import pytest


class TestHarnessSubprocess:
    """Full subprocess integration tests for the bridle CLI."""

    def test_passing_tests(self, tmp_path) -> None:
        test_file = tmp_path / "test_example.py"
        test_file.write_text(
            textwrap.dedent("""\
            def test_one():
                assert True

            def test_two():
                assert 1 + 1 == 2
        """)
        )
        result = subprocess.run(
            [sys.executable, "-m", "bridle", str(test_file), "--backend", "stub"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "passed" in result.stderr.lower()

    def test_failing_tests_nonzero_exit(self, tmp_path) -> None:
        test_file = tmp_path / "test_fail.py"
        test_file.write_text(
            textwrap.dedent("""\
            def test_bad():
                assert False
        """)
        )
        result = subprocess.run(
            [sys.executable, "-m", "bridle", str(test_file), "--backend", "stub"],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
        assert "failed" in result.stderr.lower()

    def test_mixed_outcomes(self, tmp_path) -> None:
        test_file = tmp_path / "test_mixed.py"
        test_file.write_text(
            textwrap.dedent("""\
            import pytest

            def test_pass():
                assert True

            def test_fail():
                assert False

            @pytest.mark.skip
            def test_skip():
                pass
        """)
        )
        result = subprocess.run(
            [sys.executable, "-m", "bridle", str(test_file), "--backend", "stub"],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
        stderr_lower = result.stderr.lower()
        assert "passed" in stderr_lower
        assert "failed" in stderr_lower
        assert "skipped" in stderr_lower

    def test_no_test_files(self, tmp_path) -> None:
        """Running with a directory that has no tests should still work."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        result = subprocess.run(
            [sys.executable, "-m", "bridle", str(empty_dir), "--backend", "stub"],
            capture_output=True,
            text=True,
        )
        # pytest returns 5 (no tests collected) — we pass it through.
        assert result.returncode == 5

    def test_stub_backend_message(self, tmp_path) -> None:
        test_file = tmp_path / "test_one.py"
        test_file.write_text("def test_ok(): pass\n")
        result = subprocess.run(
            [sys.executable, "-m", "bridle", str(test_file), "--backend", "stub"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "would upload" in result.stderr.lower()


class TestHarnessTimeouts:
    """Integration tests for --test-timeout-sec and --total-timeout-sec."""

    def test_per_test_timeout_kills_slow_test(self, tmp_path) -> None:
        test_file = tmp_path / "test_slow.py"
        test_file.write_text(
            textwrap.dedent("""\
            import time
            def test_hangs():
                time.sleep(60)
        """)
        )
        result = subprocess.run(
            [
                sys.executable, "-m", "bridle",
                str(test_file),
                "--test-timeout-sec", "2",
                "--backend", "stub",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode != 0
        assert "timeout" in result.stderr.lower()

    def test_total_timeout_kills_run(self, tmp_path) -> None:
        test_file = tmp_path / "test_many_slow.py"
        test_file.write_text(
            textwrap.dedent("""\
            import time
            def test_a():
                time.sleep(60)
            def test_b():
                time.sleep(60)
        """)
        )
        result = subprocess.run(
            [
                sys.executable, "-m", "bridle",
                str(test_file),
                "--total-timeout-sec", "3",
                "--backend", "stub",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode != 0
        assert "timeout" in result.stderr.lower()

    def test_no_timeout_when_tests_are_fast(self, tmp_path) -> None:
        test_file = tmp_path / "test_fast.py"
        test_file.write_text(
            textwrap.dedent("""\
            def test_quick_a():
                assert True
            def test_quick_b():
                assert 1 + 1 == 2
        """)
        )
        result = subprocess.run(
            [
                sys.executable, "-m", "bridle",
                str(test_file),
                "--test-timeout-sec", "30",
                "--total-timeout-sec", "60",
                "--backend", "stub",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0
        assert "passed" in result.stderr.lower()
