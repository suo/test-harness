# test-harness

A harness for running pytest. It handles the collection and upload of test result information in a way that is resilient to crashes/OOMs in the code under test.

## Features

- **Crash resilience** — pytest runs in a subprocess; events are flushed to disk after every test. A `TestStarted` event is written before each test runs, followed by a `TestFinished` event on completion. If the subprocess segfaults or OOMs mid-test, `resolve_events()` detects the unmatched `TestStarted` and synthesizes a failed `TestFinished`.
- **Pluggable backends** — can register one or more backends to upload test results to.
- **Rich console output** — summary table with outcome counts and duration, plus detailed failure panels, all printed to stderr.
- **Exit code passthrough** — the harness returns the subprocess exit code so CI can gate on it.

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

## Adding a Backend

Subclass `Backend` and register it in `backends/__init__.py`:

```python
from test_harness.backends._base import Backend
from test_harness._schema import TestEvent

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
src/test_harness/
├── __init__.py          # main() entrypoint
├── __main__.py          # python -m support
├── _schema.py           # TestStarted/TestFinished pydantic models + Outcome enum + JSONL ser/de
├── _plugin.py           # TestResultPlugin (pytest plugin, flush-per-line)
├── _runner.py           # Subprocess entry point
├── _harness.py          # Orchestrator: argparse, subprocess, read results, dispatch
├── _console.py          # Rich-formatted output helpers
└── backends/
    ├── __init__.py      # Registry + get_backend()
    ├── _base.py         # Abstract Backend base class
    └── _stub.py         # StubBackend (logs to console)
```
