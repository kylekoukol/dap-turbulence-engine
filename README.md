# DAP Turbulence Engine (Plane A)

The data engine behind the [Dial A Pilot](https://dialapilot.com) free turbulence
forecast tool. It turns NOAA's operational turbulence data into calm, map-ready
"blobs" and a route-samplable grid, and writes them into Supabase every hour.

This repo is **Plane A**. It never talks to the app directly — it only *writes*
to Supabase. The app (**Plane B**, a separate Lovable project) only *reads* from
Supabase. Supabase is the seam.

```
NOAA DAFS GTG  ──►  [ this engine, hourly GitHub Action ]  ──►  Supabase  ◄──  the app
   (GRIB2)            decode • grid • contour • blobs           storage+db      (reads only)
```

## What it does each hour

1. **Discover** the latest fully-available DAFS GTG cycle by listing the live
   NOMADS index (never hardcoded — NCEP reorganizes occasionally).
2. **Partial-download** only the `EDPARM` (per-flight-level EDR) records we need,
   at FL100/200/300/350/400, using the `.idx` + HTTP byte-range technique. We
   never pull whole ~30 MB files.
3. **Decode** GRIB2 → EDR arrays (pygrib/eccodes) on the native 3 km Lambert grid.
4. **Resample** to a regular ~0.1° lat/lon grid over CONUS (KDTree nearest).
5. **Contour** each severity band into soft, nested GeoJSON blobs using a calm
   palette (no alarming reds — smooth air draws nothing).
6. **Write** grids (`.bin`), contours (`.geojson`) and a `manifest.json` to
   Supabase Storage, plus a timestamped archive copy.
7. **Refresh** turbulence SIGMETs + PIREPs from aviationweather.gov into tables,
   and seed the `airports` table on first run.

## Data source

- **DAFS GTG**, `https://nomads.ncep.noaa.gov/pub/data/nccf/com/dafs/prod/`
- Files: `dafs.tHHz.gtg.3km.conus.fCCC.grib2`, F000–F018 hourly, 3 km CONUS.
- Turbulence field: `EDPARM` (GRIB2 parameter 30, per-flight-level max EDR).

## Severity model (EDR → passenger language)

| EDR | label | passenger-facing | map colour |
|----|--------|------------------|------------|
| <0.10 | smooth | "Smooth" | none |
| 0.10–0.20 | light | "A few light bumps — completely normal" | soft green |
| 0.20–0.40 | moderate | "Some noticeable bumps — normal and safe" | soft amber |
| 0.40–0.70 | severe | "A bumpy stretch — the crew plans around these" | muted orange |
| >0.70 | extreme | "A rough patch (rare) — pilots actively avoid these" | muted red-brown |

## Running

Locally (needs `libeccodes-dev` installed):

```bash
pip install -r requirements.txt
export SUPABASE_URL=https://YOURPROJECT.supabase.co
export SUPABASE_SERVICE_ROLE_KEY=...           # service role, server-side only
python run.py
```

In CI: `.github/workflows/refresh.yml` runs hourly (`8 * * * *`) and on demand
(`workflow_dispatch`). It reads `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`
from **Actions Secrets**. No secrets live in code.

## Supabase contract (the seam)

Storage:
- `turbulence-contours/latest/contours_FL{level}.geojson` — map blobs (features
  tagged with `forecastHour` + `level`).
- `turbulence-grids/latest/grid_FL{level}.bin` — Float32 EDR grid **stack**
  (`[forecast_hour][lat][lon]`, little-endian).
- `turbulence-grids/latest/manifest.json` — cycle, bounds, shape, levels,
  forecast hours, byte layout.

Tables: `sigmets`, `pireps`, `airports` (see the app's migration for columns).

## Coverage

CONUS-precise (DAFS GTG is CONUS-only). The route function degrades honestly
over ocean/international, where EDR has no coverage.

## v1 scope / fast-follow

v1 is the **hourly** GTG forecast. The 15-minute **GTGN** nowcast (operational
June 2026) is a documented fast-follow, not built here yet.
