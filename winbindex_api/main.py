import re
import sqlite3
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request

from .config import Settings
from .database import connect, find_by_hash

HASH_PATTERN = re.compile(r"^(?:[0-9a-fA-F]{32}|[0-9a-fA-F]{40}|[0-9a-fA-F]{64})$")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.database = connect(settings.database_path)
        yield
        app.state.database.close()

    app = FastAPI(title="Winbindex API", version="0.1.0", lifespan=lifespan)

    @app.get("/healthz", tags=["service"])
    def health(request: Request) -> dict[str, str | int | None]:
        connection: sqlite3.Connection = request.app.state.database
        count = connection.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        row = connection.execute(
            "SELECT value FROM metadata WHERE key = 'last_successful_scrape'"
        ).fetchone()
        return {
            "status": "ok",
            "records": count,
            "lastSuccessfulScrape": row[0] if row else None,
        }

    @app.get("/v1/files/{digest}", tags=["files"])
    def file_by_hash(digest: str, request: Request) -> dict[str, object]:
        if not HASH_PATTERN.fullmatch(digest):
            raise HTTPException(
                422, "Hash must be a hexadecimal MD5, SHA-1, or SHA-256 digest"
            )
        matches = find_by_hash(request.app.state.database, digest)
        if not matches:
            raise HTTPException(404, "Hash not found")
        return {"hash": digest.lower(), "matches": matches}

    return app


app = create_app()
