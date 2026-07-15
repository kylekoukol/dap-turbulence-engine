"""
Write path for the engine. Lovable Cloud does not expose a service-role key, so
instead of writing to Supabase directly we POST artifacts to a small secured
ingest endpoint in the app (a server route that holds the admin credentials and
writes to Storage + tables on our behalf).

Everything is gzipped on the wire (EDR grids compress heavily). The endpoint URL
and shared secret come from the environment:
  INGEST_URL     e.g. https://<app>/api/ingest   (not secret; can live in code)
  INGEST_SECRET  shared secret (GitHub Actions Secret <-> app secret)
"""
import os
import gzip
import json
import logging
import requests

log = logging.getLogger("engine.ingest")

HTTP_TIMEOUT = 180
RETRIES = 4


def _cfg():
    url = os.environ.get("INGEST_URL", "").rstrip("/")
    secret = os.environ.get("INGEST_SECRET", "")
    if not url or not secret:
        raise RuntimeError("INGEST_URL and INGEST_SECRET must be set (Actions Secrets).")
    return url, secret


def _post(kind, body, content_type, extra_headers=None):
    url, secret = _cfg()
    if isinstance(body, (dict, list)):
        body = json.dumps(body).encode("utf-8")
    elif isinstance(body, str):
        body = body.encode("utf-8")
    gz = gzip.compress(body)
    headers = {
        "x-ingest-secret": secret,
        "x-ingest-kind": kind,
        "x-ingest-gzip": "1",
        "Content-Type": content_type,
    }
    if extra_headers:
        headers.update({k: str(v) for k, v in extra_headers.items()})

    last = None
    for attempt in range(RETRIES):
        try:
            r = requests.post(url, headers=headers, data=gz, timeout=HTTP_TIMEOUT)
            if r.status_code in (200, 201):
                log.info("ingest %s %s ok (%d->%d gz bytes)",
                         kind, extra_headers or "", len(body), len(gz))
                return r
            last = RuntimeError(f"ingest {kind} -> {r.status_code} {r.text[:200]}")
            log.warning("%s (attempt %d)", last, attempt + 1)
        except requests.RequestException as e:
            last = e
            log.warning("ingest %s failed: %s (attempt %d)", kind, e, attempt + 1)
        import time
        time.sleep(3 * (2 ** attempt))
    raise last


def put_grid(level, raw_bytes):
    _post("grid", raw_bytes, "application/octet-stream", {"x-ingest-level": level})


def put_contours(level, feature_collection):
    _post("contours", feature_collection, "application/geo+json", {"x-ingest-level": level})


def put_manifest(manifest):
    _post("manifest", manifest, "application/json")


def replace_table(table, rows):
    _post("table", rows, "application/json",
          {"x-ingest-table": table, "x-ingest-mode": "replace"})


def upsert_table(table, rows, on_conflict):
    _post("table", rows, "application/json",
          {"x-ingest-table": table, "x-ingest-mode": "upsert", "x-ingest-conflict": on_conflict})
