import json
import sqlite3
from pathlib import Path
from typing import Any


SCHEMA = """
CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS files (
    filename TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    md5 TEXT,
    sha1 TEXT,
    details TEXT NOT NULL,
    PRIMARY KEY (filename, sha256)
);
CREATE INDEX IF NOT EXISTS files_sha256_idx ON files(sha256);
CREATE INDEX IF NOT EXISTS files_sha1_idx ON files(sha1);
CREATE INDEX IF NOT EXISTS files_md5_idx ON files(md5);
"""


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=30, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA busy_timeout=30000")
    connection.executescript(SCHEMA)
    return connection


def find_by_hash(connection: sqlite3.Connection, digest: str) -> list[dict[str, Any]]:
    digest = digest.lower()
    column = {32: "md5", 40: "sha1", 64: "sha256"}.get(len(digest))
    if not column:
        return []
    rows = connection.execute(
        f"SELECT filename, details FROM files WHERE {column} = ? ORDER BY filename",  # noqa: S608
        (digest,),
    ).fetchall()
    return [{"filename": row["filename"], **json.loads(row["details"])} for row in rows]
