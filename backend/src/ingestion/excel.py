"""Bug export parser: Excel → canonical Bug schema with column-mapper support."""
from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any

import openpyxl
import pandas as pd
import structlog

log = structlog.get_logger()

# Canonical column names in our schema
CANONICAL_COLUMNS = [
    "external_id", "title", "description", "severity", "component",
    "status", "root_cause", "fix_version", "linked_story", "closed_at",
]

# Common aliases customers use — LLM-assisted mapping happens at first import
_ALIAS_MAP: dict[str, str] = {
    "id": "external_id",
    "bug id": "external_id",
    "issue id": "external_id",
    "ticket id": "external_id",
    "summary": "title",
    "desc": "description",
    "details": "description",
    "sev": "severity",
    "priority": "severity",
    "module": "component",
    "area": "component",
    "state": "status",
    "resolution": "status",
    "root cause": "root_cause",
    "cause": "root_cause",
    "fix version": "fix_version",
    "resolved in": "fix_version",
    "story": "linked_story",
    "jira": "linked_story",
    "closed": "closed_at",
    "resolved date": "closed_at",
    "close date": "closed_at",
}


@dataclass
class BugRecord:
    external_id: str | None = None
    title: str = ""
    description: str | None = None
    severity: str | None = None
    component: str | None = None
    status: str | None = None
    root_cause: str | None = None
    fix_version: str | None = None
    linked_story: str | None = None
    closed_at: str | None = None
    raw: dict[str, Any] | None = None


def parse_bug_export(
    data: bytes,
    column_mapping: dict[str, str] | None = None,
) -> tuple[list[BugRecord], list[str]]:
    """
    Parse Excel bug export into BugRecords.
    Returns (records, unmapped_columns) — caller shows unmapped columns in the UI
    for the column-mapper one-time setup.
    """
    df = pd.read_excel(io.BytesIO(data), dtype=str)
    df.columns = [str(c).strip().lower() for c in df.columns]

    # Build effective mapping: explicit mapping overrides aliases
    effective_map: dict[str, str] = {}
    for col in df.columns:
        if column_mapping and col in column_mapping:
            effective_map[col] = column_mapping[col]
        elif col in _ALIAS_MAP:
            effective_map[col] = _ALIAS_MAP[col]
        elif col in CANONICAL_COLUMNS:
            effective_map[col] = col

    unmapped = [c for c in df.columns if c not in effective_map]

    records: list[BugRecord] = []
    for _, row in df.iterrows():
        mapped: dict[str, Any] = {effective_map[c]: row[c] for c in df.columns if c in effective_map}
        records.append(BugRecord(
            external_id=mapped.get("external_id"),
            title=str(mapped.get("title", "")).strip() or "Untitled",
            description=mapped.get("description"),
            severity=mapped.get("severity"),
            component=mapped.get("component"),
            status=mapped.get("status"),
            root_cause=mapped.get("root_cause"),
            fix_version=mapped.get("fix_version"),
            linked_story=mapped.get("linked_story"),
            closed_at=str(mapped.get("closed_at")) if mapped.get("closed_at") else None,
            raw=row.to_dict(),
        ))

    log.info("excel.parsed", records=len(records), unmapped_columns=unmapped)
    return records, unmapped


async def suggest_column_mapping(columns: list[str], tenant_id: str | None = None) -> dict[str, str]:
    """LLM-assisted suggestion for unmapped columns. Customer confirms in the UI."""
    from backend.src.llm.client import complete
    import json

    prompt = (
        f"Map these spreadsheet column names to canonical bug fields.\n"
        f"Canonical fields: {', '.join(CANONICAL_COLUMNS)}\n"
        f"Columns to map: {', '.join(columns)}\n\n"
        f"Respond with JSON only: {{\"column_name\": \"canonical_field_or_null\"}}"
    )
    try:
        raw = await complete(
            messages=[{"role": "user", "content": prompt}],
            tenant_id=tenant_id,
            feature="column_mapper",
        )
        return json.loads(raw)
    except Exception as e:
        log.warning("excel.mapping_suggestion_failed", error=str(e))
        return {}
