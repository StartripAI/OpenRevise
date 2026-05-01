"""Europe PMC REST client (https://europepmc.org/RestfulWebService)."""
from __future__ import annotations

from typing import Any, Dict, List

import requests

SEARCH_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"


def search(spec: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Run a query against Europe PMC; return [{id, title, ...}, ...]."""
    query = spec.get("query", "")
    limit = spec.get("limit", 25)
    params = {
        "query": query,
        "format": "json",
        "pageSize": limit,
    }
    response = requests.get(SEARCH_URL, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()
    results = data.get("resultList", {}).get("result", [])
    return list(results)
