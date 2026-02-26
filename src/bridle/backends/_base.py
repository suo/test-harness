from __future__ import annotations

from abc import ABC, abstractmethod

from bridle._schema import TestEvent


class Backend(ABC):
    """Abstract base class for test result upload backends."""

    @abstractmethod
    def upload(self, events: list[TestEvent]) -> None:
        """Upload test events to the backend."""

    @abstractmethod
    def name(self) -> str:
        """Human-readable name for this backend."""
