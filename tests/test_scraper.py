import time

from winbindex_api.database import connect
from winbindex_api.scraper import _claim_scrape


def test_recent_success_prevents_scrape(tmp_path):
    database_path = tmp_path / "cache.db"
    with connect(database_path) as database:
        database.execute(
            "INSERT INTO metadata VALUES ('last_successful_scrape_epoch', ?)",
            (str(int(time.time())),),
        )
    assert _claim_scrape(database_path, 604800, False) is False
    assert _claim_scrape(database_path, 604800, True) is True
