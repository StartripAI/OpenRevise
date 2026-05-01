"""Source-type router: dispatches a source spec to its registered backend."""
from __future__ import annotations

from typing import Any, Callable, Dict


class BackendNotRegistered(KeyError):
    """Raised when a source spec's source_type has no registered backend."""


class SourceRouter:
    """Registry of (source_type → backend) mappings.

    A backend is any callable that accepts a source spec dict and returns a result.
    Pipeline code calls `router.dispatch(spec)` to route to the appropriate backend.
    """

    def __init__(self) -> None:
        self._backends: Dict[str, Callable[[dict], Any]] = {}

    def register(self, source_type: str, backend: Callable[[dict], Any]) -> None:
        self._backends[source_type] = backend

    def dispatch(self, spec: dict) -> Any:
        source_type = spec.get("source_type", "")
        try:
            backend = self._backends[source_type]
        except KeyError as e:
            raise BackendNotRegistered(source_type) from e
        return backend(spec)
