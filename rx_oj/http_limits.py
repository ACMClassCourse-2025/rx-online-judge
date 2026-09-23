"""Bound JSON request bodies, including chunked requests, before parsing."""

from starlette.responses import JSONResponse


class RequestBoundary:
    def __init__(self, app, max_body_bytes):
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith("/api/"):
            return await self.app(scope, receive, send)
        headers = dict(scope["headers"])
        if scope["method"] not in ("POST", "PUT", "PATCH"):
            return await self.app(scope, receive, send)
        try:
            length = int(headers.get(b"content-length", b"0"))
        except ValueError:
            return await JSONResponse({"detail": "Invalid Content-Length"}, status_code=400)(
                scope, receive, send
            )
        if length > self.max_body_bytes:
            return await JSONResponse({"detail": "Request body is too large"}, status_code=413)(
                scope, receive, send
            )
        data = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            data.extend(message.get("body", b""))
            if len(data) > self.max_body_bytes:
                return await JSONResponse({"detail": "Request body is too large"}, status_code=413)(
                    scope, receive, send
                )
            if not message.get("more_body", False):
                break
        delivered = False

        async def bounded_receive():
            nonlocal delivered
            if delivered:
                return await receive()
            delivered = True
            return {"type": "http.request", "body": bytes(data), "more_body": False}

        await self.app(scope, bounded_receive, send)
