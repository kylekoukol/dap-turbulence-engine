"""
Seed the `airports` table from OurAirports open data (medium + large airports).
Idempotent upsert on `icao`. Runs on the first cycle (when the table is empty)
and refreshes coordinates cheaply thereafter.
"""
import csv
import io
import logging

import config
from engine.httputil import get
from engine import supabase_io

log = logging.getLogger("engine.airports")

_KEEP_TYPES = {"medium_airport", "large_airport"}


def fetch_airports():
    r = get(config.OURAIRPORTS_CSV, timeout=120)
    reader = csv.DictReader(io.StringIO(r.text))
    rows = []
    for a in reader:
        if a.get("type") not in _KEEP_TYPES:
            continue
        icao = (a.get("ident") or a.get("icao_code") or "").strip().upper()
        if not icao:
            continue
        try:
            lat = float(a["latitude_deg"])
            lon = float(a["longitude_deg"])
        except (KeyError, ValueError):
            continue
        rows.append(
            {
                "icao": icao,
                "iata": (a.get("iata_code") or "").strip().upper() or None,
                "name": (a.get("name") or "").strip(),
                "lat": lat,
                "lon": lon,
                "country": (a.get("iso_country") or "").strip().upper() or None,
            }
        )
    log.info("Parsed %d medium/large airports from OurAirports", len(rows))
    return rows


def seed_if_needed(force=False):
    try:
        n = supabase_io.count_rows("airports")
    except Exception as e:
        log.warning("Could not count airports (%s); attempting seed anyway", e)
        n = 0
    if n > 500 and not force:
        log.info("airports already populated (%d rows) — skipping seed", n)
        return n
    rows = fetch_airports()
    return supabase_io.upsert_rows("airports", rows, on_conflict="icao")
