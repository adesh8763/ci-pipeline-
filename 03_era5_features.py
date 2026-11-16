
"""
Step 3: ERA5 -> atmospheric predictors (hourly) for the study region.

Computes:
    CAPE, CIN, TCWV, BLH
    925-600/500 hPa wind shear proxies
    700-850 hPa relative humidity
    925 hPa temperature and specific humidity
    850-500 hPa approximate lapse rate
    Omega at 700 hPa
    T2M, D2M, SST, Surface Pressure

Input:
    ERA5 GRIB / GRIB2 files

Output:
    data/interim/era5_features.nc

Dependencies:
    xarray, numpy, cfgrib, eccodes

Run:
    python 03_era5_features.py

Notes:
    - Supports multiple GRIB files.
    - Uses cfgrib.open_datasets() to handle multiple GRIB hypercubes.
    - Handles valid_time without renaming it into an existing time coordinate.
    - Supports pressure-level and single-level datasets.
"""

import sys
import numpy as np
import xarray as xr
import cfgrib

from config import *


# ---------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------

RENAME = {
    "pressure_level": "level",
    "isobaricInhPa": "level",
}

GRIB_EXTENSIONS = {
    ".grib",
    ".grib2",
    ".grb",
    ".grb2",
}


# ---------------------------------------------------------
# TIME COORDINATE NORMALIZATION
# ---------------------------------------------------------

def normalize_time(ds):

    # Remove singleton step dimensions where possible.
    if "step" in ds.dims and ds.sizes["step"] == 1:
        ds = ds.squeeze("step", drop=True)

    if "valid_time" in ds.coords:

        valid_time = ds["valid_time"]

        # valid_time is indexed along the existing time dimension.
        if valid_time.dims == ("time",):

            ds = ds.assign_coords(
                time=valid_time
            )

            ds = ds.drop_vars("valid_time")

        # valid_time is a scalar coordinate.
        elif valid_time.ndim == 0:

            timestamp = valid_time.values

            if "time" in ds.coords:
                ds = ds.drop_vars("time")

            ds = ds.drop_vars("valid_time")

            ds = ds.expand_dims(
                time=[timestamp]
            )

    # Handle datasets containing only a scalar time coordinate.
    elif "time" in ds.coords and "time" not in ds.dims:

        timestamp = ds["time"].values

        ds = ds.expand_dims(
            time=[timestamp]
        )

    return ds


# ---------------------------------------------------------
# LOAD ERA5 GRIB DATA
# ---------------------------------------------------------

def load(folder):

    files = sorted(
        f for f in folder.rglob("*")
        if f.is_file()
        and f.suffix.lower() in GRIB_EXTENSIONS
    )

    if not files:
        sys.exit(
            f"No ERA5 GRIB files found in {folder}"
        )

    datasets = []

    for file in files:

        print(f"\nLoading: {file.name}")

        try:

            # A GRIB file can contain multiple hypercubes.
            groups = cfgrib.open_datasets(
                str(file),
                backend_kwargs={
                    "indexpath": ""
                }
            )

            for ds in groups:

                # Normalize pressure-level coordinate names.
                rename = {
                    k: v
                    for k, v in RENAME.items()
                    if k in ds.dims or k in ds.coords
                    if v not in ds.dims and v not in ds.coords
                }

                if rename:
                    ds = ds.rename(rename)

                ds = normalize_time(ds)

                datasets.append(ds)

                print(
                    "  Variables:",
                    list(ds.data_vars)
                )

        except Exception as exc:

            sys.exit(
                f"\nFailed to read {file.name}\n"
                f"Error: {exc}"
            )

    if not datasets:
        sys.exit("No readable ERA5 datasets found.")

    print("\nMerging ERA5 datasets...")

    try:

        merged = xr.merge(
            datasets,
            compat="no_conflicts",
            join="outer"
        )

    except Exception as exc:

        sys.exit(
            "\nFailed to merge ERA5 datasets.\n"
            "Check for conflicting variables, coordinates "
            "or GRIB hypercubes.\n"
            f"Error: {exc}"
        )

    return merged


# ---------------------------------------------------------
# EXTRACT ATMOSPHERIC PREDICTORS
# ---------------------------------------------------------

def extract_features(ds):

    print("\nAvailable variables:")
    print(list(ds.data_vars))

    print("\nDataset dimensions:")
    print(dict(ds.sizes))

    out = xr.Dataset()

    # -----------------------------------------------------
    # SINGLE-LEVEL VARIABLES
    # -----------------------------------------------------

    single_level_vars = [
        ("cape", "CAPE"),
        ("cin", "CIN"),
        ("tcwv", "TCWV"),
        ("blh", "BLH"),
        ("t2m", "T2M"),
        ("d2m", "D2M"),
        ("sst", "SST"),
        ("sp", "PS"),
    ]

    for variable, name in single_level_vars:

        if variable in ds.data_vars:

            out[name] = ds[variable]

            print(f"Extracted: {name}")

    # -----------------------------------------------------
    # PRESSURE-LEVEL VARIABLES
    # -----------------------------------------------------

    if "level" not in ds.dims:

        print(
            "\nWARNING: No pressure-level dimension found."
        )

    else:

        levels = ds["level"].values

        def sel(variable, pressure):

            if (
                variable in ds.data_vars
                and pressure in levels
            ):

                return ds[variable].sel(
                    level=pressure
                )

            return None

        # -------------------------------------------------
        # WIND SHEAR
        # -------------------------------------------------

        if "u" in ds.data_vars and "v" in ds.data_vars:

            u925 = sel("u", 925)
            v925 = sel("v", 925)

            if u925 is not None and v925 is not None:

                for high_level in (600, 500):

                    u_high = sel("u", high_level)
                    v_high = sel("v", high_level)

                    if (
                        u_high is not None
                        and v_high is not None
                    ):

                        out[f"SHEAR_925_{high_level}"] = (
                            np.hypot(
                                u_high - u925,
                                v_high - v925
                            )
                        )

                        print(
                            f"Extracted: SHEAR_925_{high_level}"
                        )

        # -------------------------------------------------
        # RELATIVE HUMIDITY
        # -------------------------------------------------

        if "r" in ds.data_vars:

            rh700 = sel("r", 700)
            rh850 = sel("r", 850)

            if rh700 is not None:
                out["RH_700"] = rh700

            if rh850 is not None:
                out["RH_850"] = rh850

            if (
                rh700 is not None
                and rh850 is not None
            ):

                out["RH_700_850_mean"] = (
                    xr.concat(
                        [rh700, rh850],
                        dim="level"
                    ).mean("level")
                )

        # -------------------------------------------------
        # TEMPERATURE AND LAPSE RATE
        # -------------------------------------------------

        if "t" in ds.data_vars:

            t925 = sel("t", 925)

            if t925 is not None:
                out["T_925"] = t925

            t850 = sel("t", 850)
            t500 = sel("t", 500)

            if (
                t850 is not None
                and t500 is not None
            ):

                out["LAPSE_850_500"] = (
                    (t850 - t500) / 3.6
                )

                print("Extracted: LAPSE_850_500")

        # -------------------------------------------------
        # SPECIFIC HUMIDITY
        # -------------------------------------------------

        if "q" in ds.data_vars:

            q925 = sel("q", 925)

            if q925 is not None:

                out["Q_925"] = q925 * 1000

        # -------------------------------------------------
        # VERTICAL VELOCITY
        # -------------------------------------------------

        if "w" in ds.data_vars:

            omega700 = sel("w", 700)

            if omega700 is not None:

                out["OMEGA_700"] = omega700

    return out


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------

def main():

    print("=" * 60)
    print("ERA5 ATMOSPHERIC FEATURE EXTRACTION")
    print("=" * 60)

    # Load GRIB files.
    ds = load(ERA5_DIR)

    # Check time coordinate.
    if "time" not in ds.coords:
        sys.exit(
            "ERROR: No usable time coordinate found."
        )

    print("\nTime range before filtering:")
    print(
        ds.time.min().values,
        "to",
        ds.time.max().values
    )

    # Extract predictors.
    out = extract_features(ds)

    if not out.data_vars:
        sys.exit(
            "ERROR: No atmospheric predictors extracted."
        )

    # Filter study period.
    out = out.sel(
        time=slice(START, END)
    )

    if out.sizes.get("time", 0) == 0:
        sys.exit(
            "ERROR: No data available within START and END."
        )

    # -----------------------------------------------------
    # SAVE
    # -----------------------------------------------------

    print("\nLoading extracted features into memory...")

    out.load()

    ERA5_FEAT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    out.to_netcdf(
        ERA5_FEAT_FILE
    )

    print("\n" + "=" * 60)
    print("ERA5 FEATURE EXTRACTION COMPLETE")
    print("=" * 60)

    print("\nOutput:", ERA5_FEAT_FILE)

    print("\nExtracted variables:")
    for variable in out.data_vars:
        print(
            f"  {variable}: {out[variable].dims}"
        )

    print("\nOutput dimensions:")
    print(dict(out.sizes))

    print("\nFinal time range:")
    print(
        out.time.min().values,
        "to",
        out.time.max().values
    )


if __name__ == "__main__":
    main()
