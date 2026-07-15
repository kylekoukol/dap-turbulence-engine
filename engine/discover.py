"""
Discover the latest available DAFS GTG cycle by listing the live NOMADS index.

We do NOT assume a cycle exists — we list the directory, parse the dated
subdirs, then probe cycles newest-first and confirm the actual GRIB2 files are
present before committing to a cycle.
"""
import re
import logging
from datetime import datetime, timezone

import config
from engine.httputil import get

log = logging.getLogger("engine.discover")

_DATED_RE = re.compile(r"dafs\.(\d{8})/")
_HREF_RE = re.compile(r'href="([^"]+)"')


def _list_index(url):
    """Return the list of hrefs in an Apache/NGINX autoindex page."""
    r = get(url)
    return _HREF_RE.findall(r.text)


def latest_dated_dir():
    """Return (yyyymmdd, url) for the most recent dafs.YYYYMMDD directory."""
    hrefs = _list_index(config.DAFS_BASE_URL + "/")
    dates = sorted({m.group(1) for h in hrefs for m in [_DATED_RE.search(h)] if m})
    if not dates:
        raise RuntimeError(
            f"No dafs.YYYYMMDD directories found at {config.DAFS_BASE_URL}. "
            "NCEP may have reorganized — check the base path."
        )
    yyyymmdd = dates[-1]
    log.info("Latest dated dir: dafs.%s (from %d candidates)", yyyymmdd, len(dates))
    return yyyymmdd, f"{config.DAFS_BASE_URL}/dafs.{yyyymmdd}/"


def _cycles_in_dir(dir_url):
    """Parse which cycles (t00z..t23z) have GTG files present in the dir."""
    hrefs = _list_index(dir_url)
    cycles = set()
    for h in hrefs:
        m = re.search(r"dafs\.t(\d{2})z\.gtg\.3km\.conus\.f\d{3}\.grib2$", h)
        if m:
            cycles.add(int(m.group(1)))
    return sorted(cycles)


def _file_url(dir_url, cycle, fhr):
    return dir_url + config.GTG_FILENAME_TEMPLATE.format(cycle=cycle, fhr=fhr)


def _cycle_is_ready(dir_url, cycle, need_hours):
    """Confirm the .idx exists for every forecast hour we need (cheap HEAD-ish)."""
    for fhr in need_hours:
        idx_url = _file_url(dir_url, cycle, fhr) + ".idx"
        try:
            get(idx_url, timeout=30)
        except Exception:
            return False
    return True


def latest_cycle(need_hours=None):
    """
    Return a dict describing the newest fully-available cycle:
      { cycle_utc, dir_url, cycle_hour, yyyymmdd }
    Falls back to the previous day if today's dir has no ready cycle yet.
    """
    need_hours = need_hours if need_hours is not None else [0]

    # Try the two most recent dated dirs (handles just-past-midnight UTC).
    hrefs = _list_index(config.DAFS_BASE_URL + "/")
    dates = sorted({m.group(1) for h in hrefs for m in [_DATED_RE.search(h)] if m})
    if not dates:
        raise RuntimeError("No DAFS dated directories found.")

    for yyyymmdd in reversed(dates[-2:]):
        dir_url = f"{config.DAFS_BASE_URL}/dafs.{yyyymmdd}/"
        try:
            cycles = _cycles_in_dir(dir_url)
        except Exception as e:
            log.warning("Could not list %s: %s", dir_url, e)
            continue
        log.info("dafs.%s has cycles: %s", yyyymmdd, cycles)
        for cycle in reversed(cycles):
            if _cycle_is_ready(dir_url, cycle, need_hours):
                cycle_utc = f"{yyyymmdd}T{cycle:02d}:00:00Z"
                # normalize to ISO
                dt = datetime.strptime(f"{yyyymmdd}{cycle:02d}", "%Y%m%d%H").replace(
                    tzinfo=timezone.utc
                )
                log.info("Selected cycle %s", dt.isoformat())
                return {
                    "cycle_utc": dt.isoformat(),
                    "yyyymmdd": yyyymmdd,
                    "cycle_hour": cycle,
                    "dir_url": dir_url,
                }
    raise RuntimeError(
        "No fully-available DAFS GTG cycle found in the two latest dated dirs. "
        "The feed may be delayed; the next hourly run will retry."
    )


def file_url_for(cycle_info, fhr):
    return _file_url(cycle_info["dir_url"], cycle_info["cycle_hour"], fhr)
