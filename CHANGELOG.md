# Changelog

## 0.1.0

Initial release as `bridle` (renamed from `test-harness`).

- Crash-resilient pytest harness running tests in a subprocess
- JSONL event schema with `TestStarted`/`TestFinished` discriminated union
- `resolve_events()` synthesizes failures for unmatched starts (crashes, segfaults)
- Pluggable backend system with Buildkite Test Analytics and stub backends
- Rich console output with summary table and failure panels
- Per-test and total timeout support (`--test-timeout-sec`, `--total-timeout-sec`)
