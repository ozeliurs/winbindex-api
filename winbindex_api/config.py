from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class Settings:
    database_path: Path
    source_url: str
    minimum_scrape_interval_seconds: int
    request_delay_seconds: float
    request_timeout_seconds: float
    max_concurrent_requests: int = 20
    request_max_retries: int = 3
    request_retry_backoff_seconds: float = 1.0

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_path=Path(os.getenv("DATABASE_PATH", "/data/winbindex.db")),
            source_url=os.getenv(
                "WINBINDEX_SOURCE_URL", "https://winbindex.m417z.com/data"
            ).rstrip("/"),
            minimum_scrape_interval_seconds=int(
                os.getenv("MINIMUM_SCRAPE_INTERVAL_SECONDS", "604800")
            ),
            request_delay_seconds=float(os.getenv("REQUEST_DELAY_SECONDS", "0.1")),
            request_timeout_seconds=float(os.getenv("REQUEST_TIMEOUT_SECONDS", "60")),
            max_concurrent_requests=int(os.getenv("MAX_CONCURRENT_REQUESTS", "20")),
            request_max_retries=int(os.getenv("REQUEST_MAX_RETRIES", "3")),
            request_retry_backoff_seconds=float(
                os.getenv("REQUEST_RETRY_BACKOFF_SECONDS", "1")
            ),
        )
