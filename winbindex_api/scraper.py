import argparse
import gzip
import json
import logging
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from itertools import islice
from pathlib import Path
from typing import Any, Iterable, Iterator
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from .config import Settings
from .database import connect

LOG = logging.getLogger(__name__)
USER_AGENT = "winbindex-api/0.1 (+https://github.com/ozeliurs/winbindex-api)"


def _get_json(
    url: str,
    timeout: float,
    compressed: bool = False,
    max_retries: int = 3,
    retry_backoff: float = 1.0,
) -> Any:
    for attempt in range(max_retries + 1):
        try:
            request = Request(
                url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "identity"}
            )
            with urlopen(request, timeout=timeout) as response:  # noqa: S310
                payload = response.read()
            if compressed:
                payload = gzip.decompress(payload)
            return json.loads(payload)
        except HTTPError as error:
            if error.code != 429 and error.code < 500:
                raise
            failure = error
        except (URLError, TimeoutError, gzip.BadGzipFile, json.JSONDecodeError) as error:
            failure = error

        if attempt == max_retries:
            raise failure
        delay = retry_backoff * (2**attempt)
        LOG.warning(
            "Request failed (attempt %d/%d); retrying in %.1fs: %s",
            attempt + 1,
            max_retries + 1,
            delay,
            url,
        )
        if delay:
            time.sleep(delay)


def _claim_scrape(database: Path, minimum_interval: int, force: bool) -> bool:
    now = int(time.time())
    with connect(database) as connection:
        connection.execute("BEGIN IMMEDIATE")
        last = connection.execute(
            "SELECT value FROM metadata WHERE key = 'last_successful_scrape_epoch'"
        ).fetchone()
        active = connection.execute(
            "SELECT value FROM metadata WHERE key = 'scrape_started_epoch'"
        ).fetchone()
        if not force and last and now - int(last[0]) < minimum_interval:
            LOG.info(
                "Skipping: the last successful scrape is newer than the minimum interval"
            )
            return False
        # Treat a claim as stale after six hours, so a killed job cannot block forever.
        if active and now - int(active[0]) < 21600:
            LOG.info("Skipping: another scraper has an active claim")
            return False
        connection.execute(
            "INSERT OR REPLACE INTO metadata(key, value) VALUES ('scrape_started_epoch', ?)",
            (str(now),),
        )
    return True


def _download_filename(
    filename: str, settings: Settings
) -> tuple[str, dict[str, Any]]:
    encoded = quote(filename, safe="")
    url = f"{settings.source_url}/by_filename_compressed/{encoded}.json.gz"
    records = _get_json(
        url,
        settings.request_timeout_seconds,
        compressed=True,
        max_retries=settings.request_max_retries,
        retry_backoff=settings.request_retry_backoff_seconds,
    )
    if settings.request_delay_seconds:
        time.sleep(settings.request_delay_seconds)
    return filename, records


def _download_filenames(
    filenames: Iterable[str], settings: Settings
) -> Iterator[tuple[str, dict[str, Any] | None]]:
    filenames = iter(filenames)
    with ThreadPoolExecutor(max_workers=settings.max_concurrent_requests) as executor:
        future_filenames = {
            executor.submit(_download_filename, filename, settings): filename
            for filename in islice(filenames, settings.max_concurrent_requests)
        }
        pending = set(future_filenames)
        while pending:
            done, pending = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                completed_filename = future_filenames.pop(future)
                try:
                    filename = next(filenames)
                except StopIteration:
                    pass
                else:
                    next_future = executor.submit(_download_filename, filename, settings)
                    future_filenames[next_future] = filename
                    pending.add(next_future)
                try:
                    yield future.result()
                except (
                    HTTPError,
                    URLError,
                    TimeoutError,
                    gzip.BadGzipFile,
                    json.JSONDecodeError,
                ):
                    LOG.exception(
                        "Skipping %s after request retries were exhausted",
                        completed_filename,
                    )
                    yield completed_filename, None


def scrape(settings: Settings, force: bool = False) -> bool:
    if not _claim_scrape(
        settings.database_path, settings.minimum_scrape_interval_seconds, force
    ):
        return False
    try:
        filenames = _get_json(
            f"{settings.source_url}/filenames.json",
            settings.request_timeout_seconds,
            max_retries=settings.request_max_retries,
            retry_backoff=settings.request_retry_backoff_seconds,
        )
        with connect(settings.database_path) as connection:
            connection.execute("DROP TABLE IF EXISTS files_next")
            connection.execute("CREATE TABLE files_next AS SELECT * FROM files WHERE 0")
            for number, (filename, records) in enumerate(
                _download_filenames(filenames, settings), start=1
            ):
                if records is None:
                    connection.execute(
                        "INSERT INTO files_next SELECT * FROM files WHERE filename = ?",
                        (filename,),
                    )
                    continue
                rows = []
                for sha256, details in records.items():
                    info = details.get("fileInfo", {})
                    rows.append(
                        (
                            filename,
                            sha256.lower(),
                            info.get("md5", "").lower() or None,
                            info.get("sha1", "").lower() or None,
                            json.dumps(details, separators=(",", ":")),
                        )
                    )
                connection.executemany(
                    "INSERT OR REPLACE INTO files_next(filename, sha256, md5, sha1, details) VALUES (?, ?, ?, ?, ?)",
                    rows,
                )
                if number % 100 == 0:
                    connection.commit()
                    LOG.info("Downloaded %d/%d filenames", number, len(filenames))
            connection.commit()
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DELETE FROM files")
            connection.execute("INSERT INTO files SELECT * FROM files_next")
            connection.execute("DROP TABLE files_next")
            now = datetime.now(timezone.utc)
            connection.executemany(
                "INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)",
                [
                    ("last_successful_scrape_epoch", str(int(now.timestamp()))),
                    ("last_successful_scrape", now.isoformat()),
                ],
            )
            connection.execute(
                "DELETE FROM metadata WHERE key = 'scrape_started_epoch'"
            )
        LOG.info("Scrape completed: %d filenames", len(filenames))
        return True
    except Exception:
        with connect(settings.database_path) as connection:
            connection.execute(
                "DELETE FROM metadata WHERE key = 'scrape_started_epoch'"
            )
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh the local Winbindex cache")
    parser.add_argument(
        "--force", action="store_true", help="ignore the weekly freshness check"
    )
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    scrape(Settings.from_env(), args.force)


if __name__ == "__main__":
    main()
