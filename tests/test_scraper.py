import time
from io import BytesIO
from threading import Lock
from urllib.error import HTTPError

from winbindex_api.database import connect
from winbindex_api.config import Settings
from winbindex_api.scraper import _claim_scrape, _get_json, scrape


def test_recent_success_prevents_scrape(tmp_path):
    database_path = tmp_path / "cache.db"
    with connect(database_path) as database:
        database.execute(
            "INSERT INTO metadata VALUES ('last_successful_scrape_epoch', ?)",
            (str(int(time.time())),),
        )
    assert _claim_scrape(database_path, 604800, False) is False
    assert _claim_scrape(database_path, 604800, True) is True


def test_scrape_downloads_filenames_concurrently(tmp_path, monkeypatch):
    filenames = [f"file-{number}.dll" for number in range(12)]
    lock = Lock()
    active_requests = 0
    peak_requests = 0

    def fake_get_json(url, timeout, compressed=False, **kwargs):
        nonlocal active_requests, peak_requests
        if url.endswith("/filenames.json"):
            return filenames
        assert compressed is True
        with lock:
            active_requests += 1
            peak_requests = max(peak_requests, active_requests)
        time.sleep(0.02)
        with lock:
            active_requests -= 1
        number = int(url.rsplit("file-", 1)[1].split(".dll", 1)[0])
        sha256 = f"{number:064x}"
        return {sha256: {"fileInfo": {"sha256": sha256}}}

    monkeypatch.setattr("winbindex_api.scraper._get_json", fake_get_json)
    settings = Settings(
        tmp_path / "cache.db",
        "https://example.test/data",
        604800,
        0,
        1,
        max_concurrent_requests=4,
    )

    assert scrape(settings) is True
    assert peak_requests == 4
    with connect(settings.database_path) as database:
        count = database.execute("SELECT count(*) FROM files").fetchone()[0]
    assert count == len(filenames)


def test_get_json_retries_temporary_server_error(monkeypatch):
    responses = [
        HTTPError("https://example.test/data", 503, "Unavailable", {}, None),
        BytesIO(b'{"ok": true}'),
    ]

    def fake_urlopen(request, timeout):
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr("winbindex_api.scraper.urlopen", fake_urlopen)

    assert _get_json(
        "https://example.test/data", 1, max_retries=1, retry_backoff=0
    ) == {"ok": True}
    assert responses == []


def test_scrape_keeps_cached_records_when_one_download_fails(tmp_path, monkeypatch):
    database_path = tmp_path / "cache.db"
    cached_sha256 = "a" * 64
    with connect(database_path) as database:
        database.execute(
            "INSERT INTO files(filename, sha256, details) VALUES (?, ?, ?)",
            ("unavailable.dll", cached_sha256, "{}"),
        )

    def fake_get_json(url, timeout, compressed=False, **kwargs):
        if url.endswith("/filenames.json"):
            return ["available.dll", "unavailable.dll"]
        if "unavailable.dll" in url:
            raise HTTPError(url, 503, "Unavailable", {}, None)
        sha256 = "b" * 64
        return {sha256: {"fileInfo": {"sha256": sha256}}}

    monkeypatch.setattr("winbindex_api.scraper._get_json", fake_get_json)
    settings = Settings(
        database_path,
        "https://example.test/data",
        604800,
        0,
        1,
        max_concurrent_requests=2,
        request_max_retries=0,
        request_retry_backoff_seconds=0,
    )

    assert scrape(settings) is True
    with connect(database_path) as database:
        rows = database.execute(
            "SELECT filename, sha256 FROM files ORDER BY filename"
        ).fetchall()
    assert [tuple(row) for row in rows] == [
        ("available.dll", "b" * 64),
        ("unavailable.dll", cached_sha256),
    ]
