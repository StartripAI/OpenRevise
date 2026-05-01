"""Native arXiv API client (https://export.arxiv.org/api/query). No paywall, no auth."""
from __future__ import annotations

from urllib.parse import urlencode

from .router import BackendUnavailable

ARXIV_ENDPOINT = "https://export.arxiv.org/api/query"


def search(spec: dict) -> list:
    try:
        import feedparser  # type: ignore
    except ImportError as e:
        raise BackendUnavailable(
            "feedparser not installed; pip install openrevise[preprint-arxiv]"
        ) from e
    query = spec.get("query", "")
    limit = spec.get("limit", 20)
    url = f"{ARXIV_ENDPOINT}?{urlencode({'search_query': query, 'max_results': limit})}"
    feed = feedparser.parse(url)
    return [
        {
            "id": entry.get("id", ""),
            "title": entry.get("title", ""),
            "summary": entry.get("summary", ""),
            "authors": [a.get("name", "") for a in entry.get("authors", [])],
            "published": entry.get("published", ""),
        }
        for entry in feed.entries
    ]
