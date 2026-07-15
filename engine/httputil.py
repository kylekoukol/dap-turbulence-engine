"""Small, dependency-light HTTP helper with retries + a shared session."""
import time
import logging
import requests

import config

log = logging.getLogger("engine.http")

_session = None


def session():
    global _session
    if _session is None:
        s = requests.Session()
        s.headers.update({"User-Agent": config.USER_AGENT})
        _session = s
    return _session


def get(url, headers=None, timeout=None, stream=False, expect_binary=False):
    """GET with exponential-backoff retries. Raises on final failure."""
    timeout = timeout or config.HTTP_TIMEOUT
    last = None
    for attempt in range(config.HTTP_RETRIES):
        try:
            r = session().get(url, headers=headers, timeout=timeout, stream=stream)
            if r.status_code in (200, 206):
                return r
            # 404 is meaningful for discovery — don't retry forever
            if r.status_code == 404:
                r.raise_for_status()
            last = requests.HTTPError(f"{r.status_code} for {url}")
            log.warning("GET %s -> %s (attempt %d)", url, r.status_code, attempt + 1)
        except requests.RequestException as e:
            last = e
            log.warning("GET %s failed: %s (attempt %d)", url, e, attempt + 1)
        time.sleep(config.HTTP_BACKOFF * (2 ** attempt))
    raise last if last else RuntimeError(f"GET failed: {url}")
