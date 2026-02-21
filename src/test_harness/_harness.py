from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from test_harness._console import print_results
from test_harness._schema import read_results
from test_harness.backends import get_backend


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="test-harness",
        description="Run pytest in a subprocess and collect structured results.",
    )
    parser.add_argument(
        "--backend",
        default="stub",
        help="Upload backend name (default: stub)",
    )
    return parser


def run(argv: list[str] | None = None) -> int:
    # Split our args from pytest args using '--' as a delimiter,
    # or treat all positional args as pytest args.
    if argv is None:
        argv = sys.argv[1:]

    # Find our flags (--backend) before any pytest args.
    parser = build_parser()
    known, pytest_args = parser.parse_known_args(argv)

    backend = get_backend(known.backend)

    # Create a temp file for JSONL results.
    fd, results_path = tempfile.mkstemp(suffix=".jsonl", prefix="test_harness_")
    os.close(fd)
    results_file = Path(results_path)

    try:
        # Run pytest in subprocess via our _runner module.
        # First arg to _runner is the results file path, rest are pytest args.
        proc = subprocess.run(
            [sys.executable, "-m", "test_harness._runner", str(results_file), *pytest_args],
        )
        exit_code = proc.returncode

        # Read whatever results were written, even on crash.
        results = read_results(results_file)

        # Display results.
        print_results(results)

        # Upload via backend.
        if results:
            backend.upload(results)

        return exit_code
    finally:
        # Clean up temp file.
        results_file.unlink(missing_ok=True)
