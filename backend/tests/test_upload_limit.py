"""The upload cap must hold for chunked bodies (no Content-Length) too."""
import httpx
import pytest
from fastapi import FastAPI, Request

from backend.src.upload_limit import OVERHEAD_BYTES, UploadSizeLimitMiddleware

LIMIT = 1000
CAP = LIMIT + OVERHEAD_BYTES


def _app():
    app = FastAPI()
    app.add_middleware(UploadSizeLimitMiddleware, max_bytes_getter=lambda: LIMIT)
    seen = {"read": 0}

    @app.post("/api/v1/upload/{tenant}")
    async def up(tenant: str, request: Request):
        n = 0
        async for chunk in request.stream():
            n += len(chunk)
        seen["read"] = n
        return {"bytes": n}

    @app.post("/api/v1/upload/form-{tenant}")
    async def form(tenant: str, request: Request):
        # multipart parsing wraps read errors into a 400; we must still yield 413
        await request.form()
        return {"ok": True}

    @app.post("/other")
    async def other(request: Request):
        return {"bytes": len(await request.body())}

    return app, seen


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def _chunks(sizes):
    for s in sizes:
        yield b"x" * s


async def test_small_upload_passes():
    app, _ = _app()
    async with _client(app) as c:
        r = await c.post("/api/v1/upload/t1", content=b"x" * 500)
    assert r.status_code == 200 and r.json()["bytes"] == 500


async def test_declared_oversize_refused_before_reading():
    app, seen = _app()
    async with _client(app) as c:
        r = await c.post("/api/v1/upload/t1", content=b"x" * (CAP + 1))
    assert r.status_code == 413 and seen["read"] == 0


async def test_chunked_oversize_refused_without_content_length():
    app, _ = _app()
    async with _client(app) as c:
        # an async-generator body is sent chunked: no Content-Length header
        r = await c.post("/api/v1/upload/t1", content=_chunks([CAP // 2, CAP // 2, 10]))
    assert r.status_code == 413


async def test_chunked_under_limit_passes():
    app, _ = _app()
    async with _client(app) as c:
        r = await c.post("/api/v1/upload/t1", content=_chunks([300, 300]))
    assert r.status_code == 200 and r.json()["bytes"] == 600


async def test_other_paths_unaffected():
    app, _ = _app()
    async with _client(app) as c:
        r = await c.post("/other", content=b"x" * (CAP + 10))
    assert r.status_code == 200


async def test_multipart_parse_wrapping_still_yields_413():
    app, _ = _app()
    boundary = "bb"

    async def body():
        yield f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="a.pdf"\r\nContent-Type: application/pdf\r\n\r\n'.encode()
        for _ in range(3):
            yield b"x" * (CAP // 2)
        yield f"\r\n--{boundary}--\r\n".encode()

    async with _client(app) as c:
        r = await c.post(
            "/api/v1/upload/form-t1",
            content=body(),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
    assert r.status_code == 413
