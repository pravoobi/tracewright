"""Upload endpoint: file → MinIO → arq parsing job."""
from __future__ import annotations

import os
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.auth.api_key import require_tenant_access
from backend.src.config import settings
from backend.src.db.models import SourceArtifact
from backend.src.db.session import get_session
from backend.src.storage.files import artifact_path, upload_file
from backend.src.worker import enqueue_parse_job

router = APIRouter(
    prefix="/upload",
    tags=["upload"],
    dependencies=[Depends(require_tenant_access)],
)

ALLOWED_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/csv",
}

_UNSAFE_FILENAME_CHARS = re.compile(r"[^\w.-]")


def _safe_upload_filename(filename: str | None) -> str:
    """The MinIO object key is built as artifacts/{tenant_id}/{artifact_id}/
    {filename} -- filename is entirely client-controlled (the multipart
    field), so an unsanitized "../other-tenant/evil.pdf" or a filename
    containing "/" lets a caller spoof key prefixes or scatter orphaned
    objects outside its own artifact_id namespace. basename() strips any
    directory components; the charset whitelist handles the rest."""
    base = os.path.basename(filename or "upload") or "upload"
    return _UNSAFE_FILENAME_CHARS.sub("_", base)


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

    # Read in bounded chunks rather than file.read() (which buffers the
    # entire upload into memory regardless of size) -- a client can omit or
    # lie about Content-Length, so the real limit has to be enforced against
    # bytes actually received, not the declared size.
    limit = settings.max_upload_size_bytes
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise HTTPException(
                status_code=413,
                detail=f"File exceeds maximum upload size of {limit // (1024 * 1024)} MB",
            )
        chunks.append(chunk)
    data = b"".join(chunks)
    # Normalizes tenant_id to a safe charset before it's used to build the
    # storage key below (str(uuid.UUID(...)), not the raw path param).
    tenant_uuid_str = str(uuid.UUID(tenant_id))
    artifact_id = str(uuid.uuid4())
    safe_filename = _safe_upload_filename(file.filename)
    # The bug-export parser picks CSV vs Excel by extension, so a text/csv
    # upload named e.g. "bugs" must get one or it is read as .xlsx and fails.
    if "csv" in (file.content_type or "") and not safe_filename.lower().endswith(".csv"):
        safe_filename += ".csv"

    storage_path = artifact_path(tenant_uuid_str, artifact_id, safe_filename)
    upload_file(storage_path, data, file.content_type or "application/octet-stream")

    # Determine artifact type: by declared content type OR file extension
    # (a "text/csv" upload named "bugs" has no .csv extension, and the parser
    # keys off the extension, so the extension is normalised below).
    content_type = file.content_type or ""
    if (
        "spreadsheet" in content_type
        or "excel" in content_type
        or "csv" in content_type
        or safe_filename.lower().endswith((".xlsx", ".xls", ".csv"))
    ):
        artifact_type = "bug_export"
    else:
        artifact_type = "document"

    artifact = SourceArtifact(
        id=uuid.UUID(artifact_id),
        tenant_id=uuid.UUID(tenant_id),
        type=artifact_type,
        filename=safe_filename,
        version=version,
        storage_path=storage_path,
        status="queued",
    )
    session.add(artifact)
    await session.commit()

    await enqueue_parse_job(
        artifact_id=artifact_id,
        tenant_id=tenant_id,
        filename=safe_filename,
        storage_path=storage_path,
        artifact_type=artifact_type,
    )

    return {
        "artifact_id": artifact_id,
        "status": "queued",
        "message": "File uploaded and queued for processing.",
    }
