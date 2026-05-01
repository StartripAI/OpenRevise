"""PMC (PubMed Central) client via NCBI E-utilities."""
from __future__ import annotations

from typing import Any, Dict, List

import requests

ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"


def search(spec: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Run an esearch query against PMC; return [{pmcid}, ...]."""
    query = spec.get("query", "")
    limit = spec.get("limit", 20)
    api_key = spec.get("api_key")
    params: Dict[str, Any] = {
        "db": "pmc",
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
    return [{"pmcid": pmcid} for pmcid in id_list]
