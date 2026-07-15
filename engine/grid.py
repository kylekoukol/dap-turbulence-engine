"""
Reproject/resample native 3km Lambert EDR fields onto a regular lat/lon grid at
~0.1 deg over CONUS, using a KDTree nearest-neighbour lookup (fast + robust on a
2-core GitHub Actions runner). Produces the Float32 grid (.bin) + manifest that
the route edge function samples.
"""
import io
import json
import logging
import numpy as np
from scipy.spatial import cKDTree

import config

log = logging.getLogger("engine.grid")


def target_axes():
    b = config.CONUS_BOUNDS
    res = config.GRID_RES_DEG
    lats = np.arange(b["minLat"], b["maxLat"] + res / 2, res)
    lons = np.arange(b["minLon"], b["maxLon"] + res / 2, res)
    return lats, lons


def _build_tree(native_lats, native_lons, decimate):
    la = native_lats[::decimate, ::decimate].ravel()
    lo = native_lons[::decimate, ::decimate].ravel()
    # Equirectangular scaling so degrees are roughly comparable in distance.
    coslat = np.cos(np.deg2rad(np.nanmean(la)))
    pts = np.column_stack([la, lo * coslat])
    tree = cKDTree(pts)
    return tree, coslat, decimate


def resample_to_grid(field, decimate=2):
    """field = {"lats","lons","edr"} on native grid -> regular grid dict."""
    lats, lons = target_axes()
    glon, glat = np.meshgrid(lons, lats)  # shape (rows, cols)

    native_lats = field["lats"]
    native_lons = field["lons"]
    edr = field["edr"][::decimate, ::decimate].ravel()

    tree, coslat, _ = _build_tree(native_lats, native_lons, decimate)
    q = np.column_stack([glat.ravel(), glon.ravel() * coslat])
    dist, idx = tree.query(q, k=1)
    sampled_flat = edr[idx]

    # Points too far from any native cell (outside CONUS coverage) -> NaN.
    # Native spacing is ~0.1-0.15 deg; anything beyond ~0.30 deg is off-grid.
    sampled_flat = np.where(dist > 0.30, np.nan, sampled_flat)
    sampled = sampled_flat.reshape(glat.shape).astype("float32")
    log.info("Resampled to %s grid, %.1f%% covered",
             sampled.shape, 100.0 * np.mean(~np.isnan(sampled)))
    return {"lats": lats, "lons": lons, "grid": sampled}


def grid_to_bin(grid):
    """
    Serialize the Float32 grid to bytes. Layout: row-major (lat ascending,
    lon ascending), NaN for no-coverage. Shape/bounds live in the manifest.
    """
    arr = np.ascontiguousarray(grid["grid"], dtype="<f4")  # little-endian float32
    return arr.tobytes()


def build_manifest(cycle_utc, forecast_hours, levels, sample_axes):
    lats, lons = sample_axes
    return {
        "cycle_utc": cycle_utc,
        "generated_utc": None,  # filled by run.py
        "forecast_hours": forecast_hours,
        "bounds": {
            "minLat": float(lats[0]),
            "maxLat": float(lats[-1]),
            "minLon": float(lons[0]),
            "maxLon": float(lons[-1]),
        },
        "shape": [int(len(lats)), int(len(lons))],
        "grid_shape": [int(len(forecast_hours)), int(len(lats)), int(len(lons))],
        "res_deg": config.GRID_RES_DEG,
        "levels": levels,
        "grid_dtype": "float32-le",
        "grid_order": "[forecast_hour][lat ascending][lon ascending], row-major",
        "nodata": "NaN",
        "note": (
            "grid_FL{level}.bin is a stack of len(forecast_hours) Float32 grids. "
            "Slice k (forecast_hours[k]) starts at byte k*rows*cols*4."
        ),
    }
