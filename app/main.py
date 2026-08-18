from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
import time
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, ORJSONResponse
from prometheus_client import make_asgi_app

from app.api.v1.routes_verify import router as verify_router
from app.core.config import settings
from app.core.exceptions import AppBaseException
from app.core.logging import configure_logging, get_logger
from app.core.security import AuditContextMiddleware, ContentLengthLimitMiddleware, SecurityHeadersMiddleware
from app.domain.bloom_filter import bloom_filter_service
from app.domain.mx_resolver import dns_circuit_breaker
from app.infra.dataset_sync_job import dataset_sync_job
from app.infra.l1_cache import l1_cache
from app.infra.redis_client import redis_manager

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan event handler for startup and graceful shutdown."""
    # 1. Startup Logging & Seed Dataset loading
    configure_logging(settings.LOG_LEVEL)
    logger.info(
        "Initializing application service",
        service=settings.SERVICE_NAME,
        environment=settings.ENVIRONMENT,
        json_serializer=settings.JSON_SERIALIZER_ENGINE,
        typo_engine=settings.TYPO_ENGINE_BACKEND,
        redis_parser=settings.REDIS_PARSER,
    )

    dataset_sync_job.initialize_seed()

    # 2. Redis Connection Pool setup
    await redis_manager.initialize()

    # 3. Start periodic dataset sync
    dataset_sync_job.start_periodic_sync()

    yield

    # Shutdown sequence
    logger.info("Initiating graceful shutdown sequence")
    dataset_sync_job.stop_periodic_sync()
    await redis_manager.close()
    logger.info("Shutdown sequence complete")


# Select default response class based on JSON_SERIALIZER_ENGINE
response_class = ORJSONResponse if settings.JSON_SERIALIZER_ENGINE == "orjson" else JSONResponse

app = FastAPI(
    title="Disposable Email Verification API",
    description="Secure-by-Design and Privacy-by-Design high-performance API for detecting disposable email providers.",
    version="1.2.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    default_response_class=response_class,
    swagger_ui_parameters={"syntaxHighlight.theme": "obsidian", "tryItOutEnabled": True},
    lifespan=lifespan,
)

from app.core.etag_middleware import ETagCacheMiddleware
from app.core.zstd_middleware import ZstdCompressionMiddleware

# Security, Compression & Audit Middlewares
app.add_middleware(ETagCacheMiddleware)
app.add_middleware(ZstdCompressionMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(AuditContextMiddleware)
app.add_middleware(ContentLengthLimitMiddleware, max_content_length=10240)
app.add_middleware(SecurityHeadersMiddleware)

# Register API routers
app.include_router(verify_router)

# Mount Prometheus Metrics endpoint
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)


# Mount Static Dashboard UI
@app.get("/", response_class=FileResponse, tags=["Dashboard UI"], summary="Cyber Dashboard UI")
@app.get("/dashboard", response_class=FileResponse, tags=["Dashboard UI"], summary="Cyber Dashboard UI")
async def serve_dashboard() -> FileResponse:
    """Serves the Cyber Glassmorphism Enterprise Dashboard UI."""
    return FileResponse("app/static/index.html")


@app.get(
    "/healthz",
    status_code=status.HTTP_200_OK,
    tags=["System Probes"],
    summary="Liveness Probe",
)
async def healthz() -> dict[str, str]:
    """Liveness probe indicating process is responsive."""
    return {"status": "ok"}


@app.get(
    "/readyz",
    status_code=status.HTTP_200_OK,
    tags=["System Probes"],
    summary="Readiness Probe",
)
async def readyz() -> JSONResponse:
    """Readiness probe verifying Redis connection and Bloom filter state."""
    redis_ok = await redis_manager.ping()
    bloom_info = bloom_filter_service.get_info()
    bloom_ok = bloom_info["items_count"] > 0

    is_ready = redis_ok and bloom_ok
    status_code = status.HTTP_200_OK if is_ready else status.HTTP_503_SERVICE_UNAVAILABLE

    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ready" if is_ready else "not_ready",
            "redis_connected": redis_ok,
            "bloom_filter_loaded": bloom_ok,
        },
    )


@app.get(
    "/healthz/detailed",
    status_code=status.HTTP_200_OK,
    tags=["System Probes"],
    summary="Detailed Diagnostic & Telemetry Health Probe",
)
async def healthz_detailed() -> JSONResponse:
    """Returns comprehensive telemetry including Redis latency, L1 cache hit-ratio, Bloom Filter, engine backends and DNS Circuit Breaker status."""
    t0 = time.perf_counter()
    redis_ok = await redis_manager.ping()
    redis_latency_ms = round((time.perf_counter() - t0) * 1000, 3)

    bloom_info = bloom_filter_service.get_info()
    l1_stats = l1_cache.get_stats()
    sync_status = dataset_sync_job.get_sync_status()

    is_healthy = redis_ok and bloom_info["items_count"] > 0

    return JSONResponse(
        status_code=status.HTTP_200_OK if is_healthy else status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "status": "healthy" if is_healthy else "degraded",
            "engine_backends": {
                "json_serializer": settings.JSON_SERIALIZER_ENGINE,
                "typo_engine": settings.TYPO_ENGINE_BACKEND,
                "redis_parser": settings.REDIS_PARSER,
            },
            "redis": {
                "connected": redis_ok,
                "latency_ms": redis_latency_ms,
            },
            "l1_memory_cache": l1_stats,
            "bloom_filter": bloom_info,
            "dataset_sync": sync_status,
            "dns_circuit_breaker": {
                "state": getattr(dns_circuit_breaker.current_state, "name", "CLOSED"),
            },
        },
    )


@app.get(
    "/internal/dataset-info",
    status_code=status.HTTP_200_OK,
    tags=["Internal & Research"],
    summary="Dataset version & reproducibility metadata",
)
async def dataset_info() -> dict[str, Any]:
    """Exposes active dataset version, Bloom filter capacity, item count, hash, and source URLs status."""
    info = bloom_filter_service.get_info()
    info.update(dataset_sync_job.get_sync_status())
    return info


# Global Exception Handlers
@app.exception_handler(AppBaseException)
async def app_base_exception_handler(request: Request, exc: AppBaseException) -> JSONResponse:
    """Handles domain-specific exceptions with structured RFC 7807 error format."""
    logger.warning("Domain exception caught", code=exc.code, status_code=exc.status_code)
    headers = {}
    if "retry_after" in exc.details:
        headers["Retry-After"] = str(exc.details["retry_after"])

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.message,
            "code": exc.code,
        },
        headers=headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Sanitizes validation errors to ensure input emails are not echoed back in error responses."""
    logger.warning("Request input validation failure")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": "Invalid input format. Please check the email parameter.",
            "code": "INVALID_EMAIL_FORMAT",
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=exc.headers,
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled internal server error", error=str(exc))
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal server error occurred."},
    )
