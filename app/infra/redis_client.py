import json
from typing import Any

import redis.asyncio as redis

from app.core.config import settings
from app.core.logging import get_logger
from app.core.metrics import REDIS_CACHE_LOOKUPS, REDIS_HEALTH_STATUS

logger = get_logger(__name__)


class RedisClientManager:
    """Async Redis connection pool and caching manager."""

    def __init__(self) -> None:
        self.pool: redis.ConnectionPool[Any] | None = None
        self.client: redis.Redis[Any] | None = None

    async def initialize(self) -> None:
        """Initializes async Redis connection pool."""
        try:
            self.pool = redis.ConnectionPool(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=settings.REDIS_DB,
                password=settings.REDIS_PASSWORD,
                max_connections=settings.REDIS_MAX_CONNECTIONS,
                decode_responses=True,
            )
            self.client = redis.Redis(connection_pool=self.pool)
            await self.ping()
            REDIS_HEALTH_STATUS.set(1)
            logger.info("Redis connection pool initialized successfully")
        except Exception as e:
            REDIS_HEALTH_STATUS.set(0)
            logger.warning("Redis initialization warning (will degrade gracefully)", error=str(e))

    async def close(self) -> None:
        """Closes Redis connections gracefully."""
        if self.client:
            await self.client.close()
        if self.pool:
            await self.pool.disconnect()
        REDIS_HEALTH_STATUS.set(0)
        logger.info("Redis connection pool closed")

    async def ping(self) -> bool:
        """Pings Redis server for readiness probe."""
        if not self.client:
            return False
        try:
            res = await self.client.ping()
            REDIS_HEALTH_STATUS.set(1 if res else 0)
            return bool(res)
        except Exception:
            REDIS_HEALTH_STATUS.set(0)
            return False

    async def get_cached_mx(self, domain: str) -> list[str] | None:
        """Retrieves cached MX records for domain from Redis."""
        if not self.client:
            REDIS_CACHE_LOOKUPS.labels(result="error").inc()
            return None
        try:
            val = await self.client.get(f"mx_cache:{domain}")
            if val is not None:
                REDIS_CACHE_LOOKUPS.labels(result="hit").inc()
                records: list[str] = json.loads(val)
                return records
            REDIS_CACHE_LOOKUPS.labels(result="miss").inc()
            return None
        except Exception as e:
            REDIS_CACHE_LOOKUPS.labels(result="error").inc()
            logger.warning("Redis get cached MX error", domain=domain, error=str(e))
            return None

    async def set_cached_mx(
        self, domain: str, mx_records: list[str], ttl: int = settings.REDIS_CACHE_TTL_MX_SECONDS
    ) -> None:
        """Stores MX records for domain in Redis cache."""
        if not self.client:
            return
        try:
            await self.client.setex(
                f"mx_cache:{domain}",
                ttl,
                json.dumps(mx_records),
            )
        except Exception as e:
            logger.warning("Redis set cached MX error", domain=domain, error=str(e))


redis_manager = RedisClientManager()
