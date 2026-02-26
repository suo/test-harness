from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from bridle._console import print_results
from bridle._monitor import monitor_subprocess
from bridle._schema import read_events, resolve_events
from bridle.backends import get_backends


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bridle",
        description="Run pytest in a subprocess and collect structured results.",
    )
    parser.add_argument(
        "--backend",
        default="stub",
        help="Upload backend name(s), comma-separated (default: stub)",
    )
    parser.add_argument(
        "--python",
        default=None,
        help="Path to a Python interpreter to use for the subprocess.",
    )
    parser.add_argument(
        "--test-timeout-sec",
        type=float,
        default=None,
        help="Kill the subprocess if any single test exceeds N seconds.",
    )
    parser.add_argument(
        "--total-timeout-sec",
        type=float,
        default=None,
        help="Kill the subprocess if the entire run exceeds N seconds.",
    )
    return parser


def _bridle_source_root() -> str:
    """Return the directory containing the bridle package source."""
    import bridle as _pkg

    return str(Path(_pkg.__file__).resolve().parent.parent)


def run(argv: list[str] | None = None) -> int:
    # Split our args from pytest args using '--' as a delimiter,
    # or treat all positional args as pytest args.
    if argv is None:
        argv = sys.argv[1:]

    # Find our flags (--backend) before any pytest args.
    parser = build_parser()
    known, pytest_args = parser.parse_known_args(argv)

    backends = get_backends(known.backend)

    # Create a temp file for JSONL results.
    fd, results_path = tempfile.mkstemp(suffix=".jsonl", prefix="bridle_")
    os.close(fd)
    results_file = Path(results_path)

    try:
        # Run pytest in subprocess via our _runner module.
        # First arg to _runner is the results file path, rest are pytest args.
        python_exe = known.python or sys.executable
        env = None
        if known.python:
            env = os.environ.copy()
            source_root = _bridle_source_root()
            existing = env.get("PYTHONPATH", "")
            env["PYTHONPATH"] = (
                source_root + os.pathsep + existing if existing else source_root
            )
        proc = subprocess.Popen(
            [python_exe, "-m", "bridle._runner", str(results_file), *pytest_args],
            env=env,
        )
        exit_code, timeout_result = monitor_subprocess(
            proc,
            results_file,
            test_timeout_sec=known.test_timeout_sec,
            total_timeout_sec=known.total_timeout_sec,
        )
        if timeout_result is not None:
            if timeout_result.kind == "test":
                print(
                    f"Killed: test {timeout_result.nodeid!r} exceeded "
                    f"per-test timeout of {timeout_result.limit:.1f}s",
                    file=sys.stderr,
                )
            else:
                print(
                    f"Killed: total run exceeded timeout of "
                    f"{timeout_result.limit:.1f}s",
                    file=sys.stderr,
                )

        # Read whatever events were written, even on crash.
        events = read_events(results_file)

        # Resolve started/finished pairs for display.
        resolved = resolve_events(events)

        # Display results.
        print_results(resolved)

        # Upload raw events via backends.
        if events:
            for backend in backends:
                backend.upload(events)

        return exit_code
    finally:
        # Clean up temp file.
        results_file.unlink(missing_ok=True)
