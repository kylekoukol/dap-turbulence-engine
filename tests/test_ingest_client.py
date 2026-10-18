"""
Offline tests for the optional second ingest destination (no network).
Run: python tests/test_ingest_client.py
"""
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import ingest_client


class Resp:
    def __init__(self, code):
        self.status_code = code
        self.text = ""


def _env(app=True):
    env = {"INGEST_URL": "https://site/api/ingest", "INGEST_SECRET": "s1"}
    if app:
        env.update({"APP_INGEST_URL": "https://app/functions/v1/forecast-ingest", "APP_INGEST_SECRET": "s2"})
    return env


def _run(env, responder, fn):
    ingest_client._app_failures = 0
    calls = []

    def fake_post(url, headers=None, data=None, timeout=None):
        calls.append((url, headers["x-ingest-secret"], headers["x-ingest-kind"]))
        return responder(url)

    with mock.patch.dict(os.environ, env, clear=True), \
            mock.patch.object(ingest_client.requests, "post", side_effect=fake_post), \
            mock.patch.object(ingest_client.time, "sleep"):
        fn()
    return calls


def test_no_app_settings_means_unchanged_single_destination():
    calls = _run(_env(app=False), lambda u: Resp(200), lambda: ingest_client.put_grid(300, b"\x00" * 16))
    assert calls == [("https://site/api/ingest", "s1", "grid")], calls


def test_app_copy_sent_after_primary_with_its_own_secret():
    calls = _run(_env(), lambda u: Resp(200), lambda: ingest_client.put_manifest({"cycle_utc": "x"}))
    assert calls == [("https://site/api/ingest", "s1", "manifest"),
                     ("https://app/functions/v1/forecast-ingest", "s2", "manifest")], calls


def test_app_skips_kinds_it_does_not_use():
    calls = _run(_env(), lambda u: Resp(200), lambda: (
        ingest_client.put_contours(300, {"type": "FeatureCollection", "features": []}),
        ingest_client.replace_table("pireps", []),
        ingest_client.replace_table("sigmets", []),
    ))
    app_calls = [c for c in calls if c[0].startswith("https://app")]
    assert app_calls == [("https://app/functions/v1/forecast-ingest", "s2", "table")], calls


def test_app_failure_never_raises_and_circuit_breaks():
    def responder(url):
        return Resp(500) if url.startswith("https://app") else Resp(200)
    calls = _run(_env(), responder, lambda: [ingest_client.put_grid(l, b"\x00" * 16) for l in (100, 200, 300, 350, 400)])
    site = [c for c in calls if c[0].startswith("https://site")]
    app = [c for c in calls if c[0].startswith("https://app")]
    assert len(site) == 5, site
    # 3 failing grids x 2 attempts each, then skipped for the rest of the run
    assert len(app) == ingest_client.APP_MAX_FAILURES_PER_RUN * ingest_client.APP_RETRIES, app


def test_primary_failure_still_raises_and_skips_app():
    def responder(url):
        return Resp(500)
    raised = False
    try:
        _run(_env(), responder, lambda: ingest_client.put_grid(300, b"\x00" * 16))
    except RuntimeError:
        raised = True
    assert raised


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("  ok", name)
    print("ALL INGEST CLIENT TESTS PASSED")
