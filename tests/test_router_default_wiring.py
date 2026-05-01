"""default_router() wires preprint/biomed/local backends correctly."""
from __future__ import annotations
import pytest

from openrevise.sources.router import default_router


def test_default_router_dispatches_arxiv_to_preprint():
    calls = []

    def fake_preprint_engine(spec):
        calls.append(spec.get("source_id"))
        return [{"id": "fake"}]

    router = default_router(preprint_engine=fake_preprint_engine)
    out = router.dispatch({"source_id": "arxiv", "source_type": "preprint", "query": "x"})
    assert calls == ["arxiv"]
    assert out[0]["id"] == "fake"


def test_default_router_dispatches_pubmed(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "openrevise.sources.biomed.pubmed.search",
        lambda spec: calls.append("pubmed") or [{"pmid": "1"}],
    )
    router = default_router()
    out = router.dispatch({"source_id": "pubmed", "source_type": "biomed", "query": "x"})
    assert calls == ["pubmed"]
    assert out[0]["pmid"] == "1"


def test_default_router_dispatches_europepmc(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "openrevise.sources.biomed.europepmc.search",
        lambda spec: calls.append("europepmc") or [{"id": "PMC1"}],
    )
    router = default_router()
    out = router.dispatch({"source_id": "europe_pmc", "source_type": "biomed", "query": "x"})
    assert calls == ["europepmc"]


def test_default_router_dispatches_pmc(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "openrevise.sources.biomed.pmc.search",
        lambda spec: calls.append("pmc") or [{"pmcid": "PMC2"}],
    )
    router = default_router()
    out = router.dispatch({"source_id": "pmc", "source_type": "biomed", "query": "x"})
    assert calls == ["pmc"]
