"""Step 4: IMERG Final V07 half-hourly precipitation -> one compact NetCDF (time, lat, lon) in mm/h,
cropped to the radar domain (+margin). Handles HDF5 (/Grid group) and NetCDF4 files.

    python 04_imerg_features.py

IMERG time convention: the time stamp is the START of the 30-min slot. 06_build_dataset.py therefore only
uses slots with  start + 30 min <= t_ref  as predictors (no leakage), and uses slots starting after the
event only for the independent IMERG-confirmed label (never as a predictor).
"""
import sys
import numpy as np
import xarray as xr
from config import *

PRECIP_NAMES = ["precipitation", "precipitationCal", "precipitation_cal"]
MARGIN_DEG = 2.5


def radar_centre():
    for f in sorted(RADAR_GRID_DIR.glob("*.nc")):
        with xr.open_dataset(f) as d:
            return d.attrs["radar_lat"], d.attrs["radar_lon"]
    return None


def open_one(path):
    try:
        ds = xr.open_dataset(path, group="Grid")
    except Exception:
        ds = xr.open_dataset(path)
    name = next((n for n in PRECIP_NAMES if n in ds), None)
    if name is None:
        raise RuntimeError(f"{path.name}: no precipitation variable in {list(ds.data_vars)}")
    da = ds[name].rename("precip")
    if "lat" not in da.dims:  # some products use latitude/longitude
        da = da.rename({"latitude": "lat", "longitude": "lon"})
    da = da.transpose("time", "lat", "lon")
    return da


def main():
    c = radar_centre()
    if c is None:
        sys.exit("Run 02_radar_grid.py first (need the radar location to crop IMERG).")
    lat0, lon0 = c
    files = sorted(list(IMERG_DIR.rglob("*.HDF5")) + list(IMERG_DIR.rglob("*.nc4")) + list(IMERG_DIR.rglob("*.nc")))
    if not files:
        sys.exit(f"No IMERG files in {IMERG_DIR}")
    print(f"{len(files)} IMERG files; cropping to {lat0:.2f}N {lon0:.2f}E +/- {MARGIN_DEG} deg")
    parts = []
    for i, f in enumerate(files):
        try:
            da = open_one(f)
            da = da.sel(lat=slice(lat0 - MARGIN_DEG, lat0 + MARGIN_DEG), lon=slice(lon0 - MARGIN_DEG, lon0 + MARGIN_DEG))
            da = da.where(da >= 0)               # IMERG fill value -9999.9 -> NaN
            da.attrs = {}
            # cftime -> numpy datetime64
            if da.indexes["time"].dtype == object:
                da = da.assign_coords(time=da.indexes["time"].to_datetimeindex(time_unit="ns"))
            parts.append(da.load())
        except Exception as e:
            print("skip", f.name, e)
        if (i + 1) % 200 == 0:
            print(f"  read {i+1}/{len(files)}")
    full = xr.concat(parts, dim="time").sortby("time").sel(time=slice(START, END + " 23:59"))
    n_dup = int(full.indexes["time"].duplicated().sum())
    if n_dup:
        print(f"WARNING: {n_dup} duplicated time stamps; keeping first")
        full = full.isel(time=~full.indexes["time"].duplicated())
    # completeness report
    dt = np.diff(full.time.values).astype("timedelta64[m]").astype(int)
    print(f"slots: {full.sizes['time']}   gaps>30min: {(dt > 30).sum()}   frac missing pixels: {float(full.isnull().mean()):.3f}")
    full.to_dataset().to_netcdf(IMERG_FEAT_FILE, encoding={"precip": {"zlib": True, "complevel": 4}})
    print("saved", IMERG_FEAT_FILE)


if __name__ == "__main__":
    main()
