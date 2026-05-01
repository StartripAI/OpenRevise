#!/usr/bin/env python3
"""
Evidence extraction helpers for local sources (PDF/DOCX/PPTX/images).

Design goals:
- Prefer lightweight native parsing first.
- Allow optional fallbacks (markitdown/docling) when installed.
- Keep extraction deterministic and dependency-optional.
"""

from __future__ import annotations

import os
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

from pypdf import PdfReader


W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
A_NS = "{http://schemas.openxmlformats.org/drawingml/2006/main}"


@dataclass(frozen=True)
class ExtractResult:
    text: str
    detail: str


def _normalize_join(chunks: Iterable[str]) -> str:
    return "\n".join([c for c in chunks if c]).strip()


def _parse_index_hints(location_hints: Sequence[str] | None, prefix: str) -> List[int]:
    if not location_hints:
        return []
    out: List[int] = []
    for raw in location_hints:
        hint = str(raw).strip().lower()
        if not hint.startswith(prefix + ":"):
            continue
        value = hint.split(":", 1)[1].strip()
        if not value:
            continue
        if "-" in value:
            left, right = value.split("-", 1)
            if left.strip().isdigit() and right.strip().isdigit():
                start = int(left.strip())
                end = int(right.strip())
                lo = min(start, end)
                hi = max(start, end)
                for idx in range(lo, hi + 1):
                    out.append(idx)
        elif value.isdigit():
            out.append(int(value))
    dedup = sorted(set([x for x in out if x > 0]))
    return dedup


def extract_pdf_text(path: Path, location_hints: Sequence[str] | None = None) -> ExtractResult:
    reader = PdfReader(str(path))
    page_indices = _parse_index_hints(location_hints, "page")
    total_pages = len(reader.pages)
    if not page_indices:
        chunks = [(page.extract_text() or "") for page in reader.pages]
        return ExtractResult(
            text=_normalize_join(chunks),
            detail=f"native_pdf pages=1-{total_pages}",
        )

    chunks: List[str] = []
    used: List[int] = []
    for idx_1based in page_indices:
        idx_0 = idx_1based - 1
        if 0 <= idx_0 < total_pages:
            used.append(idx_1based)
            chunks.append(reader.pages[idx_0].extract_text() or "")
    return ExtractResult(
        text=_normalize_join(chunks),
        detail=f"native_pdf pages={','.join(str(x) for x in used)}",
    )


def extract_docx_text(path: Path, location_hints: Sequence[str] | None = None) -> ExtractResult:
    paragraph_hints = _parse_index_hints(location_hints, "paragraph")
    with zipfile.ZipFile(path, "r") as zf:
        from xml.etree import ElementTree as ET

        root = ET.fromstring(zf.read("word/document.xml"))
        body = root.find(f"{W_NS}body")
        if body is None:
            return ExtractResult(text="", detail="native_docx missing_body")
        paragraphs = body.findall(f"{W_NS}p")
        out: List[str] = []
        used: List[int] = []
        for i, para in enumerate(paragraphs, start=1):
            if paragraph_hints and i not in paragraph_hints:
                continue
            text = "".join((node.text or "") for node in para.iter(f"{W_NS}t")).strip()
            if text:
                out.append(text)
                used.append(i)
        detail = (
            f"native_docx paragraphs={','.join(str(x) for x in used)}"
            if paragraph_hints
            else f"native_docx paragraphs=1-{len(paragraphs)}"
        )
        return ExtractResult(text=_normalize_join(out), detail=detail)


def extract_pptx_text_native(path: Path, location_hints: Sequence[str] | None = None) -> ExtractResult:
    slide_hints = _parse_index_hints(location_hints, "slide")
    with zipfile.ZipFile(path, "r") as zf:
        from xml.etree import ElementTree as ET

        names = sorted(
            [
                n
                for n in zf.namelist()
                if n.startswith("ppt/slides/slide") and n.endswith(".xml")
            ],
            key=lambda item: int(re.search(r"slide(\d+)\.xml$", item).group(1)),  # type: ignore[arg-type]
        )
        out: List[str] = []
        used: List[int] = []
        for name in names:
            match = re.search(r"slide(\d+)\.xml$", name)
            if not match:
                continue
            slide_no = int(match.group(1))
            if slide_hints and slide_no not in slide_hints:
                continue
            root = ET.fromstring(zf.read(name))
            texts = [
                (node.text or "").strip()
                for node in root.iter(f"{A_NS}t")
                if (node.text or "").strip()
            ]
            if texts:
                used.append(slide_no)
                out.append(f"[slide {slide_no}] " + " ".join(texts))
        detail = (
            f"native_pptx slides={','.join(str(x) for x in used)}"
            if slide_hints
            else f"native_pptx slides=1-{len(names)}"
        )
        return ExtractResult(text=_normalize_join(out), detail=detail)


def _extract_image_text_pytesseract(path: Path) -> Tuple[str, str]:
    try:
        import pytesseract  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("pytesseract_not_installed") from exc
    try:
        from PIL import Image  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("pillow_not_installed") from exc
    image = Image.open(path).convert("RGB")
    text = pytesseract.image_to_string(image) or ""
    return text, "pytesseract"


def _extract_image_text_paddle(path: Path) -> Tuple[str, str]:
    # Avoid blocking runtime with online host checks.
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
    try:
        from paddleocr import PaddleOCR  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("paddleocr_not_installed") from exc
    ocr = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)
    result = ocr.ocr(str(path), cls=True)
    lines: List[str] = []
    for page in result or []:
        for item in page or []:
            if len(item) >= 2 and isinstance(item[1], (list, tuple)) and item[1]:
                text = str(item[1][0]).strip()
                if text:
                    lines.append(text)
    return "\n".join(lines), "paddleocr"


def _extract_image_text_easy(path: Path) -> Tuple[str, str]:
    try:
        import easyocr  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("easyocr_not_installed") from exc
    reader = easyocr.Reader(["ch_sim", "en"], gpu=False)
    result = reader.readtext(str(path), detail=0)
    lines = [str(x).strip() for x in (result or []) if str(x).strip()]
    return "\n".join(lines), "easyocr"


def _merge_ocr_texts(texts: Sequence[str]) -> str:
    seen = set()
    merged: List[str] = []
    for text in texts:
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            key = line.lower()
            if key in seen:
                continue
            seen.add(key)
            merged.append(line)
    return "\n".join(merged)


def extract_image_text_dual_ocr(path: Path, ocr_mode: str = "dual") -> ExtractResult:
    mode = (ocr_mode or "dual").strip().lower()
    if mode not in {"dual", "paddle", "easy"}:
        raise ValueError(f"Unsupported ocr_mode: {ocr_mode}")

    extracts: List[Tuple[str, str]] = []
    attempted_engines: List[str] = []
    errors: List[str] = []

    def run_one(fn) -> None:  # type: ignore[no-untyped-def]
        name_map = {
            "_extract_image_text_paddle": "paddleocr",
            "_extract_image_text_easy": "easyocr",
            "_extract_image_text_pytesseract": "pytesseract",
        }
        attempted_engines.append(name_map.get(fn.__name__, fn.__name__))
        try:
            text, engine = fn(path)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{fn.__name__}:{exc}")
            return
        if text.strip():
            extracts.append((engine, text))

    if mode in {"dual", "paddle"}:
        run_one(_extract_image_text_paddle)
    if mode in {"dual", "easy"}:
        run_one(_extract_image_text_easy)

    # Single-engine modes can fallback to pytesseract as a recovery path.
    if mode in {"dual", "paddle", "easy"} and not extracts:
        run_one(_extract_image_text_pytesseract)

    if not extracts:
        raise RuntimeError(
            "source_unreadable_or_ocr_failed; " + "; ".join(errors[:4])
            if errors
            else "source_unreadable_or_ocr_failed"
        )

    merged = _merge_ocr_texts([x[1] for x in extracts])
    engines = ",".join([x[0] for x in extracts])
    attempted = ",".join(attempted_engines)
    detail = f"image_ocr engines={engines}"
    if attempted:
        detail += f" attempted={attempted}"
    return ExtractResult(text=merged, detail=detail)


def extract_with_markitdown_optional(path: Path) -> ExtractResult:
    try:
        from markitdown import MarkItDown  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("markitdown_not_installed") from exc

    md = MarkItDown()
    result = md.convert(str(path))
    text = getattr(result, "text_content", None) or getattr(result, "text", None) or ""
    if not isinstance(text, str) or not text.strip():
        raise RuntimeError("markitdown_empty_output")
    return ExtractResult(text=text, detail="markitdown")


def extract_with_docling_optional(path: Path) -> ExtractResult:
    try:
        from docling.document_converter import DocumentConverter  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("docling_not_installed") from exc

    converter = DocumentConverter()
    conv = converter.convert(str(path))
    document = getattr(conv, "document", None)
    if document is None:
        raise RuntimeError("docling_missing_document")
    text = ""
    if hasattr(document, "export_to_markdown"):
        text = document.export_to_markdown() or ""
    elif hasattr(document, "export_to_text"):
        text = document.export_to_text() or ""
    if not text.strip():
        raise RuntimeError("docling_empty_output")
    return ExtractResult(text=text, detail="docling")


def extract_local_source_text(
    *,
    source_type: str,
    path: Path,
    extract_mode: str = "auto",
    ocr_mode: str = "dual",
    location_hints: Sequence[str] | None = None,
) -> ExtractResult:
    mode = (extract_mode or "auto").strip().lower()
    if mode not in {"auto", "native", "markitdown", "docling"}:
        raise ValueError(f"Unsupported extract_mode: {extract_mode}")

    if not path.exists():
        raise FileNotFoundError(f"Local file not found: {path}")

    native_extractors = {
        "local_pdf": lambda: extract_pdf_text(path, location_hints=location_hints),
        "local_docx": lambda: extract_docx_text(path, location_hints=location_hints),
        "local_pptx": lambda: extract_pptx_text_native(path, location_hints=location_hints),
        "local_image": lambda: extract_image_text_dual_ocr(path, ocr_mode=ocr_mode),
    }

    if source_type not in native_extractors:
        raise ValueError(f"Unsupported local source type: {source_type}")

    errors: List[str] = []

    def attempt_native() -> ExtractResult:
        return native_extractors[source_type]()

    def attempt_markitdown() -> ExtractResult:
        return extract_with_markitdown_optional(path)

    def attempt_docling() -> ExtractResult:
        return extract_with_docling_optional(path)

    attempts: List[Tuple[str, object]] = []
    if mode == "native":
        attempts = [("native", attempt_native)]
    elif mode == "markitdown":
        attempts = [("markitdown", attempt_markitdown)]
    elif mode == "docling":
        attempts = [("docling", attempt_docling)]
    else:
        attempts = [
            ("native", attempt_native),
            ("markitdown", attempt_markitdown),
            ("docling", attempt_docling),
        ]

    for label, fn in attempts:
        try:
            result = fn()  # type: ignore[misc]
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{label}:{exc}")
            continue
        if result.text.strip():
            return result
        errors.append(f"{label}:empty_output")

    raise RuntimeError("; ".join(errors[:5]) if errors else "extract_failed")
