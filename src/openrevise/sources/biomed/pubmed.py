"""PubMed client via NCBI E-utilities esearch.

Returns a list of `{pmid: ...}` dicts. Pair with a downstream esummary/efetch
call when richer metadata is needed; v0 only does ID retrieval.

E-utilities docs: https://www.ncbi.nlm.nih.gov/books/NBK25500/
No API key required for low-volume use; consider passing api_key for >3 req/sec.
"""
from __future__ import annotations

from typing import Any, Dict, List

import requests

ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"


def search(spec: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Run an esearch query against PubMed; return [{pmid, ...}, ...]."""
    query = spec.get("query", "")
    limit = spec.get("limit", 20)
    api_key = spec.get("api_key")
    params: Dict[str, Any] = {
        "db": "pubmed",
        "term": query,
        "retmax": limit,
        "retmode": "json",
    }
    if api_key:
        params["api_key"] = api_key
    response = requests.get(ESEARCH_URL, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()
    id_list = data.get("esearchresult", {}).get("idlist", [])
    return [{"pmid": pmid} for pmid in id_list]
