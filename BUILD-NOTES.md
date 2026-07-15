# Build notes & decisions

Running log of senior-engineer calls made where the spec left a genuine gap, and
things the human validator should know.

## Data source verification (build time)

- Confirmed the DAFS feed is live at
  `https://nomads.ncep.noaa.gov/pub/data/nccf/com/dafs/prod/` with `dafs.YYYYMMDD/`
  dated subdirs, exactly as the spec expected.
- Confirmed the filename pattern `dafs.tHHz.gtg.3km.conus.fCCC.grib2`, F000–F018,
  3 km CONUS, and the turbulence field **`EDPARM`** (GRIB2 parameter 30,
  per-flight-level max EDR) from NOAA's DAFS documentation.
- **Version-number discrepancy:** the spec calls this "DAFS GTG v4.0"; NOAA's
  public docs currently label the operational release **"DAFS v1.0"**. Same
  product/paths — just a naming mismatch. The engine keys off the live `.idx`
  contents, not a version string, so this is cosmetic. Noted for the validator.
- **GTGN nowcast:** the 15-minute GTGN product went operational ~June 29, 2026.
  Still correctly a fast-follow — v1 uses the hourly GTG only.
- The web preview of the NOMADS index returned a stale/proxied view during the
  build (showed May dates, 403 on subdirs). The engine does live discovery from
  the GitHub Actions runner (direct requests), which sees the true state. **The
  first Action run's logs are the real confirmation of the current cycle.**

## Idx level labelling (not fully known at build time)

We could not see a live `.idx` inventory line during the build (NOMADS
subdirectory listing was blocked from the build sandbox). So `download.py`:
- matches `EDPARM` (plus aliases MAXEDR/EDR/EDRPARM, then any var containing
  "EDR"),
- parses each record's level string flexibly (flight level / metres / pressure),
- **logs every EDR record + level it finds**, and matches each wanted flight
  level to the nearest available within ±1500 ft.
**Action item for the first run:** check the "Found N EDR records / Levels seen"
log line and confirm the FL→record mapping looks right; tighten
`FL_MATCH_TOLERANCE` or the level parser if the real labels differ.

## Grid = a time stack (contract-compatible extension)

The contract lists one `grid_FL{level}.bin` per level, but the route function is
supposed to "pick the forecast hour nearest departure." To honour both, each
`.bin` is a **stack** of Float32 grids — one per stored forecast hour
(`STORE_FORECAST_HOURS = [0,3,6,9,12,15,18]`, every 3 h to keep objects small,
~5 MB/level). `manifest.json` carries `forecast_hours` + `grid_shape` and the
byte layout so the edge function can index a slice. Contours are likewise tagged
with `forecastHour` so the **map matches the verdict** for the flight's time.

## Resampling

Native 3 km Lambert → 0.1° regular grid via KDTree nearest neighbour (fast on a
2-core Actions runner). Points >0.30° from any native cell are marked NaN =
"outside CONUS coverage," which is what drives the honest degraded-coverage note.

## SIGMET / PIREP API

aviationweather.gov Data API returned a transient 502 during the build, so exact
current field names weren't captured. `backups.py` extracts fields flexibly
(tries several candidate keys) and **logs the first object's keys each run**.
**Action item for the first run:** check the "SIGMET/PIREP sample keys" log lines
and tighten the field mapping if needed. Convective SIGMETs are kept (can imply
turbulence); pure icing SIGMETs are dropped.

## Airports

Seeded from OurAirports (`medium_airport` + `large_airport`), idempotent upsert
on `icao`. Seeded on the first run and skipped thereafter once >500 rows exist.

## Palette

Calm/muted only. Severity colours: soft green / soft amber / muted orange /
muted red-brown. Smooth air is never drawn. No fire-engine reds anywhere.

## Still to validate by a human (pilot)

Building green ≠ meteorologically correct. Before real users see it, a pilot must
eyeball 1–2 routes on a known-bumpy day against aviationweather.gov's GFA
turbulence for the same valid time, to confirm the blobs land in the right place
at the right intensity.
