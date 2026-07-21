#!/usr/bin/env python3
"""
Airport conditions + raw pilot-report collector (the turbulence data moat).

Every hour this does two things:

1) RAW ARCHIVE (national): pulls every recent US pilot report (PIREP) and stores
   the full detail of each one, append-only and de-duplicated: severity, the
   altitude and the base/top of the bumpy layer, location, turbulence type,
   aircraft, time, and the raw text. This is the compounding asset: it lets us
   analyze turbulence by altitude, by location, by route, and by airport later,
   without ever having thrown detail away.

2) AIRPORT AGGREGATE: for a large set of commercially served US airports, it
   snapshots the surface weather (wind, gusts, thunderstorms) and summarizes the
   nearby climb/descent pilot reports (within ~80 nm and at or below 20,000 ft,
   the band a flight climbs and descends through), tagged with the airport's
   local hour, into the airport_obs history that powers "best times to fly".

Data integrity: PIREPs are voluntary and skew toward reported bumps, so absence
is not proof of smooth air. We store raw counts and intensities so nothing is
inferred beyond what was reported, and the public pages show sample size.

Env:
  APP_URL        deployed app base (default https://dap-turbulence.lovable.app)
  INGEST_SECRET  shared secret (GitHub Actions Secret)
"""
import os
import re
import json
import math
import hashlib
import datetime
import requests
from zoneinfo import ZoneInfo

APP = os.environ.get("APP_URL", "https://dap-turbulence.lovable.app").rstrip("/")
SECRET = os.environ.get("INGEST_SECRET", "")
UA = "dap-turbulence-engine/1.0 (+https://dialapilot.com; contact kyle@dialapilot.com)"

METAR_URL = "https://aviationweather.gov/api/data/metar"
PIREP_URL = "https://aviationweather.gov/api/data/pirep"
CONUS_BBOX = "18,-170,72,-64"   # CONUS + Alaska + Hawaii-ish western reach

# Climb/descent catchment around an airport: a flight is climbing or descending
# within roughly this radius and altitude band on arrival and departure.
NEAR_NM = 80.0
LOW_FL = 200          # <= 20,000 ft (flight level, hundreds of feet)

HERE = os.path.dirname(os.path.abspath(__file__))
TARGETS = json.load(open(os.path.join(HERE, "airports_targets.json")))


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


# --- Aircraft classification -------------------------------------------------
# Turbulence is mass-dependent: a Cessna calls "moderate" what a jet never feels.
# For the "best times" counting we only count airline-class aircraft (jets,
# regional jets, mainstream airline turboprops), and airline flight callsigns
# that show up in the aircraft-type field. Light GA, business jets, and small
# commuters are classified but NOT counted. The raw archive keeps the class on
# every report so nothing is lost.
AIRLINE_ICAO = {
    "UAL", "AAL", "DAL", "SWA", "ASA", "JBU", "NKS", "FFT", "HAL", "SCX", "AAY",
    "SKW", "RPA", "ENY", "EDV", "AWI", "QXE", "JIA", "PDT", "MXY", "GJS", "UCA",
    "CPZ", "UPS", "FDX", "ABX", "GTI", "CKS", "ACA", "WJA", "JZA",
}
JET_TYPES = {
    "B712", "B77W", "B77L", "B772", "B78X", "B788", "B789", "B762", "B763", "B764",
    "B752", "B753", "B744", "B748", "B722", "B733", "B734", "B735", "B736", "B737",
    "B738", "B739", "A318", "A319", "A320", "A321", "A19N", "A20N", "A21N", "A332",
    "A333", "A339", "A342", "A343", "A345", "A346", "A359", "A35K", "A388", "A306",
    "A310", "BCS1", "BCS3", "MD11", "MD82", "MD83", "MD88", "MD90", "DC10", "B461",
    "B462", "B463",
}
REGIONAL_JET = {
    "E170", "E75L", "E75S", "E175", "E190", "E195", "E290", "E295", "E135", "E145",
    "E45X", "ERJ", "CRJ1", "CRJ2", "CRJ7", "CRJ9", "CRJX", "CL65", "F70", "F100",
}
AIRLINE_TPROP = {
    "DH8A", "DH8B", "DH8C", "DH8D", "AT43", "AT45", "AT72", "AT75", "AT76", "SF34", "SB20",
}
COUNTED_CLASSES = {"airliner_jet", "regional_jet", "airline_turboprop"}


def classify_aircraft(actype):
    t = (actype or "").upper().strip()
    if not t:
        return "unknown"
    m = re.match(r"^([A-Z]{3})\d+$", t)
    if m and m.group(1) in AIRLINE_ICAO:
        return "airliner_jet"
    if re.match(r"^B7\d\d$", t) or re.match(r"^B3[789]M$", t) or t in JET_TYPES:
        return "airliner_jet"
    if re.match(r"^A3\d\d$", t):
        return "airliner_jet"
    if t in REGIONAL_JET or t.startswith("CRJ") or re.match(r"^E(17|19|29|75|13|14)\d?[A-Z]?$", t):
        return "regional_jet"
    if t in AIRLINE_TPROP:
        return "airline_turboprop"
    if re.match(r"^7[0-9]{2}$", t):
        return "airliner_jet"
    return "other"


def fl_to_ft(v):
    if isinstance(v, (int, float)):
        return int(round(v)) * 100
    return None


def fetch_metars(icaos):
    """Fetch METARs in batches (the ids list can be long)."""
    out = {}
    for i in range(0, len(icaos), 100):
        batch = icaos[i:i + 100]
        try:
            r = requests.get(METAR_URL, params={"ids": ",".join(batch), "format": "json"},
                             headers={"User-Agent": UA}, timeout=60)
            r.raise_for_status()
            for m in r.json():
                code = m.get("icaoId")
                if code:
                    out[code] = m
        except Exception as e:
            print(f"metar batch {i} failed (non-fatal): {e}")
    return out


def fetch_pireps():
    try:
        r = requests.get(PIREP_URL, params={"format": "json", "age": 2, "bbox": CONUS_BBOX},
                         headers={"User-Agent": UA}, timeout=90)
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        print(f"pirep fetch failed (non-fatal): {e}")
        return []


def parse_pirep(p):
    """Full raw record for the national archive."""
    raw = p.get("rawOb") or ""
    obs = p.get("obsTime")
    if not obs or not raw:
        return None
    key = hashlib.sha1(f"{obs}|{raw}".encode("utf-8")).hexdigest()
    obs_dt = datetime.datetime.fromtimestamp(obs, tz=datetime.timezone.utc)
    tbi = max(intensity_score(p.get("tbInt1")), intensity_score(p.get("tbInt2")))
    raw_int = "/".join(x for x in [p.get("tbInt1"), p.get("tbInt2")] if x) or None
    return {
        "report_key": key,
        "obs_time": obs_dt.isoformat().replace("+00:00", "Z"),
        "lat": p.get("lat"),
        "lon": p.get("lon"),
        "altitude_ft": fl_to_ft(p.get("fltLvl")),
        "tb_base_ft": fl_to_ft(p.get("tbBas1")),
        "tb_top_ft": fl_to_ft(p.get("tbTop1")),
        "tb_intensity": tbi,
        "tb_intensity_raw": raw_int,
        "tb_type": p.get("tbType1") or None,
        "icing_raw": p.get("icgInt1") or None,
        "aircraft": p.get("acType") or None,
        "aircraft_class": classify_aircraft(p.get("acType")),
        "wx": p.get("wxString") or None,
        "station": p.get("icaoId") or None,
        "raw_ob": raw[:500],
    }


def bumpiness(wind_kt, gust_kt, convective, pirep_max):
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


def post(path, rows, label):
    ok = 0
    for i in range(0, len(rows), 400):
        batch = rows[i:i + 400]
        r = requests.post(f"{APP}{path}",
                          headers={"x-ingest-secret": SECRET, "Content-Type": "application/json"},
                          data=json.dumps({"rows": batch}), timeout=90)
        print(f"{label} batch {i}: {r.status_code} {r.text[:120]}")
        r.raise_for_status()
        ok += len(batch)
    return ok


def main():
    if not SECRET:
        raise SystemExit("INGEST_SECRET not set")

    pireps = fetch_pireps()
    metars = fetch_metars([a["icao"] for a in TARGETS])
    print(f"targets: {len(TARGETS)}  metars: {len(metars)}  pireps: {len(pireps)}")

    # 1) Raw national PIREP archive
    raw_rows = [r for r in (parse_pirep(p) for p in pireps) if r]
    if raw_rows:
        post("/api/pirep-reports", raw_rows, "pirep-reports")

    # Pre-filter PIREPs usable for airport climb/descent association: airline-class
    # aircraft only (a light GA report is not what an airliner passenger feels),
    # within the climb/descent altitude band (<= FL200).
    low = []
    for p in pireps:
        lat, lon, fl = p.get("lat"), p.get("lon"), p.get("fltLvl")
        if lat is None or lon is None:
            continue
        if isinstance(fl, (int, float)) and fl > LOW_FL:
            continue
        if classify_aircraft(p.get("acType")) not in COUNTED_CLASSES:
            continue
        low.append((lat, lon, max(intensity_score(p.get("tbInt1")), intensity_score(p.get("tbInt2")))))

    # 2) Airport-hour aggregate
    obs_rows = []
    for a in TARGETS:
        m = metars.get(a["icao"])
        if not m or not m.get("obsTime"):
            continue
        obs_dt = datetime.datetime.fromtimestamp(m["obsTime"], tz=datetime.timezone.utc)
        try:
            local_hour = obs_dt.astimezone(ZoneInfo(a["tz"])).hour
        except Exception:
            local_hour = obs_dt.hour
        wind_kt = m.get("wspd")
        gust_kt = m.get("wgst")
        wx = m.get("wxString")
        convective = bool(wx and "TS" in wx.upper())
        pc = 0
        pmax = 0
        for lat, lon, inten in low:
            if haversine_nm(a["lat"], a["lon"], lat, lon) <= NEAR_NM:
                pc += 1
                pmax = max(pmax, inten)
        obs_rows.append({
            "icao": a["icao"], "iata": a["iata"],
            "observed_at": obs_dt.isoformat().replace("+00:00", "Z"),
            "local_hour": local_hour,
            "wind_kt": wind_kt, "gust_kt": gust_kt, "wx": wx, "convective": convective,
            "pirep_count": pc, "pirep_max": pmax,
            "bumpiness": bumpiness(wind_kt, gust_kt, convective, pmax),
        })

    if obs_rows:
        post("/api/airport-obs", obs_rows, "airport-obs")
    print(f"done: {len(raw_rows)} raw reports, {len(obs_rows)} airport rows")


if __name__ == "__main__":
    main()
