import asyncio
from datetime import UTC, datetime
from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.domain.bloom_filter import bloom_filter_service

logger = get_logger(__name__)

# Default seed disposable domains list for immediate startup ready state
SEED_DISPOSABLE_DOMAINS: set[str] = {
    "mailinator.com",
    "guerrillamail.com",
    "temp-mail.org",
    "10minutemail.com",
    "yopmail.com",
    "dispostable.com",
    "maildrop.cc",
    "sharklasers.com",
    "getnada.com",
    "trashmail.com",
    "fakeinbox.com",
    "mohmal.com",
    "inboxkitten.com",
    "crazymailing.com",
    "throwawaymail.com",
    "mailnesia.com",
    "tempmail.com",
    "getairmail.com",
    "mytemp.email",
}


class DatasetSyncJob:
    """Background synchronization job for pulling disposable domain datasets."""

    def __init__(self) -> None:
        self._running: bool = False
        self._task: asyncio.Task[None] | None = None
        self.sources_status: list[dict[str, Any]] = []
        self.last_sync_timestamp: str | None = None

    def initialize_seed(self) -> None:
        """Populates initial seed domains on startup or restores binary snapshot with sources telemetry if available."""
        snapshot_state = bloom_filter_service.load_snapshot()
        if snapshot_state and snapshot_state.get("sources_status"):
            self.sources_status = snapshot_state["sources_status"]
            self.last_sync_timestamp = snapshot_state.get("last_sync_timestamp") or datetime.now(UTC).isoformat()
        else:
            if not snapshot_state:
                bloom_filter_service.load_domains(SEED_DISPOSABLE_DOMAINS, version="v1.0.0-seed")
            now_iso = datetime.now(UTC).isoformat()
            self.sources_status = [
                {
                    "url": "Internal Seed Dataset",
                    "status": "success",
                    "domains_count": len(SEED_DISPOSABLE_DOMAINS),
                    "error": None,
                    "last_updated": now_iso,
                }
            ]
            for url in settings.DATASET_SOURCE_URLS:
                self.sources_status.append({
                    "url": url,
                    "status": "pending",
                    "domains_count": 0,
                    "error": None,
                    "last_updated": now_iso,
                })
            self.last_sync_timestamp = now_iso

    async def fetch_remote_dataset(self) -> set[str]:
        """Fetches and aggregates disposable email domain blocklists from multiple public open-source sources."""
        aggregated_domains: set[str] = set()
        updated_statuses: list[dict[str, Any]] = [
            {
                "url": "Internal Seed Dataset",
                "status": "success",
                "domains_count": len(SEED_DISPOSABLE_DOMAINS),
                "error": None,
                "last_updated": datetime.now(UTC).isoformat(),
            }
        ]

        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            for url in settings.DATASET_SOURCE_URLS:
                try:
                    response = await client.get(url)
                    response.raise_for_status()
                    content_type = response.headers.get("content-type", "")

                    if "application/json" in content_type or url.endswith(".json"):
                        data = response.json()
                        if isinstance(data, list):
                            domains = {str(item).strip().lower() for item in data if item}
                            aggregated_domains.update(domains)
                    else:
                        lines = response.text.splitlines()
                        domains = {
                            line.strip().lower()
                            for line in lines
                            if line.strip() and not line.startswith("#") and not line.startswith("//")
                        }
                        aggregated_domains.update(domains)

                    updated_statuses.append(
                        {
                            "url": url,
                            "status": "success",
                            "domains_count": len(domains),
                            "error": None,
                            "last_updated": datetime.now(UTC).isoformat(),
                        }
                    )
                    logger.info("Remote dataset source fetched successfully", url=url, count=len(domains))
                except Exception as e:
                    updated_statuses.append(
                        {
                            "url": url,
                            "status": "failed",
                            "domains_count": 0,
                            "error": str(e),
                            "last_updated": datetime.now(UTC).isoformat(),
                        }
                    )
                    logger.warning("Failed to fetch dataset source", url=url, error=str(e))

        self.sources_status = updated_statuses
        self.last_sync_timestamp = datetime.now(UTC).isoformat()
        return aggregated_domains

    def get_sync_status(self) -> dict[str, Any]:
        """Returns structured metadata of sources sync status for telemetry dashboard."""
        if len(self.sources_status) <= 1:
            snapshot = bloom_filter_service.load_snapshot()
            if snapshot and snapshot.get("sources_status"):
                self.sources_status = snapshot["sources_status"]
                if snapshot.get("last_sync_timestamp"):
                    self.last_sync_timestamp = snapshot["last_sync_timestamp"]

        return {
            "last_sync_timestamp": self.last_sync_timestamp,
            "sources_status": self.sources_status,
        }

    async def sync_once(self) -> None:
        """Executes a sync cycle and persists snapshot to disk. Uses a lock so 1 worker syncs."""
        from app.infra.redis_client import redis_manager

        lock_acquired = False
        if redis_manager.client:
            try:
                # Set a 300s lock in Redis
                lock_acquired = bool(await redis_manager.client.set("lock:dataset_sync", "1", nx=True, ex=300))
            except Exception:
                lock_acquired = True
        else:
            lock_acquired = True

        if lock_acquired:
            try:
                remote_domains = await self.fetch_remote_dataset()
                if remote_domains:
                    combined = SEED_DISPOSABLE_DOMAINS.union(remote_domains)
                    bloom_filter_service.load_domains(combined, version="v1.1.0-synced")
                    bloom_filter_service.save_snapshot(
                        sources_status=self.sources_status,
                        last_sync_timestamp=self.last_sync_timestamp,
                    )
            finally:
                if redis_manager.client:
                    try:
                        await redis_manager.client.delete("lock:dataset_sync")
                    except Exception:
                        pass  # nosec B110
        else:
            # Another worker is performing the sync; reload updated snapshot if available
            await asyncio.sleep(2)
            snapshot_state = bloom_filter_service.load_snapshot()
            if snapshot_state and snapshot_state.get("sources_status"):
                self.sources_status = snapshot_state["sources_status"]
                if snapshot_state.get("last_sync_timestamp"):
                    self.last_sync_timestamp = snapshot_state["last_sync_timestamp"]

    async def _periodic_loop(self) -> None:
        while self._running:
            try:
                await self.sync_once()
            except Exception as e:
                logger.error("Dataset sync loop error", error=str(e))
            # Sync every 24 hours (86400 seconds)
            await asyncio.sleep(86400)

    def start_periodic_sync(self) -> None:
        """Starts background periodic sync task."""
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(self._periodic_loop())
            logger.info("Dataset periodic sync task started")

    def stop_periodic_sync(self) -> None:
        """Stops background periodic sync task."""
        self._running = False
        if self._task:
            self._task.cancel()
            logger.info("Dataset periodic sync task stopped")


dataset_sync_job = DatasetSyncJob()
