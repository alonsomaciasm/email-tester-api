from multiprocessing.shared_memory import SharedMemory

from app.core.logging import get_logger

logger = get_logger(__name__)


class SharedBloomMemoryManager:
    """Inter-Process Communication (IPC) Shared Memory Manager for Bloom Filter Bitsets.

    Enables multiple Gunicorn / Granian worker processes to share a single, read-optimized
    shared memory segment in RAM, eliminating memory duplication across workers.
    """

    def __init__(self, segment_name: str = "email_verifier_bloom_shm") -> None:
        self.segment_name = segment_name
        self.shm: SharedMemory | None = None
        self.is_owner = False

    def get_or_create_buffer(self, size_bytes: int) -> memoryview | bytearray:
        """Attaches to existing IPC shared memory segment or creates a new one of size_bytes."""
        try:
            # Try attaching to existing segment created by master process
            self.shm = SharedMemory(name=self.segment_name, create=False)
            self.is_owner = False
            logger.info("Attached to existing IPC Shared Memory segment for Bloom Filter", segment=self.segment_name)
            return self.shm.buf
        except FileNotFoundError:
            try:
                # Create new shared memory segment
                self.shm = SharedMemory(name=self.segment_name, create=True, size=size_bytes)
                self.is_owner = True
                logger.info(
                    "Created new IPC Shared Memory segment for Bloom Filter",
                    segment=self.segment_name,
                    size_bytes=size_bytes,
                )
                return self.shm.buf
            except Exception as e:
                logger.warning(
                    "IPC SharedMemory creation fallback to in-process memory",
                    error=str(e),
                )
                return bytearray(size_bytes)
        except Exception as e:
            logger.warning(
                "IPC SharedMemory attach fallback to in-process memory",
                error=str(e),
            )
            return bytearray(size_bytes)

    def close(self) -> None:
        """Closes handle and unlinks segment if owner."""
        if self.shm is not None:
            try:
                self.shm.close()
                if self.is_owner:
                    self.shm.unlink()
                logger.info("Closed IPC Shared Memory segment", segment=self.segment_name)
            except Exception as e:
                logger.warning("Error closing IPC Shared Memory segment", error=str(e))
            finally:
                self.shm = None


shared_bloom_manager = SharedBloomMemoryManager()
