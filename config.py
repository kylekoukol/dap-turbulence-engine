"""
Central configuration for the Dial A Pilot turbulence engine (Plane A).

Nothing here is a secret. Secrets (SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
come from environment variables / GitHub Actions Secrets at runtime.
"""

# ---------------------------------------------------------------------------
# NOAA DAFS GTG data source
# ---------------------------------------------------------------------------
# Base directory. NCEP occasionally reorganizes; discovery lists this index at
# runtime and parses the latest dated subdir + latest cycle rather than assuming.
DAFS_BASE_URL = "https://nomads.ncep.noaa.gov/pub/data/nccf/com/dafs/prod"

# Dated subdir pattern, e.g. dafs.20260715/
DATED_DIR_PREFIX = "dafs."

# GRIB2 filename pattern. cycle = UTC hour of the run, fhr = forecast hour.
# e.g. dafs.t12z.gtg.3km.conus.f003.grib2
GTG_FILENAME_TEMPLATE = "dafs.t{cycle:02d}z.gtg.3km.conus.f{fhr:03d}.grib2"

# Forecast hours available (F000-F018 hourly). We fetch the ones we need per run.
FORECAST_HOURS = list(range(0, 19))

# Which forecast hours we actually store per cycle. Every 3h keeps Supabase
# objects small (~5MB/level) while letting the route function pick the slice
# nearest a flight's departure + en-route time (DAFS covers ~18h ahead).
STORE_FORECAST_HOURS = [0, 3, 6, 9, 12, 15, 18]

# The turbulence field in the GRIB2 .idx inventory.
# Confirmed via NOAA DAFS docs: EDPARM = GRIB2 parameter 30, per-flight-level
# max Eddy Dissipation Rate. Discovery still greps the live .idx and logs every
# EDPARM record it finds, so a rename surfaces immediately instead of silently.
EDR_RECORD_NAME = "EDPARM"
# Fallback aliases to also match if NCEP renames the mnemonic.
EDR_RECORD_ALIASES = ["EDPARM", "MAXEDR", "EDR", "EDRPARM"]

# ---------------------------------------------------------------------------
# Flight-level bands (v1)
# ---------------------------------------------------------------------------
# Feet / 100. Climb/cruise/descent coverage, cruise emphasis on FL300-FL400.
FLIGHT_LEVELS = [100, 200, 300, 350, 400]
CRUISE_LEVELS = [300, 350, 400]

# When matching an idx level to a wanted band, accept this tolerance (in FL).
FL_MATCH_TOLERANCE = 15  # +/- 1500 ft

# ---------------------------------------------------------------------------
# EDR severity model (normalized to a medium/heavy airliner)
# ---------------------------------------------------------------------------
# (edr_low_inclusive, edr_high_exclusive, internal_label)
EDR_BANDS = [
    (0.00, 0.10, "smooth"),
    (0.10, 0.20, "light"),
    (0.20, 0.40, "moderate"),
    (0.40, 0.70, "severe"),
    (0.70, 99.0, "extreme"),
]

# Contour thresholds. Draw "light" and above only — smooth means no blob.
CONTOUR_LEVELS = [0.10, 0.20, 0.40, 0.70, 99.0]

# ---------------------------------------------------------------------------
# Output grid: regular lat/lon over CONUS at ~0.1 deg (plenty for passengers)
# ---------------------------------------------------------------------------
GRID_RES_DEG = 0.1
CONUS_BOUNDS = {
    "minLat": 21.0,
    "maxLat": 53.0,
    "minLon": -125.0,
    "maxLon": -66.0,
}

# ---------------------------------------------------------------------------
# Backup layers (aviationweather.gov Data API)
# Endpoints are confirmed at runtime; these are the documented v2 data-api paths.
# ---------------------------------------------------------------------------
AWC_SIGMET_URL = "https://aviationweather.gov/api/data/airsigmet"
AWC_ISIGMET_URL = "https://aviationweather.gov/api/data/isigmet"
AWC_PIREP_URL = "https://aviationweather.gov/api/data/pirep"
AWC_GAIRMET_URL = "https://aviationweather.gov/api/data/gairmet"

# OurAirports open data (medium + large airports seeded into Supabase)
OURAIRPORTS_CSV = "https://davidmegginson.github.io/ourairports-data/airports.csv"

# ---------------------------------------------------------------------------
# Supabase data contract (the seam)
# ---------------------------------------------------------------------------
BUCKET_CONTOURS = "turbulence-contours"
BUCKET_GRIDS = "turbulence-grids"

CONTOUR_OBJECT_TEMPLATE = "latest/contours_FL{level}.geojson"
GRID_OBJECT_TEMPLATE = "latest/grid_FL{level}.bin"
MANIFEST_OBJECT = "latest/manifest.json"

# Also keep a timestamped copy under archive/<cycle_utc>/...
ARCHIVE_PREFIX_TEMPLATE = "archive/{cycle_utc}/"

# Network behavior
HTTP_TIMEOUT = 120
HTTP_RETRIES = 4
HTTP_BACKOFF = 3  # seconds, exponential
USER_AGENT = "dap-turbulence-engine/1.0 (+https://dialapilot.com; contact kyle@dialapilot.com)"
