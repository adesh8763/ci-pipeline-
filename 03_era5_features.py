"""Step 3: ERA5 -> atmospheric predictors (hourly) for the study region.

Computes, from pressure-level and/or single-level fields where available:
  CAPE, CIN (if present), TCWV, 0-6 km-proxy shear (u,v 925 vs 600/500 hPa), 700-850 hPa RH,
  low-level (925 hPa) moisture/temperature, mid-level lapse rate (850-500), boundary-layer height, SST/T2m.
Output: data/interim/era5_features.nc

    python 03_era5_features.py
Variable names differ between CDS downloads; check with 00_inventory.py and edit RENAME if needed.
"""
import sys
import numpy as np
import xarray as xr
from config import *

RENAME = {"valid_time": "time", "pressure_level": "level", "isobaricInhPa": "level"}


def load(folder):
    files = sorted(folder.rglob("*.nc"))
    if not files:
        sys.exit("No ERA5 .nc files found (if they're GRIB, tell me and I'll switch to cfgrib).")
    ds = xr.open_mfdataset(files, combine="by_coords", chunks={"time": 24})
    return ds.rename({k: v for k, v in RENAME.items() if k in ds.dims or k in ds.coords})


def main():
    ds = load(ERA5_DIR)
    print("variables:", list(ds.data_vars), "dims:", dict(ds.sizes))
    out = xr.Dataset()

    for v, name in [("cape", "CAPE"), ("cin", "CIN"), ("tcwv", "TCWV"), ("blh", "BLH"),
                    ("t2m", "T2M"), ("d2m", "D2M"), ("sst", "SST"), ("sp", "PS")]:
        if v in ds:
            out[name] = ds[v]

    if "level" in ds.dims:
        sel = lambda var, p: ds[var].sel(level=p) if var in ds else None
        if "u" in ds and "v" in ds:
            for hi in (600, 500):
                if hi in ds.level:
                    out[f"SHEAR_925_{hi}"] = np.hypot(sel("u", hi) - sel("u", 925), sel("v", hi) - sel("v", 925))
        if "r" in ds:
            out["RH_700"] = sel("r", 700)
            out["RH_850"] = sel("r", 850)
            out["RH_700_850_mean"] = ds["r"].sel(level=[700, 850]).mean("level")
        if "t" in ds:
            out["T_925"] = sel("t", 925)
            out["LAPSE_850_500"] = (sel("t", 850) - sel("t", 500)) / 3.6  # K/km (approx. 3.6 km layer)
        if "q" in ds:
            out["Q_925"] = sel("q", 925) * 1000  # g/kg
        if "w" in ds:
            out["OMEGA_700"] = sel("w", 700)
    out = out.sel(time=slice(START, END))
    out.load().to_netcdf(ERA5_FEAT_FILE)
    print("saved", ERA5_FEAT_FILE, list(out.data_vars))


if __name__ == "__main__":
    main()
