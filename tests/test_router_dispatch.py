"""SourceRouter dispatches by source_type to registered backends."""
from __future__ import annotations
import pytest

from openrevise.sources.router import SourceRouter, BackendNotRegistered


def test_dispatches_by_source_type():
    router = SourceRouter()
    calls = []
    router.register("preprint", lambda spec: calls.append(("preprint", spec)) or "ok")
    router.register("biomed", lambda spec: calls.append(("biomed", spec)) or "ok")
    spec = {"source_id": "arxiv", "source_type": "preprint", "query": "HFrEF"}
    assert router.dispatch(spec) == "ok"
    assert calls == [("preprint", spec)]


def test_unknown_source_type_raises():
    router = SourceRouter()
    with pytest.raises(BackendNotRegistered):
        router.dispatch({"source_type": "unknown"})
