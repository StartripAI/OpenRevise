"""DeepXiv-SDK backend (https://github.com/DeepXiv/deepxiv_sdk).

Optional dependency. Install with: pip install "openrevise[preprint-deepxiv]"
"""
from __future__ import annotations

from .router import BackendUnavailable


def search(spec: dict) -> list:
    try:
        import deepxiv_sdk  # type: ignore
    except ImportError as e:
        raise BackendUnavailable("deepxiv_sdk not installed") from e
    client = deepxiv_sdk.Client()  # placeholder; replace with actual SDK init when wired up
    return client.search(spec.get("query", ""), limit=spec.get("limit", 20))
