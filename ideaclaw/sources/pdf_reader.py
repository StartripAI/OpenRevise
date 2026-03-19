"""PDF to text extraction with fallback chain.

Ported from AI-Scientist's `load_paper()`.
Tries pymupdf4llm → pymupdf → pypdf in order.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

__all__ = ["load_paper"]


def load_paper(
    pdf_path: str | Path,
    num_pages: Optional[int] = None,
    min_size: int = 100,
) -> str:
    """Extract text from a PDF file.

    Uses a 3-level fallback chain:
    1. pymupdf4llm (best markdown output)
    2. pymupdf (good text extraction)
    3. pypdf (basic text extraction)

    Args:
        pdf_path: Path to the PDF file.
        num_pages: Optional limit on number of pages to extract.
        min_size: Minimum text length to consider valid.

    Returns:
        Extracted text content.

    Raises:
        FileNotFoundError: If PDF file doesn't exist.
        RuntimeError: If all extraction methods fail.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    # Try pymupdf4llm first (best quality markdown output)
    try:
        import pymupdf4llm

        if num_pages is None:
            text = pymupdf4llm.to_markdown(str(pdf_path))
        else:
            text = pymupdf4llm.to_markdown(str(pdf_path), pages=list(range(num_pages)))

        if len(text) >= min_size:
            logger.debug(f"Extracted {len(text)} chars via pymupdf4llm")
            return text
        raise ValueError("Text too short")
    except Exception as e:
        logger.debug(f"pymupdf4llm failed: {e}")

    # Try pymupdf (fitz)
    try:
        import pymupdf

        doc = pymupdf.open(str(pdf_path))
        pages = doc[:num_pages] if num_pages else doc
        text = ""
        for page in pages:
            text += page.get_text()

        if len(text) >= min_size:
            logger.debug(f"Extracted {len(text)} chars via pymupdf")
            return text
        raise ValueError("Text too short")
    except Exception as e:
        logger.debug(f"pymupdf failed: {e}")

    # Try pypdf (basic fallback)
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(pdf_path))
        pages = reader.pages[:num_pages] if num_pages else reader.pages
        text = "".join(page.extract_text() or "" for page in pages)

        if len(text) >= min_size:
            logger.debug(f"Extracted {len(text)} chars via pypdf")
            return text
        raise ValueError("Text too short")
    except ImportError:
        logger.error("No PDF library available. Install pymupdf4llm, pymupdf, or pypdf.")
    except Exception as e:
        logger.error(f"pypdf failed: {e}")

    raise RuntimeError(
        f"Failed to extract text from {pdf_path}. "
        "Ensure the file is a valid PDF and install pymupdf4llm: pip install pymupdf4llm"
    )
