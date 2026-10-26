from fastapi.responses import JSONResponse

from app.auth import origin_allowed
from app.config import get_settings


class RequestProtection:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        is_api = scope["path"].startswith("/api")
        if is_api and scope["method"] not in {"GET", "HEAD", "OPTIONS"}:
            headers = dict(scope.get("headers", []))
            if not origin_allowed(headers.get(b"origin", b"").decode("latin-1")):
                return await JSONResponse({"detail": "Invalid request origin."}, 403)(scope, receive, send)
            limit = get_settings().max_body_bytes
            declared = headers.get(b"content-length")
            if declared and declared.isdigit() and int(declared) > limit:
                return await JSONResponse({"detail": "Request is too large."}, 413)(scope, receive, send)
            body = bytearray()
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                body.extend(message.get("body", b""))
                if len(body) > limit:
                    return await JSONResponse({"detail": "Request is too large."}, 413)(scope, receive, send)
                if not message.get("more_body"):
                    break
            done = False

            async def replay():
                nonlocal done
                if not done:
                    done = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return await receive()

            inner_receive = replay
        else:
            inner_receive = receive

        async def guarded_send(message):
            if message["type"] == "http.response.start":
                extra = [(b"x-content-type-options", b"nosniff"), (b"referrer-policy", b"no-referrer"),
                         (b"x-frame-options", b"DENY")]
                if is_api:
                    extra.append((b"cache-control", b"no-store"))
                message["headers"] = list(message.get("headers", [])) + extra
            await send(message)

        await self.app(scope, inner_receive, guarded_send)
