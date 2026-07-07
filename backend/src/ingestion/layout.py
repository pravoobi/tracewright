"""Stage 2: Layout extraction — Docling for native pages, MinerU stub for scanned."""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import Any

import structlog

from backend.src.config import settings
from backend.src.ingestion.triage import TriageResult

log = structlog.get_logger()


@dataclass
class Block:
    block_type: str  # heading | paragraph | list_item | table | figure_caption
    content: str
    page_number: int
    level: int = 0  # heading level (1-6), 0 for non-headings
    table_data: list[list[str]] = field(default_factory=list)
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class LayoutResult:
    filename: str
    blocks: list[Block] = field(default_factory=list)
    raw_json: dict[str, Any] = field(default_factory=dict)


def extract_layout(filename: str, data: bytes, triage: TriageResult) -> LayoutResult:
    ext = triage.file_type

    if ext in ("xlsx", "xls"):
        return _extract_excel(filename, data)
    elif ext == "docx":
        return _extract_docx(filename, data)
    elif ext == "pdf":
        return _extract_pdf(filename, data, triage)
    else:
        log.warning("layout.unsupported", filename=filename, ext=ext)
        return LayoutResult(filename=filename)


def _extract_pdf(filename: str, data: bytes, triage: TriageResult) -> LayoutResult:
    has_scanned = any(p.page_type == "scanned" for p in triage.pages)

    if settings.parsing_backend == "cloud":
        return _extract_cloud(filename, data)

    # Primary: Docling for all pages
    result = _extract_docling(filename, data)

    if has_scanned:
        log.info("layout.scanned_pages_detected", filename=filename)
        # MinerU / PaddleOCR-VL would run here for scanned pages; stub for now
        # until GPU infra is confirmed and AGPL license reviewed
        _annotate_low_confidence_scanned(result, triage)

    return result


def _extract_docling(filename: str, data: bytes) -> LayoutResult:
    from docling.document_converter import DocumentConverter

    converter = DocumentConverter()
    # Docling accepts file paths; write to a temp buffer
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=f"_{filename}", delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name

    try:
        doc_result = converter.convert(tmp_path)
        doc = doc_result.document
    finally:
        os.unlink(tmp_path)

    blocks: list[Block] = []
    raw = {}

    try:
        raw = doc.export_to_dict()
    except Exception:
        pass

    for item, _level in doc.iterate_items():
        from docling_core.types.doc import TextItem, TableItem, SectionHeaderItem, ListItem

        if isinstance(item, SectionHeaderItem):
            blocks.append(Block(
                block_type="heading",
                content=item.text,
                page_number=_get_page(item),
                level=item.level if hasattr(item, "level") else 1,
                confidence=1.0,
            ))
        elif isinstance(item, TableItem):
            table_data = _extract_table_data(item)
            blocks.append(Block(
                block_type="table",
                content=item.export_to_markdown() if hasattr(item, "export_to_markdown") else "",
                page_number=_get_page(item),
                table_data=table_data,
                confidence=_table_confidence(item),
            ))
        elif isinstance(item, ListItem):
            blocks.append(Block(
                block_type="list_item",
                content=item.text,
                page_number=_get_page(item),
            ))
        elif isinstance(item, TextItem):
            blocks.append(Block(
                block_type="paragraph",
                content=item.text,
                page_number=_get_page(item),
            ))

    log.info("layout.docling", filename=filename, blocks=len(blocks))
    return LayoutResult(filename=filename, blocks=blocks, raw_json=raw)


def _get_page(item: Any) -> int:
    try:
        provenance = item.prov
        if provenance:
            return provenance[0].page_no
    except (AttributeError, IndexError):
        pass
    return 0


def _extract_table_data(item: Any) -> list[list[str]]:
    try:
        df = item.export_to_dataframe()
        return [df.columns.tolist()] + df.values.tolist()
    except Exception:
        return []


def _table_confidence(item: Any) -> float:
    # TableFormer provides a confidence score; fall back to 0.8 if unavailable
    try:
        return float(item.confidence)
    except (AttributeError, TypeError):
        return 0.8


def _annotate_low_confidence_scanned(result: LayoutResult, triage: TriageResult) -> None:
    scanned_pages = {p.page_number for p in triage.pages if p.page_type == "scanned"}
    for block in result.blocks:
        if block.page_number in scanned_pages:
            block.confidence = min(block.confidence, 0.6)
            block.metadata["needs_ocr_review"] = True


def _extract_cloud(filename: str, data: bytes) -> LayoutResult:
    # Placeholder for Mistral OCR / Gemini Flash cloud parsing path
    # Enabled only when PARSING_BACKEND=cloud in config
    raise NotImplementedError("Cloud parsing backend not yet implemented")


def _extract_docx(filename: str, data: bytes) -> LayoutResult:
    from docx import Document

    doc = Document(io.BytesIO(data))
    blocks: list[Block] = []

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        style = para.style.name if para.style else ""
        if "Heading" in style:
            try:
                level = int(style.split()[-1])
            except (ValueError, IndexError):
                level = 1
            blocks.append(Block(block_type="heading", content=text, page_number=1, level=level))
        elif style.startswith("List"):
            blocks.append(Block(block_type="list_item", content=text, page_number=1))
        else:
            blocks.append(Block(block_type="paragraph", content=text, page_number=1))

    return LayoutResult(filename=filename, blocks=blocks)


def _extract_excel(filename: str, data: bytes) -> LayoutResult:
    import openpyxl
    import pandas as pd

    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    blocks: list[Block] = []

    for sheet_idx, sheet_name in enumerate(wb.sheetnames):
        ws = wb[sheet_name]
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            continue
        # Treat first row as header
        table_data = [[str(c) if c is not None else "" for c in row] for row in rows]
        blocks.append(Block(
            block_type="table",
            content=f"Sheet: {sheet_name}",
            page_number=sheet_idx + 1,
            table_data=table_data,
            metadata={"sheet_name": sheet_name},
        ))

    return LayoutResult(filename=filename, blocks=blocks)
