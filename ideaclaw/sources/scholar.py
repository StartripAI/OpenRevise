"""Semantic Scholar & OpenAlex paper search.

Ported from AI-Scientist's generate_ideas.py `search_for_papers()`.
Adds OpenAlex fallback and structured result objects.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

__all__ = ["search_for_papers", "SemanticScholarSearch", "PaperResult"]

S2_API_KEY = os.environ.get("S2_API_KEY", "")


@dataclass
class PaperResult:
    """Structured paper search result."""

    title: str
    authors: str
    venue: str
    year: int
    abstract: str
    url: str = ""
    doi: str = ""
    citation_count: int = 0
    bibtex: str = ""
    paper_id: str = ""

    def to_citation_string(self) -> str:
        """Format as a one-line citation."""
        return f"{self.authors} ({self.year}). {self.title}. {self.venue}."

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "title": self.title,
            "authors": self.authors,
            "venue": self.venue,
            "year": self.year,
            "abstract": self.abstract,
            "url": self.url,
            "doi": self.doi,
            "citation_count": self.citation_count,
            "bibtex": self.bibtex,
            "paper_id": self.paper_id,
        }


class SemanticScholarSearch:
    """Search Semantic Scholar with retry and rate-limiting."""

    BASE_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
    FIELDS = "title,authors,venue,year,abstract,citationStyles,citationCount,externalIds,url"

    def __init__(self, api_key: str = ""):
        self.api_key = api_key or S2_API_KEY

    def search(
        self,
        query: str,
        limit: int = 10,
        year_range: Optional[str] = None,
    ) -> List[PaperResult]:
        """Search for papers on Semantic Scholar.

        Args:
            query: Search query string.
            limit: Maximum number of results (max 100).
            year_range: Optional year filter, e.g. "2020-2025" or "2024-".

        Returns:
            List of PaperResult objects.
        """
        if not query:
            return []

        params: Dict[str, Any] = {
            "query": query,
            "limit": min(limit, 100),
            "fields": self.FIELDS,
        }
        if year_range:
            params["year"] = year_range

        url = f"{self.BASE_URL}?{urllib.parse.urlencode(params)}"
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["X-API-KEY"] = self.api_key

        return self._fetch(url, headers)

    def _fetch(self, url: str, headers: Dict[str, str], retries: int = 3) -> List[PaperResult]:
        """Fetch with exponential backoff."""
        for attempt in range(retries):
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                return self._parse_results(data)
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    wait = 2 ** (attempt + 1)
                    logger.warning("Rate limited. Retrying in %ds...", wait)
                    time.sleep(wait)
                    continue
                logger.error("Semantic Scholar API error %d", e.code)
                return []
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                logger.error("Semantic Scholar connection error: %s", e)
                if attempt < retries - 1:
                    time.sleep(1)
                    continue
                return []
        return []

    def _parse_results(self, data: Dict) -> List[PaperResult]:
        """Parse Semantic Scholar API response into PaperResult objects."""
        results = []
        for item in data.get("data", []):
            authors_list = item.get("authors") or []
            author_names = ", ".join(a.get("name", "") for a in authors_list[:5])
            if len(authors_list) > 5:
                author_names += " et al."

            bibtex = ""
            cite_styles = item.get("citationStyles", {})
            if cite_styles:
                bibtex = cite_styles.get("bibtex", "")

            external_ids = item.get("externalIds", {}) or {}

            results.append(
                PaperResult(
                    title=item.get("title") or "",
                    authors=author_names,
                    venue=item.get("venue") or "",
                    year=item.get("year") or 0,
                    abstract=item.get("abstract") or "",
                    url=item.get("url") or "",
                    doi=external_ids.get("DOI") or "",
                    citation_count=item.get("citationCount") or 0,
                    bibtex=bibtex,
                    paper_id=item.get("paperId") or "",
                )
            )
        return results


class OpenAlexSearch:
    """Fallback search using OpenAlex API."""

    BASE_URL = "https://api.openalex.org/works"

    def search(self, query: str, limit: int = 10) -> List[PaperResult]:
        """Search OpenAlex for papers with retry."""
        if not query:
            return []

        params = {
            "search": query,
            "per_page": min(limit, 25),
            "select": "title,authorships,primary_location,publication_year,abstract_inverted_index,doi,cited_by_count,id",
        }
        url = f"{self.BASE_URL}?{urllib.parse.urlencode(params)}"
        headers = {"Accept": "application/json", "User-Agent": "IdeaClaw/0.1 (mailto:research@startripai.com)"}

        for attempt in range(3):
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                return self._parse_results(data)
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < 2:
                    wait = 2 ** (attempt + 1)
                    logger.warning("OpenAlex rate limited. Retrying in %ds...", wait)
                    time.sleep(wait)
                    continue
                logger.error("OpenAlex API error %d", e.code)
                return []
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                logger.error("OpenAlex connection error: %s", e)
                if attempt < 2:
                    time.sleep(1)
                    continue
                return []
        return []

    def _parse_results(self, data: Dict) -> List[PaperResult]:
        """Parse OpenAlex API response."""
        results = []
        for item in data.get("results", []):
            # Reconstruct abstract from inverted index
            abstract = ""
            inv_idx = item.get("abstract_inverted_index")
            if inv_idx:
                word_positions = []
                for word, positions in inv_idx.items():
                    for pos in positions:
                        word_positions.append((pos, word))
                word_positions.sort()
                abstract = " ".join(w for _, w in word_positions)

            authors = ", ".join(
                a.get("author", {}).get("display_name", "")
                for a in (item.get("authorships", []) or [])[:5]
            )

            loc = item.get("primary_location", {}) or {}
            venue = ""
            if loc.get("source"):
                venue = loc["source"].get("display_name", "")

            results.append(
                PaperResult(
                    title=item.get("title", "") or "",
                    authors=authors,
                    venue=venue,
                    year=item.get("publication_year", 0) or 0,
                    abstract=abstract[:500],
                    doi=item.get("doi", "") or "",
                    citation_count=item.get("cited_by_count", 0) or 0,
                    paper_id=item.get("id", "") or "",
                )
            )
        return results


def search_for_papers(
    query: str,
    limit: int = 10,
    engine: str = "semanticscholar",
    year_range: Optional[str] = None,
) -> List[PaperResult]:
    """Search for academic papers (convenience function).

    Tries Semantic Scholar first, falls back to OpenAlex.

    Args:
        query: Search query.
        limit: Max results.
        engine: "semanticscholar" or "openalex".
        year_range: Optional year filter for Semantic Scholar.

    Returns:
        List of PaperResult objects.
    """
    if engine == "semanticscholar":
        results = SemanticScholarSearch().search(query, limit, year_range)
        if results:
            return results
        logger.info("Semantic Scholar returned no results, trying OpenAlex...")
        return OpenAlexSearch().search(query, limit)
    elif engine == "openalex":
        results = OpenAlexSearch().search(query, limit)
        if results:
            return results
        logger.info("OpenAlex returned no results, trying Semantic Scholar...")
        return SemanticScholarSearch().search(query, limit)
    else:
        raise ValueError(f"Unknown engine: {engine}. Use 'semanticscholar' or 'openalex'.")
