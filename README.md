# bridle

A harness for running pytest. It handles the collection and upload of test result information in a way that is resilient to crashes/OOMs in the code under test.

## Features

- **Crash resilience** — pytest runs in a subprocess; events are flushed to disk after every test. A `TestStarted` event is written before each test runs, followed by a `TestFinished` event on completion. If the subprocess segfaults or OOMs mid-test, `resolve_events()` detects the unmatched `TestStarted` and synthesizes a failed `TestFinished`.
- **Pluggable backends** — can register one or more backends to upload test results to.
- **Rich console output** — summary table with outcome counts and duration, plus detailed failure panels, all printed to stderr.
- **Custom Python interpreter** — `--python /path/to/python` runs tests in a different Python environment (e.g. a uv venv or conda env). The target environment only needs pytest installed; bridle injects its own source via `PYTHONPATH`.
- **Exit code passthrough** — the harness returns the subprocess exit code so CI can gate on it.
- **Per-test and total timeouts** — `--test-timeout-sec N` kills the subprocess if any single test exceeds N seconds; `--total-timeout-sec N` kills it if the entire run exceeds N seconds. Timed-out tests appear as normal failures with a timeout-specific message in `longrepr`.

## JSONL Schema

The JSONL file contains a tagged union of two event types, discriminated by the `type` field:

### `TestStarted` — emitted before each test runs

```json
{"type":"test_started","nodeid":"tests/test_a.py::test_ok","start":1735689600.0,"location":["tests/test_a.py",0,"test_ok"]}
```

| Field      | Type                          | Description                          |
|------------|-------------------------------|--------------------------------------|
| `type`     | `"test_started"`              | Event discriminator                  |
| `nodeid`   | `string`                      | Pytest node ID                       |
| `start`    | `float`                       | Epoch timestamp when the test starts |
| `location` | `[string, int\|null, string]` | `[filepath, lineno, domain]`, or null|

### `TestFinished` — emitted when a test phase completes

```json
{"type":"test_finished","nodeid":"tests/test_a.py::test_ok","outcome":"passed","when":"call","duration":0.005,"start":1735689600.0,"stop":1735689600.005,"location":["tests/test_a.py",0,"test_ok"],"longrepr":null,"sections":null,"wasxfail":null}
```

| Field      | Type                          | Description                                                      |
|------------|-------------------------------|------------------------------------------------------------------|
| `type`     | `"test_finished"`             | Event discriminator                                              |
| `nodeid`   | `string`                      | Pytest node ID                                                   |
| `outcome`  | `string`                      | `passed`, `failed`, `skipped`, `error`, `xfailed`, `xpassed`    |
| `when`     | `string`                      | Phase: `setup`, `call`, or `teardown`                            |
| `duration` | `float`                       | Test duration in seconds                                         |
| `start`    | `float`                       | Epoch timestamp when the phase started                           |
| `stop`     | `float`                       | Epoch timestamp when the phase ended                             |
| `location` | `[string, int\|null, string]` | `[filepath, lineno, domain]`, or null                            |
| `longrepr` | `string \| null`              | Failure representation, null on pass                             |
| `sections` | `[[string, string]] \| null`  | Captured output sections, e.g. `[["Captured stdout call", "..."]]` |
| `wasxfail` | `string \| null`              | xfail reason if the test was marked xfail                        |

`TestEvent = TestStarted | TestFinished` is a discriminated union. Use `resolve_events()` to match pairs — unmatched `TestStarted` events become synthetic failed `TestFinished` entries.

## Timeouts

Kill tests that hang or entire runs that take too long:

```bash
# Kill any single test that runs longer than 30 seconds
uv run bridle tests/ --test-timeout-sec 30

# Kill the entire run if it exceeds 2 minutes
uv run bridle tests/ --total-timeout-sec 120

# Both can be combined
uv run bridle tests/ --test-timeout-sec 30 --total-timeout-sec 120
```

When a timeout fires, the subprocess is killed and `TestFinished` events are written for all active tests with a timeout-specific `longrepr`. Downstream code (display, backends) sees them as normal failed tests.

## Custom Python Interpreter

Use `--python` to run tests in a different Python environment while bridle orchestrates from the current one:

```bash
# Run tests using a uv venv
uv run bridle tests/ --python .venv/bin/python

# Run tests using a conda environment
uv run bridle tests/ --python /path/to/conda/env/bin/python
```

The target environment only needs **pytest** installed. bridle automatically injects its own source into `PYTHONPATH` so the subprocess can find the bridle plugin without installing bridle into the target env.

## Buildkite Test Analytics

The `buildkite` backend uploads test results to [Buildkite Test Analytics](https://buildkite.com/docs/test-analytics) for flaky test detection, suite analytics, and performance tracking.

### Setup

Set the `BUILDKITE_ANALYTICS_TOKEN` environment variable to your Buildkite Test Analytics suite API token:

```bash
export BUILDKITE_ANALYTICS_TOKEN="your-suite-token"
uv run bridle tests/ --backend buildkite
```

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `BUILDKITE_ANALYTICS_TOKEN` | Yes | Suite API token for authentication |
| `BUILDKITE_ANALYTICS_API_URL` | No | Custom API endpoint (defaults to `https://analytics-api.buildkite.com/v1/uploads`) |

The backend automatically detects CI environment (Buildkite, GitHub Actions, CircleCI) from standard CI env vars. If no CI provider is detected, it falls back to a generic environment.

### Behavior

- Upload is best-effort: HTTP/network errors are logged as warnings, never propagated.
- If `BUILDKITE_ANALYTICS_TOKEN` is not set, a warning is logged and upload is skipped.
- Test results are uploaded in batches of 100.
- Crash events (unmatched `TestStarted`) are reported as failed tests.

## Adding a Backend

Subclass `Backend` and register it in `backends/__init__.py`:

```python
from bridle.backends._base import Backend
from bridle._schema import TestEvent

class MyBackend(Backend):
    def name(self) -> str:
        return "my-backend"

    def upload(self, events: list[TestEvent]) -> None:
        # upload logic here
        ...
```

Then add it to the registry in `backends/__init__.py`:

```python
_REGISTRY: dict[str, type[Backend]] = {
    "stub": StubBackend,
    "my-backend": MyBackend,
}
```

## Development

```
# Install dev dependencies
uv sync

# Run tests
uv run pytest tests/

# Update syrupy snapshots
uv run pytest tests/ --snapshot-update
```

## Project Structure

```
src/bridle/
├── __init__.py          # main() entrypoint
├── __main__.py          # python -m support
├── _schema.py           # TestStarted/TestFinished pydantic models + Outcome enum + JSONL ser/de
├── _monitor.py          # Subprocess monitor with per-test and total timeout enforcement
├── _plugin.py           # TestResultPlugin (pytest plugin, flush-per-line)
├── _runner.py           # Subprocess entry point
├── _harness.py          # Orchestrator: argparse, subprocess, read results, dispatch
├── _console.py          # Rich-formatted output helpers
└── backends/
    ├── __init__.py      # Registry + get_backend()
    ├── _base.py         # Abstract Backend base class
    ├── _buildkite.py    # BuildkiteBackend (Buildkite Test Analytics)
    └── _stub.py         # StubBackend (logs to console)
```
