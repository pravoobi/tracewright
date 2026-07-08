from __future__ import annotations

import io
from pathlib import PurePosixPath

import structlog
from minio import Minio
from minio.error import S3Error

from backend.src.config import settings

log = structlog.get_logger()

_client: Minio | None = None


def get_minio() -> Minio:
    global _client
    if _client is None:
        _client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        _ensure_bucket()
    return _client


def _ensure_bucket() -> None:
    client = _client
    assert client is not None
    if not client.bucket_exists(settings.minio_bucket):
        client.make_bucket(settings.minio_bucket)
        log.info("minio.bucket_created", bucket=settings.minio_bucket)


def upload_file(object_name: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    client = get_minio()
    client.put_object(
        settings.minio_bucket,
        object_name,
        io.BytesIO(data),
        length=len(data),
        content_type=content_type,
    )
    log.info("storage.uploaded", object_name=object_name, size=len(data))
    return object_name


def download_file(object_name: str) -> bytes:
    client = get_minio()
    response = client.get_object(settings.minio_bucket, object_name)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


def delete_file(object_name: str) -> None:
    client = get_minio()
    client.remove_object(settings.minio_bucket, object_name)


def artifact_path(tenant_id: str, artifact_id: str, filename: str) -> str:
    return str(PurePosixPath("artifacts") / tenant_id / artifact_id / filename)


def auth_session_path(tenant_id: str, environment_id: str) -> str:
    return str(PurePosixPath("auth-sessions") / tenant_id / f"{environment_id}.enc")


def registry_path(tenant_id: str, environment_id: str) -> str:
    return str(PurePosixPath("registries") / tenant_id / f"{environment_id}.json")
