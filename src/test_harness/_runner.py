"""Subprocess entry point: python -m test_harness._runner <results_path> [pytest args...]

This module is invoked by the harness in a subprocess. The first argument is
the JSONL results file path; all remaining arguments are forwarded to pytest.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from test_harness._plugin import TestResultPlugin


def main() -> int:
    results_path = Path(sys.argv[1])
    pytest_args = sys.argv[2:]
    plugin = TestResultPlugin(results_path)
    return pytest.main(pytest_args, plugins=[plugin])


if __name__ == "__main__":
    sys.exit(main())
