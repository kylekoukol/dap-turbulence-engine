"""
Turn a regular EDR grid into soft, nested GeoJSON "blobs" — one severity band at
a time, so every polygon is tagged with the exact passenger-facing severity and
a calm colour. Smooth air (EDR < 0.10) is never drawn.

We contour each band as an annulus (e.g. the "light" ring surrounds the
"moderate" core). Rendered as stacked translucent fills on MapLibre this gives
the reassuring ForeFlight-style look.
"""
import json
import logging

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import geojsoncontour  # noqa: E402

import config  # noqa: E402
from engine import palette  # noqa: E402

log = logging.getLogger("engine.contour")

# Bands we actually draw (light and above). (lo, hi, label)
_DRAW_BANDS = [b for b in config.EDR_BANDS if b[2] != "smooth"]


def _retag(feature_collection_str, label, style, extra_props=None):
    fc = json.loads(feature_collection_str)
    feats = []
    for feat in fc.get("features", []):
        geom = feat.get("geometry")
        if not geom or not geom.get("coordinates"):
            continue
        props = {
            "severity": label,
            "passenger": style["passenger"],
            "color": style["map_color"],
            "fillOpacity": style["fill_opacity"],
            "lineColor": style["line_color"],
            "score": style["score"],
        }
        if extra_props:
            props.update(extra_props)
        feats.append({"type": "Feature", "geometry": geom, "properties": props})
    return feats


def contour_band(lons, lats, grid, lo, hi, label, extra_props=None):
    style = palette.style_for_label(label)
    upper = hi if hi < 90 else float(np.nanmax(grid)) + 0.01
    if not np.isfinite(upper) or upper <= lo:
        return []
    # Anything in [lo, upper) filled as one band.
    fig, ax = plt.subplots()
    try:
        cs = ax.contourf(lons, lats, grid, levels=[lo, upper])
        gj = geojsoncontour.contourf_to_geojson(
            contourf=cs,
            ndigits=3,
            min_angle_deg=2.0,
            fill_opacity=style["fill_opacity"],
        )
        feats = _retag(gj, label, style, extra_props=extra_props)
    except Exception as e:
        log.warning("Band %s (%.2f-%.2f) produced no contour: %s", label, lo, hi, e)
        feats = []
    finally:
        plt.close(fig)
    return feats


def band_features(gridobj, extra_props=None):
    """Return the list of blob features for one grid slice (one forecast hour)."""
    lons = gridobj["lons"]
    lats = gridobj["lats"]
    grid = gridobj["grid"]
    if grid is None or not np.any(np.isfinite(grid)):
        return []
    features = []
    for lo, hi, label in _DRAW_BANDS:
        features.extend(contour_band(lons, lats, grid, lo, hi, label, extra_props))
    return features


def features_to_fc(features):
    return {"type": "FeatureCollection", "features": features}
