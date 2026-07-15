"""
Backup layers from the aviationweather.gov Data API: turbulence SIGMETs
(escalate-only) and PIREPs (confidence + human voice). Written to Supabase
tables each hourly run.

The AWC API has changed field names before, so extraction is deliberately
flexible: we try several candidate keys and log the first object's keys so the
real schema is visible in the Action logs on the first run.
"""
import logging
from datetime import datetime, timezone

import config
from engine.httputil import get

log = logging.getLogger("engine.backups")


def _first(d, *keys, default=None):
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return default


def _to_iso(v):
    if v is None:
        return None
    # epoch seconds?
    try:
        n = float(v)
        if n > 1_000_000_000:
            return datetime.fromtimestamp(n, tz=timezone.utc).isoformat()
    except (TypeError, ValueError):
        pass
    return str(v)


def _get_json(url):
    r = get(url + ("&" if "?" in url else "?") + "format=json", timeout=90)
    try:
        data = r.json()
    except Exception:
        log.warning("Non-JSON from %s", url)
        return []
    if isinstance(data, dict):
        # some endpoints wrap in {"features"/"data": [...]}
        for k in ("features", "data", "results"):
            if isinstance(data.get(k), list):
                return data[k]
        return [data]
    return data if isinstance(data, list) else []


def _coords_to_polygon(obj):
    """Build a GeoJSON Polygon from AWC coord points, if present."""
    coords = _first(obj, "coords", "area", "points")
    if not coords or not isinstance(coords, list):
        return None
    ring = []
    for p in coords:
        if isinstance(p, dict):
            lat = _first(p, "lat", "latitude")
            lon = _first(p, "lon", "long", "longitude")
        elif isinstance(p, (list, tuple)) and len(p) >= 2:
            lat, lon = p[1], p[0]
        else:
            continue
        if lat is None or lon is None:
            continue
        ring.append([float(lon), float(lat)])
    if len(ring) < 3:
        return None
    if ring[0] != ring[-1]:
        ring.append(ring[0])
    return {"type": "Polygon", "coordinates": [ring]}


def fetch_sigmets():
    rows = []
    for url in (config.AWC_SIGMET_URL, config.AWC_ISIGMET_URL):
        try:
            objs = _get_json(url + "?hazard=turb")
        except Exception as e:
            log.warning("SIGMET fetch failed %s: %s", url, e)
            continue
        if objs:
            log.info("SIGMET sample keys (%s): %s", url, list(objs[0].keys()))
        for o in objs:
            hazard = str(_first(o, "hazard", "hazardType", default="")).upper()
            if "TURB" not in hazard and "CONV" not in hazard and hazard != "":
                # keep convective too (can imply turbulence); skip pure ICE
                if "ICE" in hazard:
                    continue
            geom = _coords_to_polygon(o)
            rows.append(
                {
                    "hazard": hazard or "TURB",
                    "geometry": geom,
                    "fl_lo": _first(o, "altitudeLow1", "altitudeLow", "minFt", "base"),
                    "fl_hi": _first(o, "altitudeHi1", "altitudeHi", "maxFt", "top"),
                    "valid_from": _to_iso(_first(o, "validTimeFrom", "validTimeFromISO", "issueTime")),
                    "valid_to": _to_iso(_first(o, "validTimeTo", "validTimeToISO", "expireTime")),
                    "raw_text": _first(o, "rawAirSigmet", "raw_text", "rawSigmet", "rawOb", default=""),
                }
            )
    log.info("Fetched %d turbulence SIGMET rows", len(rows))
    return rows


def fetch_pireps(age_hours=3):
    try:
        objs = _get_json(f"{config.AWC_PIREP_URL}?age={age_hours}")
    except Exception as e:
        log.warning("PIREP fetch failed: %s", e)
        return []
    if objs:
        log.info("PIREP sample keys: %s", list(objs[0].keys()))
    rows = []
    for o in objs:
        lat = _first(o, "lat", "latitude")
        lon = _first(o, "lon", "longitude")
        if lat is None or lon is None:
            continue
        # turbulence intensity fields vary: tbInt1, turbulence, tbType
        intensity = _first(o, "tbInt1", "turbIntensity", "tbType", "intensity")
        rows.append(
            {
                "lat": float(lat),
                "lon": float(lon),
                "altitude_ft": _first(o, "fltLvl", "altitude_ft", "fltlvl", "altitude"),
                "intensity": str(intensity) if intensity is not None else None,
                "observed_at": _to_iso(_first(o, "obsTime", "receiptTime", "reportTime")),
                "raw_text": _first(o, "rawOb", "raw_text", "report", default=""),
            }
        )
    log.info("Fetched %d PIREP rows", len(rows))
    return rows
