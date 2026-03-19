"""Sources package — literature search, citation management, and PDF reading."""

from ideaclaw.sources.scholar import search_for_papers, SemanticScholarSearch
from ideaclaw.sources.citation import CitationManager
from ideaclaw.sources.pdf_reader import load_paper

__all__ = [
    "search_for_papers",
    "SemanticScholarSearch",
    "CitationManager",
    "load_paper",
]
