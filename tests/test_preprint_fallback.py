"""Preprint router falls back from primary engine to secondary on BackendUnavailable."""
from __future__ import annotations
from openrevise.sources.preprint.router import PreprintRouter, BackendUnavailable


def test_falls_back_when_primary_unavailable():
    seen = []

    def primary(spec):
        seen.append("primary")
        raise BackendUnavailable("deepxiv not installed")

    def fallback(spec):
        seen.append("fallback")
        return [{"id": "arxiv:2603.00084", "title": "DeepXiv-SDK"}]

    router = PreprintRouter(engines=[("deepxiv", primary), ("arxiv_native", fallback)])
    out = router.search({"query": "DeepXiv"})
    assert seen == ["primary", "fallback"]
    assert out[0]["id"].startswith("arxiv:")


def test_disabled_engine_returns_empty():
    router = PreprintRouter(engines=[])
    assert router.search({"query": "anything"}) == []


def test_primary_success_skips_fallback():
    seen = []

    def primary(spec):
        seen.append("primary")
        return [{"id": "arxiv:1234"}]

    def fallback(spec):
        seen.append("fallback")
        return [{"id": "arxiv:9999"}]

    router = PreprintRouter(engines=[("primary", primary), ("fallback", fallback)])
    out = router.search({"query": "x"})
    assert seen == ["primary"]
    assert out[0]["id"] == "arxiv:1234"
