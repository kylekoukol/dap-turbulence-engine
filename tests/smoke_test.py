"""
Offline smoke tests for the pieces that don't need live NOAA/Supabase:
idx parsing, level->FL conversion, EDR-record selection, grid resampling,
and contour/GeoJSON generation on a synthetic EDR field.
"""
import os
import sys
import json
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from engine import download, grid as gridmod, contour, palette


def test_idx_parse_and_select():
    # Synthetic idx lines mimicking wgrib2 output for EDPARM at flight levels.
    idx = "\n".join([
        "1:0:d=2026071512:EDPARM:9144 m above mean sea level:3 hour fcst:",
        "2:120000:d=2026071512:EDPARM:6096 m above mean sea level:3 hour fcst:",
        "3:240000:d=2026071512:EDPARM:10668 m above mean sea level:3 hour fcst:",
        "4:360000:d=2026071512:TMP:surface:3 hour fcst:",
        "5:480000:d=2026071512:EDPARM:12192 m above mean sea level:3 hour fcst:",
    ])
    recs = download.parse_idx(idx)
    assert len(recs) == 5, len(recs)
    assert recs[0]["end"] == 119999, recs[0]["end"]
    # 9144 m ~ FL300, 6096 ~ FL200, 10668 ~ FL350, 12192 ~ FL400
    assert download.level_to_fl("9144 m above mean sea level") == 300
    assert download.level_to_fl("6096 m above mean sea level") == 200
    assert download.level_to_fl("300 mb") is not None
    sel = download.select_edr_records(recs, config.FLIGHT_LEVELS)
    # FL200, FL300, FL350, FL400 should match; FL100 (3048m) has no record here
    assert 300 in sel and 350 in sel and 400 in sel and 200 in sel, sel.keys()
    assert sel[300]["num"] == "1"
    print("  idx parse/select OK ->", {k: v["num"] for k, v in sel.items()})


def _synthetic_field():
    """A native-ish grid over CONUS with a turbulence bullseye over Colorado."""
    lat = np.linspace(24, 50, 300)
    lon = np.linspace(-123, -68, 500)
    lons, lats = np.meshgrid(lon, lat)
    # bump centered near Denver (39.7, -104.9)
    d2 = (lats - 39.7) ** 2 + (lons + 104.9) ** 2
    edr = 0.55 * np.exp(-d2 / 6.0) + 0.05
    edr[lats > 48] = np.nan  # a no-data strip up north
    return {"lats": lats, "lons": lons, "edr": edr.astype("float32")}


def test_resample_and_contour():
    field = _synthetic_field()
    g = gridmod.resample_to_grid(field, decimate=1)
    assert g["grid"].shape == (len(g["lats"]), len(g["lons"]))
    assert np.nanmax(g["grid"]) > 0.4, np.nanmax(g["grid"])
    feats = contour.band_features(g, extra_props={"forecastHour": 3, "level": 300})
    assert len(feats) > 0, "expected some blobs"
    labels = {f["properties"]["severity"] for f in feats}
    assert "light" in labels or "moderate" in labels, labels
    # no fire-engine red in palette
    for f in feats:
        c = f["properties"]["color"].lower()
        assert c not in ("#ff0000", "#f00", "red"), c
    fc = contour.features_to_fc(feats)
    s = json.dumps(fc)
    assert '"forecastHour": 3' in s
    print(f"  resample+contour OK -> {len(feats)} features, labels={labels}")


def test_manifest_and_bin():
    field = _synthetic_field()
    g = gridmod.resample_to_grid(field, decimate=1)
    stack = np.ascontiguousarray(np.stack([g["grid"], g["grid"]]), dtype="<f4")
    b = stack.tobytes()
    rows, cols = g["grid"].shape
    assert len(b) == 2 * rows * cols * 4, len(b)
    man = gridmod.build_manifest("2026-07-15T12:00:00+00:00", [0, 3], [300, 350],
                                 (g["lats"], g["lons"]))
    assert man["grid_shape"] == [2, rows, cols], man["grid_shape"]
    # verify a round-trip slice read like the edge function will do
    slice1 = np.frombuffer(b, dtype="<f4", count=rows * cols,
                           offset=1 * rows * cols * 4).reshape(rows, cols)
    assert np.allclose(np.nan_to_num(slice1), np.nan_to_num(g["grid"]))
    print(f"  manifest+bin OK -> shape {man['grid_shape']}")


if __name__ == "__main__":
    test_idx_parse_and_select()
    test_resample_and_contour()
    test_manifest_and_bin()
    print("ALL SMOKE TESTS PASSED")
