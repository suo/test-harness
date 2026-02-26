from __future__ import annotations

from bridle.backends._base import Backend
from bridle.backends._buildkite import BuildkiteBackend
from bridle.backends._mslci import MslciBackend
from bridle.backends._stub import StubBackend

_REGISTRY: dict[str, type[Backend]] = {
    "stub": StubBackend,
    "buildkite": BuildkiteBackend,
    "mslci": MslciBackend,
}


def get_backend(name: str) -> Backend:
    """Look up and instantiate a backend by name."""
    cls = _REGISTRY.get(name)
    if cls is None:
        available = ", ".join(sorted(_REGISTRY))
        raise ValueError(
            f"Unknown backend {name!r}. Available backends: {available}"
        )
    return cls()


def get_backends(names: str) -> list[Backend]:
    """Look up and instantiate backends from a comma-separated string."""
    return [get_backend(n.strip()) for n in names.split(",")]


__all__ = ["Backend", "BuildkiteBackend", "MslciBackend", "StubBackend", "get_backend", "get_backends"]
