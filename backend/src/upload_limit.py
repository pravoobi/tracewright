"""Request-body size limit for the upload endpoint.

The handler's own byte count only runs after the framework has spooled the
whole multipart body to disk, and a chunked request carries no Content-Length
to check up front. This pure-ASGI middleware therefore does both: it refuses
on a declared Content-Length before reading anything, and otherwise counts the
bytes actually received and aborts the moment the cap is crossed.
"""
from __future__ import annotations

import json

# Multipart framing adds a little overhead over the file itself.
OVERHEAD_BYTES = 1_048_576


class _BodyTooLarge(Exception):
    pass


class UploadSizeLimitMiddleware:
    def __init__(self, app, *, max_bytes_getter, path_prefix: str = "/api/v1/upload/"):
        self.app = app
        self._max_bytes = max_bytes_getter  # callable, so config changes apply
        self.path_prefix = path_prefix

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] != "http"
            or scope["method"] != "POST"
            or not scope["path"].startswith(self.path_prefix)
        ):
            return await self.app(scope, receive, send)

        limit = self._max_bytes() + OVERHEAD_BYTES
        declared = dict(scope["headers"]).get(b"content-length", b"")
        if declared.isdigit() and int(declared) > limit:
            return await self._reject(send)

        received = 0
        tripped = False
        started = False

        async def counting_receive():
            nonlocal received, tripped
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    tripped = True
                    raise _BodyTooLarge
            return message

        async def tracking_send(message):
            nonlocal started
            if tripped:
                return  # the framework may turn our abort into a 400; drop it
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, counting_receive, tracking_send)
        except _BodyTooLarge:
            pass
        if tripped and not started:
            await self._reject(send)

    @staticmethod
    async def _reject(send):
        body = json.dumps({"detail": "Upload exceeds maximum size"}).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    (b"connection", b"close"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
