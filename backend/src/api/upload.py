"""Upload endpoint: file → MinIO → arq parsing job."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.db.models import SourceArtifact
from backend.src.db.session import get_session
from backend.src.storage.files import artifact_path, upload_file
from backend.src.worker import enqueue_parse_job

router = APIRouter(prefix="/upload", tags=["upload"])

ALLOWED_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/csv",
}


@router.post("/{tenant_id}")
async def upload_document(
    tenant_id: str,
    file: UploadFile,
    version: str = "1.0",
    session: AsyncSession = Depends(get_session),
):
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type: {file.content_type}. Allowed: PDF, Excel, DOCX.",
        )

    data = await file.read()
    artifact_id = str(uuid.uuid4())

    storage_path = artifact_path(tenant_id, artifact_id, file.filename or "upload")
    upload_file(storage_path, data, file.content_type or "application/octet-stream")

    # Determine artifact type
    if "spreadsheet" in (file.content_type or "") or "excel" in (file.content_type or "") or "csv" in (file.content_type or ""):
        artifact_type = "bug_export"
    elif file.filename and file.filename.lower().endswith(".xlsx"):
        artifact_type = "bug_export"
    else:
        artifact_type = "document"

    artifact = SourceArtifact(
        id=uuid.UUID(artifact_id),
        tenant_id=uuid.UUID(tenant_id),
        type=artifact_type,
        filename=file.filename or "upload",
        version=version,
        storage_path=storage_path,
        status="queued",
    )
    session.add(artifact)
    await session.commit()

    await enqueue_parse_job(
        artifact_id=artifact_id,
        tenant_id=tenant_id,
        filename=file.filename or "upload",
        storage_path=storage_path,
        artifact_type=artifact_type,
    )

    return {
        "artifact_id": artifact_id,
        "status": "queued",
        "message": "File uploaded and queued for processing.",
    }
