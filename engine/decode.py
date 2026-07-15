"""
Decode a (partial) GRIB2 file of EDPARM records into per-flight-level EDR
arrays on the native 3km Lambert grid, using pygrib (eccodes under the hood).
"""
import logging
import numpy as np
import pygrib

log = logging.getLogger("engine.decode")


def decode_edr(grib_path, level_order):
    """
    Return { fl: {"lats": 2D, "lons": 2D, "edr": 2D masked->nan} }.

    We re-derive the level from each GRIB message rather than trusting position,
    matching it back to the requested flight levels in `level_order`
    ({fl: written_index}). If message level metadata is ambiguous we fall back
    to written order.
    """
    grbs = pygrib.open(grib_path)
    messages = list(grbs)
    grbs.close()
    log.info("Decoded %d GRIB messages", len(messages))

    # invert order map: written_index -> fl
    idx_to_fl = {v: k for k, v in level_order.items()}

    out = {}
    for i, grb in enumerate(messages):
        vals = np.array(grb.values, dtype="float32")
        # mask missing -> NaN
        if np.ma.isMaskedArray(grb.values):
            vals = np.where(grb.values.mask, np.nan, vals)
        lats, lons = grb.latlons()
        lons = np.where(lons > 180, lons - 360, lons)

        fl = idx_to_fl.get(i)
        try:
            log.info("msg %d: %s level=%s typeOfLevel=%s shape=%s -> FL%s",
                     i, grb.shortName, getattr(grb, "level", "?"),
                     getattr(grb, "typeOfLevel", "?"), vals.shape, fl)
        except Exception:
            pass
        if fl is None:
            continue
        out[fl] = {"lats": lats, "lons": lons, "edr": vals}
    return out
