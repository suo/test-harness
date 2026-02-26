from __future__ import annotations

from rich.console import Console

from bridle._schema import TestEvent, TestFinished, TestStarted
from bridle.backends._base import Backend


class StubBackend(Backend):
    """Stub backend that logs events to stderr instead of uploading."""

    def name(self) -> str:
        return "stub"

    def upload(self, events: list[TestEvent]) -> None:
        started = sum(1 for e in events if isinstance(e, TestStarted))
        finished = sum(1 for e in events if isinstance(e, TestFinished))
        console = Console(stderr=True)
        console.print(
            f"[dim]StubBackend: would upload {len(events)} event(s) "
            f"({started} started, {finished} finished)[/dim]"
        )
