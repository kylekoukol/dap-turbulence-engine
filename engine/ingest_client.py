"""
Write path for the engine. Lovable Cloud does not expose a service-role key, so
instead of writing to Supabase directly we POST artifacts to a small secured
ingest endpoint in the app (a server route that holds the admin credentials and
writes to Storage + tables on our behalf).

Everything is gzipped on the wire (EDR grids compress heavily). The endpoint URL
and shared secret come from the environment:
  INGEST_URL     e.g. https://<app>/api/ingest   (not secret; can live in code)
  INGEST_SECRET  shared secret (GitHub Actions Secret <-> app secret)

Optional second destination (the Dial A Pilot app backend). Only used when BOTH
are set; when either is missing the engine behaves exactly as before:
  APP_INGEST_URL     e.g. https://<project>.supabase.co/functions/v1/forecast-ingest
  APP_INGEST_SECRET  shared secret (GitHub Actions Secret <-> app backend secret)
The primary destination always goes first and keeps its retries and errors.
A failure at the second destination is logged and never stops or fails the run,
and after a few failures in one run it is skipped for the rest of that run, so
it cannot slow the primary upload down.
"""
import os
import gzip
import json
import logging
import time
import requests

log = logging.getLogger("engine.ingest")

HTTP_TIMEOUT = 180
RETRIES = 4

# Second destination: fewer retries, and it is only sent what the app backend uses.
APP_RETRIES = 2
APP_MAX_FAILURES_PER_RUN = 3
APP_KINDS = {"grid", "manifest", "table"}
APP_TABLES = {"sigmets", "airports"}

_app_failures = 0


def _cfg():
    url = os.environ.get("INGEST_URL", "").rstrip("/")
    secret = os.environ.get("INGEST_SECRET", "")
    if not url or not secret:
        raise RuntimeError("INGEST_URL and INGEST_SECRET must be set (Actions Secrets).")
    return url, secret


def _app_cfg():
    url = os.environ.get("APP_INGEST_URL", "").rstrip("/")
    secret = os.environ.get("APP_INGEST_SECRET", "")
    if not url or not secret:
        return None
    return url, secret


def _send(url, secret, kind, gz, body_len, content_type, extra_headers, retries):
    headers = {
        "x-ingest-secret": secret,
        "x-ingest-kind": kind,
        "x-ingest-gzip": "1",
        "Content-Type": content_type,
    }
    if extra_headers:
        headers.update({k: str(v) for k, v in extra_headers.items()})

    last = None
    for attempt in range(retries):
        try:
            r = requests.post(url, headers=headers, data=gz, timeout=HTTP_TIMEOUT)
            if r.status_code in (200, 201):
                log.info("ingest %s %s ok (%d->%d gz bytes)",
                         kind, extra_headers or "", body_len, len(gz))
                return r
            last = RuntimeError(f"ingest {kind} -> {r.status_code} {r.text[:200]}")
            log.warning("%s (attempt %d)", last, attempt + 1)
        except requests.RequestException as e:
            last = e
            log.warning("ingest %s failed: %s (attempt %d)", kind, e, attempt + 1)
        time.sleep(3 * (2 ** attempt))
    raise last


def _wants_app_copy(kind, extra_headers):
    if kind not in APP_KINDS:
        return False
    if kind == "table":
        table = (extra_headers or {}).get("x-ingest-table")
        return table in APP_TABLES
    return True


def _send_app_copy(kind, gz, body_len, content_type, extra_headers):
    global _app_failures
    app = _app_cfg()
    if app is None or not _wants_app_copy(kind, extra_headers):
        return
    if _app_failures >= APP_MAX_FAILURES_PER_RUN:
        log.warning("app ingest skipped for %s %s (too many failures this run)",
                    kind, extra_headers or "")
        return
    url, secret = app
    try:
        _send(url, secret, kind, gz, body_len, content_type, extra_headers, APP_RETRIES)
    except Exception as e:  # never let the second destination fail the run
        _app_failures += 1
        log.error("app ingest %s %s failed (%d/%d this run): %s",
                  kind, extra_headers or "", _app_failures, APP_MAX_FAILURES_PER_RUN, e)


def _post(kind, body, content_type, extra_headers=None):
    url, secret = _cfg()
    if isinstance(body, (dict, list)):
        body = json.dumps(body).encode("utf-8")
    elif isinstance(body, str):
        body = body.encode("utf-8")
    gz = gzip.compress(body)

    # Primary (website) first, unchanged behavior: retries, then raise.
    r = _send(url, secret, kind, gz, len(body), content_type, extra_headers, RETRIES)
    # Optional second copy for the app backend; failures are logged only.
    _send_app_copy(kind, gz, len(body), content_type, extra_headers)
    return r


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
