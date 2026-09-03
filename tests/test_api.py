import json

from fastapi.testclient import TestClient

from winbindex_api.config import Settings
from winbindex_api.database import connect
from winbindex_api.main import create_app


def settings(tmp_path):
    return Settings(tmp_path / "test.db", "https://example.test", 604800, 0, 1)


def test_query_by_each_supported_hash(tmp_path):
    config = settings(tmp_path)
    details = {
        "fileInfo": {
            "md5": "a" * 32,
            "sha1": "b" * 40,
            "sha256": "c" * 64,
            "description": "A legitimate file",
        },
        "windowsVersions": {"11-24H2": {}},
    }
    with connect(config.database_path) as database:
        database.execute(
            "INSERT INTO files VALUES (?, ?, ?, ?, ?)",
            ("example.exe", "c" * 64, "a" * 32, "b" * 40, json.dumps(details)),
        )

    with TestClient(create_app(config)) as client:
        for digest in ("A" * 32, "b" * 40, "c" * 64):
            response = client.get(f"/v1/files/{digest}")
            assert response.status_code == 200
            assert response.json()["matches"] == [
                {"filename": "example.exe", **details}
            ]


def test_invalid_and_unknown_hashes(tmp_path):
    with TestClient(create_app(settings(tmp_path))) as client:
        assert client.get("/v1/files/not-a-hash").status_code == 422
        assert client.get(f"/v1/files/{'d' * 64}").status_code == 404


def test_health_reports_cache_state(tmp_path):
    with TestClient(create_app(settings(tmp_path))) as client:
        assert client.get("/healthz").json() == {
            "status": "ok",
            "records": 0,
            "lastSuccessfulScrape": None,
        }
