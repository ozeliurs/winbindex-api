# Winbindex API

A read-only FastAPI service backed by a local SQLite cache of the public
[Winbindex](https://winbindex.m417z.com/) metadata. It returns Winbindex's complete
file details for MD5, SHA-1, or SHA-256 hashes, including every matching filename.

## API

```text
GET /v1/files/{md5-or-sha1-or-sha256}
GET /healthz
GET /docs
```

Example response:

```json
{
  "hash": "01b407af0200b66a34d9b1fa6d9eaab758efa36a36bb99b554384f59f8690b1a",
  "matches": [
    {
      "filename": ".accdb_large.png",
      "fileInfo": {"sha256": "01b407af...", "signingStatus": "Unsigned"},
      "windowsVersions": {"1809": {"BASE": {}}}
    }
  ]
}
```

The endpoint returns `422` for a malformed digest and `404` when no cached record
matches. Hash lookup is case-insensitive. `/healthz` also reports the cache record
count and last successful refresh.

## Local development

Python 3.11 or newer is required.

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'
export DATABASE_PATH="$PWD/winbindex.db"
winbindex-scrape
uvicorn winbindex_api.main:app --reload
```

The scraper downloads the filename index and then fetches up to 20 compressed
per-filename documents concurrently by default. The concurrency and a small delay
per worker are configurable to avoid aggressively requesting the upstream service.
Transient upstream failures are retried with exponential backoff. If a filename
still cannot be downloaded, the refresh continues and retains that filename's
records from the previous snapshot rather than emptying the cache or failing the
whole job.

The database records the successful refresh time and refuses another refresh for
seven days, even if the command is invoked more frequently. It also uses a six-hour
scrape claim to prevent overlapping runs. `winbindex-scrape --force` bypasses only
the seven-day freshness check and should be used sparingly.

| Environment variable | Default | Description |
| --- | --- | --- |
| `DATABASE_PATH` | `/data/winbindex.db` | SQLite database file |
| `WINBINDEX_SOURCE_URL` | `https://winbindex.m417z.com/data` | Upstream data root |
| `MINIMUM_SCRAPE_INTERVAL_SECONDS` | `604800` | Minimum successful-refresh interval |
| `MAX_CONCURRENT_REQUESTS` | `20` | Maximum simultaneous filename requests |
| `REQUEST_DELAY_SECONDS` | `0.1` | Courtesy delay between filename requests |
| `REQUEST_TIMEOUT_SECONDS` | `60` | Timeout for each upstream request |
| `REQUEST_MAX_RETRIES` | `3` | Retries after a transient request failure |
| `REQUEST_RETRY_BACKOFF_SECONDS` | `1` | Initial retry delay (doubled after each failure) |

## Container image

Every push to `main` and version tag builds and publishes images to
`ghcr.io/ozeliurs/winbindex-api`; pull requests build without publishing. Locally:

```bash
docker build -t winbindex-api .
docker run --rm -p 8000:8000 -v winbindex-data:/data winbindex-api
```

Run a refresh against the same volume with:

```bash
docker run --rm -v winbindex-data:/data winbindex-api winbindex-scrape
```

## Kubernetes / Helm

The chart creates a Deployment, Service, Ingress, persistent volume claim, and a
weekly CronJob. The API and scraper share the claim. The CronJob uses
`concurrencyPolicy: Forbid`, while the application-level timestamp and claim remain
the source of truth for scrape throttling.

```bash
helm upgrade --install winbindex ./chart \
  --set ingress.hosts[0].host=winbindex.example.org \
  --set image.tag=sha-0123456
```

Set `ingress.className`, `ingress.annotations`, and `ingress.tls` for the target
cluster. For storage provisioners that do not allow simultaneous mounting of a
`ReadWriteOnce` volume from different nodes, use an `ReadWriteMany` storage class,
or scheduling affinity appropriate for the cluster. An existing PVC can be selected
with `persistence.existingClaim`.

The initial CronJob run populates the empty database. Until it finishes, the API is
healthy but hash queries return `404` and `/healthz` reports zero records.

## Data provenance

This project caches metadata supplied by Winbindex and does not host Windows
binaries. A database match means the hash appears in that dataset; callers must
make their own security and trust decisions.
