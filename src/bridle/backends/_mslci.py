from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request

from bridle._schema import TestEvent, TestFinished, resolve_events
from bridle.backends._base import Backend
from bridle.backends._run_env import _detect_run_env

logger = logging.getLogger(__name__)


def _location_to_str(
    location: tuple[str, int | None, str] | None,
) -> str | None:
    """Convert a pytest location tuple to a string (or None)."""
    if location is None:
        return None
    file, lineno, _domain = location
    if lineno is not None:
        return f"{file}:{lineno}"
    return file


def _make_mslci_run_env(raw: dict) -> dict:
    """Remap _detect_run_env() output to the MSLCI RunEnv schema.

    The server expects ``commit_sha`` (not ``commit``) and ``ci`` (not ``CI``).
    Extra fields like ``number`` and ``message`` are dropped.
    """
    return {
        "key": raw.get("key", ""),
        "branch": raw.get("branch"),
        "commit_sha": raw.get("commit"),
        "job_id": raw.get("job_id"),
        "url": raw.get("url"),
        "ci": raw.get("CI"),
    }


def _serialize_event(event: TestFinished) -> dict:
    """Serialize a TestFinished event for the MSLCI upload payload."""
    data = event.model_dump(exclude={"type"})
    # Convert location from tuple to string for the server schema.
    data["location"] = _location_to_str(event.location)
    return data


_BATCH_SIZE = 5000


def _post_batch(
    api_url: str,
    headers: dict[str, str],
    run_env: dict,
    data: list[dict],
) -> None:
    """POST a batch of serialized events to the MSLCI server."""
    payload = json.dumps({"run_env": run_env, "events": data}).encode("utf-8")

    req = urllib.request.Request(
        api_url,
        data=payload,
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(req) as resp:
            resp.read()
    except (urllib.error.URLError, OSError) as exc:
        logger.warning("MSLCI upload failed: %s", exc)


class MslciBackend(Backend):
    """Upload test results to the MSLCI server."""

    def name(self) -> str:
        return "mslci"

    def upload(self, events: list[TestEvent]) -> None:
        api_url = os.environ.get("MSLCI_API_URL")
        if not api_url:
            logger.warning("MSLCI_API_URL not set; skipping MSLCI upload")
            return

        resolved = resolve_events(events)
        if not resolved:
            return

        run_env = _make_mslci_run_env(_detect_run_env())
        data = [_serialize_event(ev) for ev in resolved]

        headers: dict[str, str] = {"Content-Type": "application/json"}
        token = os.environ.get("MSLCI_API_TOKEN")
        if token:
            headers["Authorization"] = f'Token token="{token}"'

        for i in range(0, len(data), _BATCH_SIZE):
            batch = data[i : i + _BATCH_SIZE]
            _post_batch(api_url, headers, run_env, batch)
