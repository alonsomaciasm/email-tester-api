import zstandard as zstd
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import FileResponse, Response, StreamingResponse


class ZstdCompressionMiddleware(BaseHTTPMiddleware):
    """Middleware for Zstandard (zstd) high-speed C-native response compression.

    Triggered when client sends 'Accept-Encoding: zstd'.
    """

    def __init__(self, app: BaseHTTPMiddleware, compression_level: int = 3, min_size: int = 256) -> None:
        super().__init__(app)
        self.compression_level = compression_level
        self.min_size = min_size

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        accept_encoding = request.headers.get("Accept-Encoding", "").lower()

        # Skip static dashboard HTML, FileResponse and StreamingResponse
        if request.url.path in ("/", "/dashboard"):
            return await call_next(request)

        response = await call_next(request)

        if "zstd" not in accept_encoding:
            return response

        # Don't re-compress if content-encoding is already set
        if "content-encoding" in response.headers:
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

            # Skip compression if body is smaller than min_size threshold
            if len(full_body) < self.min_size:
                return Response(
                    content=full_body,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    media_type=response.media_type,
                )

            cctx = zstd.ZstdCompressor(level=self.compression_level)
            compressed_body = cctx.compress(full_body)

            headers = dict(response.headers)
            headers["content-encoding"] = "zstd"
            headers["content-length"] = str(len(compressed_body))

            return Response(
                content=compressed_body,
                status_code=response.status_code,
                headers=headers,
                media_type=response.media_type,
            )
        except Exception:
            return response
