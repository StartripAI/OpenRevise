"""Preprint router with priority-ordered engines and graceful fallback."""
from __future__ import annotations

from typing import Any, Callable, List, Tuple


class BackendUnavailable(RuntimeError):
    """Raised when a preprint engine is configured but not usable at runtime
    (e.g., optional dependency not installed, network unreachable, missing API key).

    The PreprintRouter catches this and tries the next configured engine.
    Other exceptions propagate (they indicate real bugs, not unavailability).
    """


class PreprintRouter:
    """Multi-engine preprint search with primary→fallback dispatch.

    Engines are tried in order. If an engine raises BackendUnavailable, the next
    engine is tried. If all engines are unavailable, returns an empty list (soft
    degradation).
    """

    def __init__(self, engines: List[Tuple[str, Callable[[dict], list]]]) -> None:
        self._engines = list(engines)

    def search(self, spec: dict) -> list:
        for _name, engine in self._engines:
            try:
                return engine(spec)
            except BackendUnavailable:
                continue
        return []
