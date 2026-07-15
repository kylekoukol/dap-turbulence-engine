"""
Partial GRIB2 download using the .idx + HTTP byte-range technique
(the Wesley Ebisuzaki method). We fetch ONLY the EDPARM records at the flight
levels we need — never the whole ~30MB file.
"""
import re
import logging

import config
from engine.httputil import get

log = logging.getLogger("engine.download")


def _std_pressure_to_fl(hpa):
    """Rough ISA pressure(hPa) -> flight level (feet/100)."""
    # Barometric formula, troposphere/lower-stratosphere approximation.
    import math
    p = float(hpa)
    if p <= 0:
        return None
    if p > 226.32:  # below ~11km, troposphere
        # h = 44330 * (1 - (p/1013.25)^0.1903) meters
        h_m = 44330.0 * (1.0 - (p / 1013.25) ** 0.190263)
    else:
        # lower stratosphere (isothermal layer above 11km)
        h_m = 11000.0 + (math.log(226.32 / p) * 6341.6)
    return round(h_m * 3.28084 / 100.0)


def level_to_fl(level_str):
    """Parse an idx level field into a flight level (feet/100), or None."""
    s = level_str.strip().lower()
    # explicit flight level
    m = re.search(r"fl\s*0*(\d{2,3})", s)
    if m:
        return int(m.group(1))
    # pressure levels
    if "mb" in s or "hpa" in s or "pa " in s:
        m = re.search(r"([\d.]+)", s)
        if m:
            val = float(m.group(1))
            if " pa" in s and "hpa" not in s and "mb" not in s:
                val = val / 100.0  # Pa -> hPa
            return _std_pressure_to_fl(val)
    # height in metres above msl/ground
    m = re.search(r"([\d.]+)\s*m\b", s)
    if m:
        meters = float(m.group(1))
        return round(meters * 3.28084 / 100.0)
    return None


def parse_idx(idx_text):
    """
    Parse a wgrib2/eccodes .idx inventory into records with byte ranges.
    Line format: N:startbyte:d=YYYYMMDDHH:VAR:LEVEL:FCST:...
    """
    records = []
    for line in idx_text.strip().splitlines():
        if not line.strip():
            continue
        parts = line.split(":")
        if len(parts) < 5:
            continue
        try:
            start = int(parts[1])
        except ValueError:
            continue
        records.append(
            {
                "num": parts[0],
                "start": start,
                "date": parts[2],
                "var": parts[3],
                "level": parts[4],
                "rest": parts[5:],
                "raw": line,
            }
        )
    # end byte = next record start - 1 (last record: open-ended)
    for i, rec in enumerate(records):
        rec["end"] = records[i + 1]["start"] - 1 if i + 1 < len(records) else None
    return records


def select_edr_records(records, wanted_levels):
    """
    Find EDPARM (or alias) records and match each wanted flight level to the
    closest available record. Logs every EDR record found so a rename/relabel
    is immediately visible in the Action logs.
    """
    aliases = {a.upper() for a in config.EDR_RECORD_ALIASES}
    edr_recs = [r for r in records if r["var"].upper() in aliases]
    if not edr_recs:
        # fall back to substring match (e.g. "MAXEDR", "EDR SFC")
        edr_recs = [r for r in records if "EDR" in r["var"].upper()]

    for r in edr_recs:
        r["fl"] = level_to_fl(r["level"])
    log.info(
        "Found %d EDR records. Levels seen: %s",
        len(edr_recs),
        sorted({(r["var"], r["level"], r["fl"]) for r in edr_recs}, key=str),
    )

    selected = {}
    for want in wanted_levels:
        best, best_d = None, None
        for r in edr_recs:
            if r["fl"] is None:
                continue
            d = abs(r["fl"] - want)
            if best is None or d < best_d:
                best, best_d = r, d
        if best is not None and best_d <= config.FL_MATCH_TOLERANCE:
            selected[want] = best
            log.info("FL%s -> idx record %s (level '%s', dist %d)",
                     want, best["num"], best["level"], best_d)
        else:
            log.warning("FL%s: no EDR record within tolerance (closest dist %s)",
                        want, best_d)
    return selected


def fetch_idx(file_url):
    return get(file_url + ".idx", timeout=60).text


def download_records(file_url, records_by_level, out_path):
    """
    Byte-range download the selected records into a single concatenated GRIB2
    file. Returns the mapping {fl: message_index} in the order written so the
    decoder can associate each message back to its flight level.
    """
    order = {}
    with open(out_path, "wb") as f:
        idx = 0
        for fl, rec in records_by_level.items():
            end = rec["end"]
            rng = "bytes=%d-%s" % (rec["start"], end if end is not None else "")
            r = get(file_url, headers={"Range": rng}, expect_binary=True)
            f.write(r.content)
            order[fl] = idx
            idx += 1
            log.info("Downloaded FL%s (%s bytes)", fl, len(r.content))
    return order
