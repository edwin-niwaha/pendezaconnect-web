import logging
import os

logger = logging.getLogger(__name__)


def log_process_memory(label: str) -> None:
    try:
        import psutil
    except ImportError:
        return

    process = psutil.Process(os.getpid())
    rss_mb = process.memory_info().rss / (1024 * 1024)
    logger.info("memory_usage label=%s rss_mb=%.2f", label, rss_mb)
