"""
Write outputs into Supabase — the seam between Plane A (this engine) and Plane B
(the app). Uses the raw Storage + PostgREST REST APIs with the service-role key
(no client library, to avoid version drift). Secrets come from env.
"""
import os
import json
import logging
import requests

import config

log = logging.getLogger("engine.supabase")


def _env():
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set "
            "(GitHub Actions Secrets)."
        )
    return url, key


def _headers(key, extra=None):
    h = {"apikey": key, "Authorization": f"Bearer {key}"}
    if extra:
        h.update(extra)
    return h


# --------------------------------------------------------------------------
# Storage
# --------------------------------------------------------------------------
def ensure_bucket(bucket, public=True):
    url, key = _env()
    r = requests.post(
        f"{url}/storage/v1/bucket",
        headers=_headers(key, {"Content-Type": "application/json"}),
        data=json.dumps({"id": bucket, "name": bucket, "public": public}),
        timeout=60,
    )
    if r.status_code in (200, 201):
        log.info("Created bucket %s", bucket)
    elif r.status_code == 409:
        log.info("Bucket %s already exists", bucket)
    else:
        log.warning("ensure_bucket %s -> %s %s", bucket, r.status_code, r.text[:200])


def upload(bucket, path, data, content_type):
    """Upsert an object into Storage."""
    url, key = _env()
    if isinstance(data, (dict, list)):
        data = json.dumps(data).encode("utf-8")
    elif isinstance(data, str):
        data = data.encode("utf-8")
    r = requests.post(
        f"{url}/storage/v1/object/{bucket}/{path}",
        headers=_headers(key, {"Content-Type": content_type, "x-upsert": "true"}),
        data=data,
        timeout=config.HTTP_TIMEOUT,
    )
    if r.status_code not in (200, 201):
        raise RuntimeError(f"upload {bucket}/{path} -> {r.status_code} {r.text[:200]}")
    log.info("Uploaded %s/%s (%d bytes)", bucket, path, len(data))


# --------------------------------------------------------------------------
# Tables (PostgREST)
# --------------------------------------------------------------------------
def replace_table(table, rows, chunk=500):
    """Refresh a table: delete all rows, then bulk insert current set."""
    url, key = _env()
    # delete all
    d = requests.delete(
        f"{url}/rest/v1/{table}?id=not.is.null",
        headers=_headers(key, {"Prefer": "return=minimal"}),
        timeout=config.HTTP_TIMEOUT,
    )
    if d.status_code not in (200, 204):
        log.warning("delete %s -> %s %s", table, d.status_code, d.text[:200])
    # insert in chunks
    inserted = 0
    for i in range(0, len(rows), chunk):
        part = rows[i : i + chunk]
        r = requests.post(
            f"{url}/rest/v1/{table}",
            headers=_headers(key, {"Content-Type": "application/json",
                                   "Prefer": "return=minimal"}),
            data=json.dumps(part),
            timeout=config.HTTP_TIMEOUT,
        )
        if r.status_code not in (200, 201, 204):
            log.warning("insert %s chunk -> %s %s", table, r.status_code, r.text[:300])
        else:
            inserted += len(part)
    log.info("Replaced %s: %d rows", table, inserted)
    return inserted


def upsert_rows(table, rows, on_conflict, chunk=500):
    """Idempotent upsert (used for airports)."""
    url, key = _env()
    total = 0
    for i in range(0, len(rows), chunk):
        part = rows[i : i + chunk]
        r = requests.post(
            f"{url}/rest/v1/{table}?on_conflict={on_conflict}",
            headers=_headers(key, {"Content-Type": "application/json",
                                   "Prefer": "resolution=merge-duplicates,return=minimal"}),
            data=json.dumps(part),
            timeout=config.HTTP_TIMEOUT,
        )
        if r.status_code not in (200, 201, 204):
            log.warning("upsert %s chunk -> %s %s", table, r.status_code, r.text[:300])
        else:
            total += len(part)
    log.info("Upserted %s: %d rows", table, total)
    return total


def count_rows(table):
    url, key = _env()
    r = requests.get(
        f"{url}/rest/v1/{table}?select=id",
        headers=_headers(key, {"Prefer": "count=exact", "Range": "0-0"}),
        timeout=60,
    )
    cr = r.headers.get("content-range", "*/0")
    try:
        return int(cr.split("/")[-1])
    except ValueError:
        return 0
