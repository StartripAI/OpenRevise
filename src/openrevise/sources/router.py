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


def default_router(
    *,
    preprint_engine: Callable[[dict], Any] | None = None,
) -> SourceRouter:
    """Build a SourceRouter wired with the standard backends.

    - preprint    → preprint_engine if provided, else PreprintRouter with deepXIV→arXiv fallback
    - biomed      → routed by source_id to pubmed/europepmc/pmc
    - local_*     → evidence_extractors.extract_local_source_text  (TODO: wire when needed)
    """
    from openrevise.sources.biomed import pubmed, europepmc, pmc
    from openrevise.sources.preprint.router import PreprintRouter
    from openrevise.sources.preprint import deepxiv as preprint_deepxiv
    from openrevise.sources.preprint import arxiv as preprint_arxiv

    if preprint_engine is None:
        preprint_router = PreprintRouter(
            engines=[
                ("deepxiv", preprint_deepxiv.search),
                ("arxiv_native", preprint_arxiv.search),
            ]
        )
        preprint_engine = preprint_router.search

    def biomed_dispatch(spec: dict) -> Any:
        source_id = spec.get("source_id", "")
        if source_id == "pubmed":
            return pubmed.search(spec)
        if source_id == "europe_pmc":
            return europepmc.search(spec)
        if source_id == "pmc":
            return pmc.search(spec)
        raise BackendNotRegistered(f"biomed source_id '{source_id}' unknown")

    router = SourceRouter()
    router.register("preprint", preprint_engine)
    router.register("biomed", biomed_dispatch)
    return router
