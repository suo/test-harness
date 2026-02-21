from __future__ import annotations

import logging
from enum import Enum
from pathlib import Path
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, TypeAdapter

logger = logging.getLogger(__name__)

CRASH_REPR = "Test crashed (no result received)"


class Outcome(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"
    XFAILED = "xfailed"
    XPASSED = "xpassed"


class TestStarted(BaseModel):
    __test__ = False  # prevent pytest collection

    type: Literal["test_started"] = "test_started"
    nodeid: str
    start: float
    location: tuple[str, int | None, str] | None = None


class TestFinished(BaseModel):
    __test__ = False  # prevent pytest collection

    type: Literal["test_finished"] = "test_finished"
    nodeid: str
    outcome: Outcome
    when: str
    duration: float
    start: float
    stop: float
    location: tuple[str, int | None, str] | None = None
    longrepr: str | None = None
    sections: list[tuple[str, str]] | None = None
    wasxfail: str | None = None


TestEvent = Annotated[Union[TestStarted, TestFinished], Field(discriminator="type")]
_event_adapter: TypeAdapter[TestEvent] = TypeAdapter(TestEvent)


def read_events(path: Path) -> list[TestEvent]:
    """Read JSONL events file, skipping malformed/truncated lines."""
    events: list[TestEvent] = []
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return events

    for lineno, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            events.append(_event_adapter.validate_json(line))
        except Exception as exc:
            logger.warning("Skipping malformed line %d: %s", lineno, exc)

    return events


def resolve_events(events: list[TestEvent]) -> list[TestFinished]:
    """Match TestStarted/TestFinished pairs; synthesize failures for crashes.

    Any TestStarted without a corresponding TestFinished is converted into a
    synthetic TestFinished with outcome=FAILED, indicating a crash.
    """
    finished_nodeids: set[str] = set()
    for ev in events:
        if isinstance(ev, TestFinished):
            finished_nodeids.add(ev.nodeid)

    resolved: list[TestFinished] = []
    for ev in events:
        if isinstance(ev, TestFinished):
            resolved.append(ev)
        elif isinstance(ev, TestStarted) and ev.nodeid not in finished_nodeids:
            resolved.append(
                TestFinished(
                    nodeid=ev.nodeid,
                    outcome=Outcome.FAILED,
                    when="call",
                    duration=0.0,
                    start=ev.start,
                    stop=ev.start,
                    location=ev.location,
                    longrepr=CRASH_REPR,
                )
            )

    return resolved
