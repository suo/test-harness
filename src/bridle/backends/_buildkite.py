from __future__ import annotations

import json
import logging
import os
import urllib.request
import urllib.error
from uuid import uuid4

from bridle._schema import Outcome, TestEvent, TestFinished, resolve_events
from bridle.backends._base import Backend

logger = logging.getLogger(__name__)

_DEFAULT_API_URL = "https://analytics-api.buildkite.com/v1/uploads"

_OUTCOME_MAP: dict[Outcome, str] = {
    Outcome.PASSED: "passed",
    Outcome.FAILED: "failed",
    Outcome.ERROR: "failed",
    Outcome.SKIPPED: "skipped",
    Outcome.XFAILED: "skipped",
    Outcome.XPASSED: "passed",
}


def _map_outcome(outcome: Outcome) -> str:
    """Map an internal Outcome to a Buildkite result string."""
    return _OUTCOME_MAP[outcome]


def _parse_nodeid(nodeid: str) -> tuple[str, str, str]:
    """Split a pytest nodeid into (file_name, scope, name).

    Examples:
        "tests/test_a.py::test_ok"           -> ("tests/test_a.py", "tests/test_a.py", "test_ok")
        "tests/test_a.py::TestClass::test_m"  -> ("tests/test_a.py", "TestClass", "test_m")
        "tests/test_a.py::test_p[1-2]"       -> ("tests/test_a.py", "tests/test_a.py", "test_p[1-2]")
    """
    parts = nodeid.split("::")
    file_name = parts[0]
    if len(parts) == 3:
        scope = parts[1]
        name = parts[2]
    elif len(parts) == 2:
        scope = file_name
        name = parts[1]
    else:
        scope = file_name
        name = nodeid
    return file_name, scope, name


def _convert_event(event: TestFinished) -> dict:
    """Convert a TestFinished event to a Buildkite test data dict."""
    file_name, scope, name = _parse_nodeid(event.nodeid)
    result = _map_outcome(event.outcome)

    location_str: str | None = None
    if event.location is not None:
        loc_file, loc_line, loc_domain = event.location
        if loc_line is not None:
            location_str = f"{loc_file}:{loc_line}"
        else:
            location_str = loc_file

    entry: dict = {
        "id": str(uuid4()),
        "scope": scope,
        "name": name,
        "identifier": event.nodeid,
        "location": location_str,
        "file_name": file_name,
        "result": result,
        "history": {
            "start_at": event.start,
            "end_at": event.stop,
            "duration": event.duration,
        },
    }

    if result == "failed":
        entry["failure_reason"] = event.longrepr or ""
        if event.longrepr:
            entry["failure_expanded"] = [{"expanded": event.longrepr}]

    return entry


def _detect_run_env() -> dict:
    """Detect CI environment from env vars."""
    env = os.environ

    if env.get("BUILDKITE_BUILD_ID"):
        return {
            "CI": "buildkite",
            "key": env.get("BUILDKITE_BUILD_ID", ""),
            "number": env.get("BUILDKITE_BUILD_NUMBER", ""),
            "job_id": env.get("BUILDKITE_JOB_ID", ""),
            "branch": env.get("BUILDKITE_BRANCH", ""),
            "commit": env.get("BUILDKITE_COMMIT", ""),
            "message": env.get("BUILDKITE_MESSAGE", ""),
            "url": env.get("BUILDKITE_BUILD_URL", ""),
        }

    if env.get("GITHUB_ACTION"):
        return {
            "CI": "github_actions",
            "key": f"{env.get('GITHUB_RUN_ID', '')}-{env.get('GITHUB_RUN_ATTEMPT', '1')}",
            "number": env.get("GITHUB_RUN_NUMBER", ""),
            "branch": env.get("GITHUB_REF", ""),
            "commit": env.get("GITHUB_SHA", ""),
            "url": f"{env.get('GITHUB_SERVER_URL', '')}/{env.get('GITHUB_REPOSITORY', '')}/actions/runs/{env.get('GITHUB_RUN_ID', '')}",
        }

    if env.get("CIRCLE_BUILD_NUM"):
        return {
            "CI": "circleci",
            "key": env.get("CIRCLE_WORKFLOW_ID", ""),
            "number": env.get("CIRCLE_BUILD_NUM", ""),
            "branch": env.get("CIRCLE_BRANCH", ""),
            "commit": env.get("CIRCLE_SHA1", ""),
            "url": env.get("CIRCLE_BUILD_URL", ""),
        }

    return {
        "CI": "generic",
        "key": env.get("CI_BUILD_ID", ""),
    }


def _post_batch(
    api_url: str, token: str, run_env: dict, data: list[dict]
) -> None:
    """POST a batch of test data to Buildkite."""
    payload = json.dumps(
        {
            "format": "json",
            "run_env": run_env,
            "data": data,
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        api_url,
        data=payload,
        headers={
            "Authorization": f"Token token=\"{token}\"",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req) as resp:
            resp.read()
    except (urllib.error.URLError, OSError) as exc:
        logger.warning("Buildkite upload failed: %s", exc)


_BATCH_SIZE = 100


class BuildkiteBackend(Backend):
    """Upload test results to Buildkite Test Analytics."""

    def name(self) -> str:
        return "buildkite"

    def upload(self, events: list[TestEvent]) -> None:
        token = os.environ.get("BUILDKITE_ANALYTICS_TOKEN")
        if not token:
            logger.warning(
                "BUILDKITE_ANALYTICS_TOKEN not set; skipping Buildkite upload"
            )
            return

        resolved = resolve_events(events)
        if not resolved:
            return

        api_url = os.environ.get("BUILDKITE_ANALYTICS_API_URL", _DEFAULT_API_URL)
        run_env = _detect_run_env()
        data = [_convert_event(ev) for ev in resolved]

        for i in range(0, len(data), _BATCH_SIZE):
            batch = data[i : i + _BATCH_SIZE]
            _post_batch(api_url, token, run_env, batch)
