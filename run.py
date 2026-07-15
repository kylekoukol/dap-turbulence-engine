#!/usr/bin/env python3
"""
Dial A Pilot — Turbulence Engine (Plane A) entrypoint.

Hourly pipeline:
  1. Discover the latest fully-available DAFS GTG cycle.
  2. For each stored forecast hour, partial-download the EDPARM records at our
     flight levels (.idx + byte-range), decode, and resample to a 0.1deg grid.
  3. Per level: stack the hourly slices -> Float32 .bin, and contour each slice
     -> nested calm GeoJSON blobs (tagged with forecast hour).
  4. Write grids + contours + manifest to Supabase Storage (latest/ + archive/).
  5. Refresh turbulence SIGMETs + PIREPs into Supabase tables.
  6. Seed the airports table on first run.

Secrets (SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY) come from the environment.
"""
import os
import sys
import logging
import tempfile
from datetime import datetime, timezone

import numpy as np

import config
from engine import (
    discover,
    download,
    decode,
    grid as gridmod,
    contour,
    backups,
    airports,
    supabase_io,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("run")


def build_turbulence(cycle):
    fhrs = config.STORE_FORECAST_HOURS
    axes = gridmod.target_axes()
    rows, cols = len(axes[0]), len(axes[1])
    per_level = {fl: {} for fl in config.FLIGHT_LEVELS}  # fl -> {fhr: gridobj}

    for fhr in fhrs:
        file_url = discover.file_url_for(cycle, fhr)
        try:
            idx_text = download.fetch_idx(file_url)
        except Exception as e:
            log.error("No .idx for F%03d (%s) — skipping hour", fhr, e)
            continue
        records = download.parse_idx(idx_text)
        selected = download.select_edr_records(records, config.FLIGHT_LEVELS)
        if not selected:
            log.warning("No EDR records matched at F%03d", fhr)
            continue
        tmp = tempfile.NamedTemporaryFile(suffix=".grib2", delete=False).name
        try:
            order = download.download_records(file_url, selected, tmp)
            fields = decode.decode_edr(tmp, order)
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass
        for fl, field in fields.items():
            try:
                per_level[fl][fhr] = gridmod.resample_to_grid(field)
            except Exception as e:
                log.error("Resample failed FL%s F%03d: %s", fl, fhr, e)

    stored_hours = [h for h in fhrs
                    if any(h in per_level[fl] for fl in config.FLIGHT_LEVELS)]
    if not stored_hours:
        raise RuntimeError("No turbulence data produced for any forecast hour.")
    log.info("Stored forecast hours: %s", stored_hours)

    supabase_io.ensure_bucket(config.BUCKET_GRIDS, public=True)
    supabase_io.ensure_bucket(config.BUCKET_CONTOURS, public=True)

    levels_out = []
    archive = config.ARCHIVE_PREFIX_TEMPLATE.format(cycle_utc=cycle["cycle_utc"].replace(":", ""))
    for fl in config.FLIGHT_LEVELS:
        slices = per_level[fl]
        if not slices:
            log.warning("FL%s: no data, skipping", fl)
            continue
        levels_out.append(fl)
        stack, feats = [], []
        for h in stored_hours:
            g = slices.get(h)
            if g is None:
                stack.append(np.full((rows, cols), np.nan, dtype="float32"))
            else:
                stack.append(np.asarray(g["grid"], dtype="float32"))
                feats.extend(
                    contour.band_features(g, extra_props={"forecastHour": h, "level": fl})
                )
        stackarr = np.ascontiguousarray(np.stack(stack), dtype="<f4")
        grid_path = config.GRID_OBJECT_TEMPLATE.format(level=fl)
        fc = contour.features_to_fc(feats)
        contour_path = config.CONTOUR_OBJECT_TEMPLATE.format(level=fl)

        supabase_io.upload(config.BUCKET_GRIDS, grid_path, stackarr.tobytes(),
                           "application/octet-stream")
        supabase_io.upload(config.BUCKET_CONTOURS, contour_path, fc,
                           "application/geo+json")
        # timestamped archive copies
        supabase_io.upload(config.BUCKET_GRIDS, archive + f"grid_FL{fl}.bin",
                           stackarr.tobytes(), "application/octet-stream")
        supabase_io.upload(config.BUCKET_CONTOURS, archive + f"contours_FL{fl}.geojson",
                           fc, "application/geo+json")

    manifest = gridmod.build_manifest(cycle["cycle_utc"], stored_hours, levels_out, axes)
    manifest["generated_utc"] = datetime.now(timezone.utc).isoformat()
    supabase_io.upload(config.BUCKET_GRIDS, config.MANIFEST_OBJECT, manifest,
                       "application/json")
    supabase_io.upload(config.BUCKET_GRIDS, archive + "manifest.json", manifest,
                       "application/json")
    log.info("Turbulence outputs written for levels %s", levels_out)
    return manifest


def refresh_backups():
    try:
        supabase_io.replace_table("sigmets", backups.fetch_sigmets())
    except Exception as e:
        log.error("SIGMET refresh failed: %s", e)
    try:
        supabase_io.replace_table("pireps", backups.fetch_pireps())
    except Exception as e:
        log.error("PIREP refresh failed: %s", e)


def main():
    started = datetime.now(timezone.utc)
    log.info("=== DAP turbulence engine run @ %s ===", started.isoformat())

    # airports seed first (cheap, idempotent) so the app has them even if the
    # GTG step has a bad cycle.
    try:
        airports.seed_if_needed()
    except Exception as e:
        log.error("Airport seed failed: %s", e)

    cycle = discover.latest_cycle(need_hours=config.STORE_FORECAST_HOURS)
    log.info("Using cycle %s (dir %s)", cycle["cycle_utc"], cycle["dir_url"])

    manifest = build_turbulence(cycle)
    refresh_backups()

    dur = (datetime.now(timezone.utc) - started).total_seconds()
    log.info("=== Done in %.0fs. Cycle %s, levels %s ===",
             dur, manifest["cycle_utc"], manifest["levels"])


if __name__ == "__main__":
    main()
