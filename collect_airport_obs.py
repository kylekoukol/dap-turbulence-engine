#!/usr/bin/env python3
"""
Airport conditions collector (the "best times to fly" data moat).

Every hour, for a set of major US airports, we snapshot the surface weather
(wind, gusts, thunderstorms) from the METAR and count nearby low-altitude pilot
turbulence reports, tag each with the airport's LOCAL hour of day, compute a
transparent bumpiness proxy, and append it to the airport_obs history in
Supabase (via a secured app ingest route). Over weeks and seasons this builds a
real, observed picture of which hours are typically smoothest into and out of
each airport. It is append-only and compounding: every run makes it better.

Data integrity notes:
- METAR fields (wind/gust/wx) are reliable and observed.
- PIREPs are voluntary and sparse, and skew toward reported bumps; absence of a
  report does NOT mean smooth air. We store the raw counts/intensities so the
  score can be recomputed, and the public pages must show sample size and treat
  thin data honestly.

Env:
  APP_URL        deployed app base (default https://dap-turbulence.lovable.app)
  INGEST_SECRET  shared secret (GitHub Actions Secret)
"""
import os
import json
import math
import datetime
import requests
from zoneinfo import ZoneInfo

APP = os.environ.get("APP_URL", "https://dap-turbulence.lovable.app").rstrip("/")
SECRET = os.environ.get("INGEST_SECRET", "")
UA = "dap-turbulence-engine/1.0 (+https://dialapilot.com; contact kyle@dialapilot.com)"

METAR_URL = "https://aviationweather.gov/api/data/metar"
PIREP_URL = "https://aviationweather.gov/api/data/pirep"
CONUS_BBOX = "21,-125,50,-66"

# iata, icao, lat, lon, IANA timezone. The airports nervous fliers ask about
# most, plus the major hubs and the known time-of-day / convective / terrain
# offenders. Easy to extend.
AIRPORTS = [
    ("LAS", "KLAS", 36.0801, -115.1522, "America/Los_Angeles"),
    ("LAX", "KLAX", 33.9416, -118.4085, "America/Los_Angeles"),
    ("SFO", "KSFO", 37.6213, -122.3790, "America/Los_Angeles"),
    ("SEA", "KSEA", 47.4502, -122.3088, "America/Los_Angeles"),
    ("SMF", "KSMF", 38.6954, -121.5908, "America/Los_Angeles"),
    ("SAN", "KSAN", 32.7336, -117.1897, "America/Los_Angeles"),
    ("DEN", "KDEN", 39.8561, -104.6737, "America/Denver"),
    ("SLC", "KSLC", 40.7899, -111.9791, "America/Denver"),
    ("PHX", "KPHX", 33.4342, -112.0116, "America/Phoenix"),
    ("DFW", "KDFW", 32.8998, -97.0403, "America/Chicago"),
    ("IAH", "KIAH", 29.9902, -95.3368, "America/Chicago"),
    ("ORD", "KORD", 41.9742, -87.9073, "America/Chicago"),
    ("MSP", "KMSP", 44.8848, -93.2223, "America/Chicago"),
    ("ATL", "KATL", 33.6407, -84.4277, "America/New_York"),
    ("MCO", "KMCO", 28.4312, -81.3081, "America/New_York"),
    ("MIA", "KMIA", 25.7959, -80.2870, "America/New_York"),
    ("JFK", "KJFK", 40.6413, -73.7781, "America/New_York"),
    ("LGA", "KLGA", 40.7769, -73.8740, "America/New_York"),
    ("BOS", "KBOS", 42.3656, -71.0096, "America/New_York"),
    ("DCA", "KDCA", 38.8512, -77.0402, "America/New_York"),
]

NEAR_NM = 50.0        # count PIREPs within this radius of the airport
LOW_FL = 120          # only low-altitude reports (<= 12,000 ft) matter for arr/dep


def haversine_nm(lat1, lon1, lat2, lon2):
    R = 3440.065
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(min(1.0, math.sqrt(a)))


def intensity_score(s):
    v = (s or "").upper()
    if "EXT" in v:
        return 4
    if "SEV" in v:
        return 3
    if "MOD" in v:
        return 2
    if "LGT" in v or v == "LT":
        return 1
    return 0


def fetch_metars(icaos):
    r = requests.get(METAR_URL, params={"ids": ",".join(icaos), "format": "json"},
                     headers={"User-Agent": UA}, timeout=60)
    r.raise_for_status()
    out = {}
    for m in r.json():
        code = m.get("icaoId")
        if code:
            out[code] = m
    return out


def fetch_pireps():
    try:
        r = requests.get(PIREP_URL, params={"format": "json", "age": 2, "bbox": CONUS_BBOX},
                         headers={"User-Agent": UA}, timeout=60)
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        print(f"pirep fetch failed (non-fatal): {e}")
        return []


def nearby_pireps(lat, lon, pireps):
    count = 0
    peak = 0
    for p in pireps:
        plat, plon = p.get("lat"), p.get("lon")
        if plat is None or plon is None:
            continue
        fl = p.get("fltLvl")
        if isinstance(fl, (int, float)) and fl > LOW_FL:
            continue
        if haversine_nm(lat, lon, plat, plon) > NEAR_NM:
            continue
        count += 1
        peak = max(peak, intensity_score(p.get("tbInt1")), intensity_score(p.get("tbInt2")))
    return count, peak


def bumpiness(wind_kt, gust_kt, convective, pirep_max):
    """Transparent 0-4 proxy from surface weather + nearby reports. Stored
    alongside the raw fields so it can be recomputed if we tune the formula."""
    score = 0
    if isinstance(wind_kt, (int, float)) and wind_kt >= 20:
        score += 1
    if isinstance(gust_kt, (int, float)) and gust_kt >= 25:
        score += 1
    if convective:
        score += 2
    if pirep_max >= 3:
        score += 2
    elif pirep_max >= 2:
        score += 1
    return min(score, 4)


def main():
    if not SECRET:
        raise SystemExit("INGEST_SECRET not set")
    metars = fetch_metars([a[1] for a in AIRPORTS])
    pireps = fetch_pireps()
    print(f"metars: {len(metars)}  pireps(conus): {len(pireps)}")

    rows = []
    for iata, icao, lat, lon, tz in AIRPORTS:
        m = metars.get(icao)
        if not m:
            print(f"{icao}: no METAR, skipping")
            continue
        obs_ts = m.get("obsTime")
        if not obs_ts:
            print(f"{icao}: no obsTime, skipping")
            continue
        obs_dt = datetime.datetime.fromtimestamp(obs_ts, tz=datetime.timezone.utc)
        local_hour = obs_dt.astimezone(ZoneInfo(tz)).hour
        wind_kt = m.get("wspd")
        gust_kt = m.get("wgst")
        wx = m.get("wxString")
        convective = bool(wx and "TS" in wx.upper())
        pc, pmax = nearby_pireps(lat, lon, pireps)
        rows.append({
            "icao": icao,
            "iata": iata,
            "observed_at": obs_dt.isoformat().replace("+00:00", "Z"),
            "local_hour": local_hour,
            "wind_kt": wind_kt,
            "gust_kt": gust_kt,
            "wx": wx,
            "convective": convective,
            "pirep_count": pc,
            "pirep_max": pmax,
            "bumpiness": bumpiness(wind_kt, gust_kt, convective, pmax),
        })

    if not rows:
        raise SystemExit("no rows built")

    r = requests.post(f"{APP}/api/airport-obs",
                      headers={"x-ingest-secret": SECRET, "Content-Type": "application/json"},
                      data=json.dumps({"rows": rows}), timeout=60)
    print(f"ingest {r.status_code}: {r.text[:200]}")
    r.raise_for_status()


if __name__ == "__main__":
    main()
