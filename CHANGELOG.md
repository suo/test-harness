# Changelog

## 0.5.0

- Support multiple backends via comma-separated `--backend` values (e.g. `--backend buildkite,mslci`)

## 0.4.0

- Add MSLCI upload backend (`--backend mslci`)
- Extract `_detect_run_env()` to shared module for backend reuse
- Batch event uploads (5,000 per request) to handle large test suites

## 0.3.0

- Lower minimum Python version from 3.13 to 3.12
- Add Python 3.12 to CI test matrix

## 0.2.0

- Add `--python` flag to run tests in a different Python interpreter
- Refactor `_plugin.py` to avoid pydantic dependency in the subprocess (only pytest needed in target env)
- Bridle source is automatically injected into `PYTHONPATH` when using `--python`

## 0.1.0

Initial release as `bridle` (renamed from `test-harness`).

- Crash-resilient pytest harness running tests in a subprocess
- JSONL event schema with `TestStarted`/`TestFinished` discriminated union
- `resolve_events()` synthesizes failures for unmatched starts (crashes, segfaults)
- Pluggable backend system with Buildkite Test Analytics and stub backends
- Rich console output with summary table and failure panels
- Per-test and total timeout support (`--test-timeout-sec`, `--total-timeout-sec`)
