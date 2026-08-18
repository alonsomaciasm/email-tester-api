import hashlib
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import FileResponse, Response, StreamingResponse


class ETagCacheMiddleware(BaseHTTPMiddleware):
    """Middleware for deterministic ETag generation and HTTP 304 Not Modified caching.

    Complies with RFC 7232 & RFC 9110 HTTP caching standards.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Only process GET / POST read queries
        if request.method not in ("GET", "POST"):
            return await call_next(request)

        # Skip static dashboard HTML, FileResponse and StreamingResponse
        if request.url.path in ("/", "/dashboard"):
            return await call_next(request)

        if_none_match = request.headers.get("If-None-Match")

        response = await call_next(request)

        # Skip non-200 responses, existing ETags, or file responses
        if response.status_code != 200 or "etag" in response.headers:
            return response

        if isinstance(response, (FileResponse, StreamingResponse)):
            return response

        try:
            body = []
            async for chunk in response.body_iterator:
                if isinstance(chunk, bytes):
                    body.append(chunk)
                elif isinstance(chunk, str):
                    body.append(chunk.encode("utf-8"))

            if not body:
                return response

            full_body = b"".join(body)

            etag_val = f'W/"{hashlib.md5(full_body).hexdigest()[:16]}"'

            headers = dict(response.headers)
            headers["etag"] = etag_val

            # Handle 304 Not Modified if client sent matching If-None-Match header
            if if_none_match and if_none_match.strip() == etag_val:
                return Response(
                    status_code=304,
                    headers=headers,
                )

            return Response(
                content=full_body,
                status_code=response.status_code,
                headers=headers,
                media_type=response.media_type,
            )
        except Exception:
            return response
