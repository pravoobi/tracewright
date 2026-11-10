"""Stage 1: Per-page classification — native text vs scanned, language, page manifest."""
from __future__ import annotations

import io
from dataclasses import dataclass, field

import structlog

log = structlog.get_logger()

SCANNED_CHAR_THRESHOLD = 50  # fewer extracted chars on a non-blank page → scanned


@dataclass
class PageManifest:
    page_number: int
    page_type: str  # 'native' | 'scanned' | 'blank'
    word_count: int
    language: str = "en"


@dataclass
class TriageResult:
    filename: str
    total_pages: int
    pages: list[PageManifest] = field(default_factory=list)
    language: str = "en"
    is_password_protected: bool = False
    is_oversized: bool = False
    file_type: str = "pdf"


def triage_document(filename: str, data: bytes, max_pages: int = 500) -> TriageResult:
    ext = filename.rsplit(".", 1)[-1].lower()

    if ext in ("xlsx", "xls", "csv"):
        return _triage_spreadsheet(filename, data)
    elif ext in ("docx", "doc"):
        return _triage_docx(filename, data)
    elif ext == "pdf":
        return _triage_pdf(filename, data, max_pages)
    else:
        log.warning("triage.unsupported_format", filename=filename, ext=ext)
        return TriageResult(filename=filename, total_pages=0, file_type=ext)


def _triage_pdf(filename: str, data: bytes, max_pages: int) -> TriageResult:
    import pypdf

    try:
        reader = pypdf.PdfReader(io.BytesIO(data))
    except pypdf.errors.PdfReadError:
        return TriageResult(filename=filename, total_pages=0, is_password_protected=True, file_type="pdf")

    if reader.is_encrypted:
        return TriageResult(filename=filename, total_pages=0, is_password_protected=True, file_type="pdf")

    total = len(reader.pages)
    is_oversized = total > max_pages
    pages: list[PageManifest] = []

    for i, page in enumerate(reader.pages[:max_pages]):
        text = page.extract_text() or ""
        stripped = text.strip()
        word_count = len(stripped.split()) if stripped else 0

        if not stripped:
            page_type = "blank"
        elif len(stripped) < SCANNED_CHAR_THRESHOLD:
            page_type = "scanned"
        else:
            page_type = "native"

        pages.append(PageManifest(page_number=i + 1, page_type=page_type, word_count=word_count))

    log.info(
        "triage.pdf",
        filename=filename,
        total_pages=total,
        scanned=sum(1 for p in pages if p.page_type == "scanned"),
        native=sum(1 for p in pages if p.page_type == "native"),
    )
    return TriageResult(
        filename=filename,
        total_pages=total,
        pages=pages,
        is_oversized=is_oversized,
        file_type="pdf",
    )


def _triage_docx(filename: str, data: bytes) -> TriageResult:
    from docx import Document

    doc = Document(io.BytesIO(data))
    word_count = sum(len(p.text.split()) for p in doc.paragraphs)
    pages = [PageManifest(page_number=1, page_type="native", word_count=word_count)]
    return TriageResult(filename=filename, total_pages=1, pages=pages, file_type="docx")


def _triage_spreadsheet(filename: str, data: bytes) -> TriageResult:
    if filename.lower().endswith(".csv"):
        # openpyxl (used below for real Excel files) can't open a CSV at
        # all -- it expects a zip-based .xlsx container. A CSV has no sheet
        # concept, so it's always exactly one "page".
        pages = [PageManifest(page_number=1, page_type="native", word_count=0)]
        return TriageResult(filename=filename, total_pages=1, pages=pages, file_type="csv")

    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    sheet_count = len(wb.sheetnames)
    pages = [PageManifest(page_number=i + 1, page_type="native", word_count=0) for i in range(sheet_count)]
    return TriageResult(filename=filename, total_pages=sheet_count, pages=pages, file_type="xlsx")
