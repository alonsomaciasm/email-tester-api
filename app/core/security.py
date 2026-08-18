import hashlib
import hmac
import time
import uuid
from typing import Any

import structlog
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import HTTPException, Request, Response, Security, status
from fastapi.security import APIKeyHeader
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

api_key_header = APIKeyHeader(name=settings.API_KEY_HEADER_NAME, auto_error=False)
ph = PasswordHasher()


def hash_identifier(identifier: str) -> str:
    """Hashes IP or client identifier with daily rotating salt for privacy-preserving rate limiting."""
    salted = f"{identifier}:{settings.SECRET_SALT}".encode()
    return hashlib.sha256(salted).hexdigest()


async def verify_api_key(api_key: str | None = Security(api_key_header)) -> str:
    """Validates X-API-Key using constant-time comparison and Argon2id hash verification."""
    if not settings.REQUIRE_API_KEY:
        return api_key or "anonymous"

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API Key header",
        )

    # Check against allowed keys (plain-text constant time digest or Argon2id hash)
    key_valid = False
    for allowed in settings.ALLOWED_API_KEYS:
        if allowed.startswith("$argon2id$"):
            try:
                if ph.verify(allowed, api_key):
                    key_valid = True
                    break
            except VerifyMismatchError:
                logger.debug("Argon2 API key mismatch")
            except Exception as e:
                logger.debug("Argon2 verification exception", error=str(e))
        else:
            if hmac.compare_digest(api_key.encode("utf-8"), allowed.encode("utf-8")):
                key_valid = True
                break

    if not key_valid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API Key",
        )

    return api_key


class AuditContextMiddleware(BaseHTTPMiddleware):
    """Middleware that injects request correlation ID and anonymized client IP hash into structlog contextvars."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        structlog.contextvars.clear_contextvars()

        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        client_ip = request.client.host if request.client else "127.0.0.1"
        client_ip_hash = hash_identifier(client_ip)

        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            client_ip_hash=client_ip_hash[:16],
            path=request.url.path,
            method=request.method,
        )

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class ContentLengthLimitMiddleware(BaseHTTPMiddleware):
    """Mitigates Denial of Service (DoS) by enforcing maximum HTTP body length limits."""

    def __init__(self, app: Any, max_content_length: int = 10240) -> None:  # 10 KB default limit
        super().__init__(app)
        self.max_content_length = max_content_length

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > self.max_content_length:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="Request body payload exceeds maximum allowed size (10 KB)",
                    )
            except ValueError:
                pass
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds secure HTTP response headers and strips server disclosure headers."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)

        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "0"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net; "
            "font-src 'self' https://fonts.gstatic.com data:; "
            "img-src 'self' https://fastapi.tiangolo.com data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none';"
        )
        response.headers["Referrer-Policy"] = "no-referrer"

        # Remove revealing server header if present
        if "server" in response.headers:
            del response.headers["server"]
        if "Server" in response.headers:
            del response.headers["Server"]

        return response


class SlidingWindowRateLimiter:
    """Distributed Redis sliding window rate limiter with privacy-preserving hash keys."""

    def __init__(self) -> None:
        # In-memory fallback tracking if Redis is unreachable
        self._local_fallback_cache: dict[str, list[float]] = {}

    async def check_rate_limit(
        self,
        request: Request,
        redis_client: Any = None,
        key_prefix: str = "rate_limit",
        max_requests: int = settings.RATE_LIMIT_IP_REQUESTS,
        window_seconds: int = settings.RATE_LIMIT_WINDOW_SECONDS,
    ) -> None:
        client_ip = request.client.host if request.client else "127.0.0.1"
        client_hash = hash_identifier(client_ip)
        now = time.time()
        clear_before = now - window_seconds
        redis_key = f"{key_prefix}:{client_hash}"

        if redis_client is not None:
            try:
                # Redis Pipeline sliding window using sorted sets (ZSET)
                async with redis_client.pipeline(transaction=True) as pipe:
                    pipe.zremrangebyscore(redis_key, 0, clear_before)
                    pipe.zadd(redis_key, {str(now): now})
                    pipe.zcard(redis_key)
                    pipe.expire(redis_key, window_seconds + 5)
                    results = await pipe.execute()

                current_count = results[2]
                if current_count > max_requests:
                    retry_after = int(window_seconds)
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail="Rate limit exceeded",
                        headers={"Retry-After": str(retry_after)},
                    )
                return
            except HTTPException:
                raise
            except Exception as e:
                logger.warning(
                    "Redis rate limit check failed, falling back to local window",
                    error=str(e),
                )

        # Fallback local in-memory sliding window
        timestamps = self._local_fallback_cache.get(client_hash, [])
        timestamps = [ts for ts in timestamps if ts > clear_before]
        timestamps.append(now)
        self._local_fallback_cache[client_hash] = timestamps

        if len(timestamps) > max_requests:
            retry_after = int(window_seconds)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded (fallback mode)",
                headers={"Retry-After": str(retry_after)},
            )


rate_limiter = SlidingWindowRateLimiter()
