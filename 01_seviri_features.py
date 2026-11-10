"""
Step 1: SEVIRI -> per-scene brightness-temperature features on a common grid.

Reads NetCDF files from:
    data/raw/seviri_tailored
    data/interim/seviri_box

Writes one compact NetCDF per day to:
    data/interim/seviri_features

Derived fields:
    d_BT108_15min   Previous BT - current BT over 15 min (positive = cooling)
    d_BT108_30min   Previous BT - current BT over 30 min
    BTD_62_73       WV6.2 - WV7.3
    BTD_87_108      IR8.7 - IR10.8
    BTD_108_120     IR10.8 - IR12.0
    BTD_39_108      IR3.9 - IR10.8

Run:
    python 01_seviri_features.py
"""

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from config import *


# Source variable name -> standardised SEVIRI channel name.
# Check these against the output of 00_inventory.py.
CHANNEL_MAP = {
    "channel_4": "IR039",
    "channel_5": "WV062",
    "channel_6": "WV073",
    "channel_7": "IR087",
    "channel_9": "IR108",
    "channel_10": "IR120",
    "channel_11": "IR134",

    "IR_039": "IR039",
    "WV_062": "WV062",
    "WV_073": "WV073",
    "IR_087": "IR087",
    "IR_108": "IR108",
    "IR_120": "IR120",
    "IR_134": "IR134",
}


def open_any(path):
    """
    Open the NetCDF without automatically decoding its time variable.

    We assign a consistent timestamp ourselves using metadata or
    the filename, avoiding failures caused by malformed time metadata.
    """
    return xr.open_dataset(
        path,
        decode_times=False,
        mask_and_scale=True
    )


def parse_timestamp(value):
    """Convert a metadata timestamp into datetime64[ns]."""

    if value is None:
        return None

    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="ignore")

    try:
        timestamp = pd.to_datetime(
            value,
            utc=True,
            errors="coerce"
        )

        if pd.isna(timestamp):
            return None

        # Convert timezone-aware pandas timestamp to UTC datetime64[ns].
        timestamp = timestamp.tz_convert("UTC").tz_localize(None)

        return np.datetime64(timestamp.to_datetime64(), "ns")

    except (TypeError, ValueError, OverflowError):
        return None


def timestamp_from_filename(path):
    """
    Extract acquisition time from common SEVIRI filename patterns.

    Supported examples:
        HRSEVIRI_20060819T120000Z...
        ...-20060819120000.000Z-...
        ...-20060819120000Z-...
    """

    name = Path(path).name

    # EUMETSAT Data Tailor-style filename.
    match = re.search(
        r"HRSEVIRI_(\d{8}T\d{6})Z",
        name
    )

    if match:
        timestamp = pd.to_datetime(
            match.group(1),
            format="%Y%m%dT%H%M%S",
            utc=True
        )

        timestamp = timestamp.tz_convert(None)

        return np.datetime64(timestamp.to_datetime64(), "ns")

    # Boxed SEVIRI filename with YYYYMMDDHHMMSS and optional fractions.
    match = re.search(
        r"-(\d{14})(?:\.(\d+))?Z-",
        name
    )

    if match:
        timestamp = pd.to_datetime(
            match.group(1),
            format="%Y%m%d%H%M%S",
            utc=True
        )

        fraction = match.group(2)

        if fraction:
            timestamp += pd.to_timedelta(
                float("0." + fraction),
                unit="s"
            )

        timestamp = timestamp.tz_convert(None)

        return np.datetime64(timestamp.to_datetime64(), "ns")

    return None


def get_timestamp(ds, path):
    """
    Prefer acquisition-time metadata.
    Fall back to the filename if metadata is unavailable.
    """

    possible_attributes = [
        "time_coverage_start",
        "start_time",
        "sensing_start",
        "nominal_product_time",
    ]

    for attribute in possible_attributes:
        value = ds.attrs.get(attribute)

        timestamp = parse_timestamp(value)

        if timestamp is not None:
            return timestamp

    timestamp = timestamp_from_filename(path)

    if timestamp is not None:
        return timestamp

    raise ValueError(
        "Could not determine acquisition timestamp "
        "from NetCDF metadata or filename."
    )


def remove_single_scene_time_dimension(ds):
    """
    Ensure that each input file represents one scene.

    A singleton time dimension is removed before assigning our
    standardised timestamp.
    """

    if "time" in ds.dims:

        if ds.sizes["time"] != 1:
            raise ValueError(
                f"Expected one scene per file, but found "
                f"{ds.sizes['time']} time entries."
            )

        ds = ds.isel(time=0, drop=True)

    elif "time" in ds.coords:

        ds = ds.drop_vars("time")

    return ds


def standardise(ds, timestamp):
    """Rename available source channels to standard BT channel names."""

    output = {}

    for source_name, channel_name in CHANNEL_MAP.items():

        output_name = "BT_" + channel_name

        # The first matching alias wins.
        # This prevents two aliases from overwriting the same channel.
        if (
            source_name in ds.data_vars
            and output_name not in output
        ):
            output[output_name] = ds[source_name]

    if not output:
        raise RuntimeError(
            "No recognised SEVIRI channels found. "
            f"Available variables: {list(ds.data_vars)}"
        )

    result = xr.Dataset(output)

    # Every file is assigned one explicit timestamp with ns precision.
    result = result.expand_dims(
        time=[np.datetime64(timestamp, "ns")]
    )

    return result


def derived(ds):
    """Calculate brightness-temperature differences and cooling features."""

    def channel(name):
        variable = "BT_" + name

        if variable in ds:
            return ds[variable]

        return None

    # Water vapour difference.
    if channel("WV062") is not None and channel("WV073") is not None:
        ds["BTD_62_73"] = channel("WV062") - channel("WV073")

    # Cloud-top phase / cloud-top temperature differences.
    if channel("IR087") is not None and channel("IR108") is not None:
        ds["BTD_87_108"] = channel("IR087") - channel("IR108")

    if channel("IR108") is not None and channel("IR120") is not None:
        ds["BTD_108_120"] = channel("IR108") - channel("IR120")

    # This difference is calculated here but is NOT yet day/night masked.
    # Apply a daytime mask using solar zenith information before treating
    # it as a daytime-only feature.
    if channel("IR039") is not None and channel("IR108") is not None:
        ds["BTD_39_108"] = channel("IR039") - channel("IR108")

    # Cooling features.
    if channel("IR108") is not None:

        bt = channel("IR108")
        times = ds["time"].values.astype("datetime64[ns]")

        # Positive values indicate cooling:
        # previous BT - current BT.
        valid_15 = np.zeros(len(times), dtype=bool)

        if len(times) >= 2:
            valid_15[1:] = (
                np.diff(times) == np.timedelta64(15, "m")
            )

        valid_15 = xr.DataArray(
            valid_15,
            dims=["time"],
            coords={"time": ds["time"]}
        )

        ds["d_BT108_15min"] = (
            bt.shift(time=1) - bt
        ).where(valid_15)

        valid_30 = np.zeros(len(times), dtype=bool)

        if len(times) >= 3:
            valid_30[2:] = (
                times[2:] - times[:-2]
                == np.timedelta64(30, "m")
            )

        valid_30 = xr.DataArray(
            valid_30,
            dims=["time"],
            coords={"time": ds["time"]}
        )

        ds["d_BT108_30min"] = (
            bt.shift(time=2) - bt
        ).where(valid_30)

    return ds


def collect_files():
    """
    Use only the boxed SEVIRI dataset.

    The tailored files have a different spatial grid and must not
    be concatenated with the boxed files without regridding.
    """
    files = sorted(
        Path(SEVIRI_BOX).rglob("*.nc")
    )

    return files


def main():

    files = collect_files()

    if not files:
        sys.exit(
            "No boxed SEVIRI files found. "
            "Check SEVIRI_BOX in config.py."
        )

    print(f"Found {len(files)} boxed SEVIRI files.")

    # ---------------------------------------------------------
    # STEP 1: Read timestamps and build a chronological index.
    # Only metadata is read at this stage.
    # ---------------------------------------------------------

    records = []
    skipped = 0

    for i, filepath in enumerate(files, start=1):

        try:
            with open_any(filepath) as ds:
                timestamp = get_timestamp(ds, filepath)

            records.append((timestamp, filepath))

        except Exception as error:
            skipped += 1
            print(f"SKIP {filepath.name}: {error}")

        if i % 200 == 0:
            print(f"Indexed {i}/{len(files)} files.")

    # Sort chronologically.
    records.sort(key=lambda item: item[0])

    # Remove duplicate acquisition timestamps.
    unique_records = []
    seen_times = set()

    for timestamp, filepath in records:

        key = str(timestamp)

        if key not in seen_times:
            unique_records.append((timestamp, filepath))
            seen_times.add(key)

    records = unique_records

    if not records:
        raise RuntimeError("No valid SEVIRI timestamps found.")

    print(f"\nValid scenes: {len(records)}")
    print(f"Skipped during indexing: {skipped}")

    # ---------------------------------------------------------
    # STEP 2: Group scenes by UTC day.
    # ---------------------------------------------------------

    daily_indices = {}

    for index, (timestamp, filepath) in enumerate(records):

        day = np.datetime_as_string(
            timestamp,
            unit="D"
        )

        daily_indices.setdefault(day, []).append(index)

    output_directory = Path(SEVIRI_FEAT_DIR)
    output_directory.mkdir(parents=True, exist_ok=True)

    print(f"Processing {len(daily_indices)} days.")

    # ---------------------------------------------------------
    # STEP 3: Process one day at a time.
    # Include two preceding scenes for cooling calculations.
    # ---------------------------------------------------------

    for day, indices in sorted(daily_indices.items()):

        print(f"\nProcessing {day}...")

        first_index = indices[0]
        last_index = indices[-1]

        # Include the two preceding scenes so that the first
        # scenes of this day can have 15- and 30-min features.
        batch_start = max(0, first_index - 2)
        batch_end = last_index + 1

        batch_records = records[batch_start:batch_end]

        parts = []

        for timestamp, filepath in batch_records:

            try:
                with open_any(filepath) as raw_ds:

                    scene_ds = remove_single_scene_time_dimension(
                        raw_ds
                    )

                    standardised = standardise(
                        scene_ds,
                        timestamp
                    )

                    # Load this scene before closing the source file.
                    parts.append(standardised.load())

            except Exception as error:
                raise RuntimeError(
                    f"Failed while loading {filepath.name}: {error}"
                ) from error

        if not parts:
            print(f"No scenes available for {day}. Skipping.")
            continue

        # Combine only this day's scenes plus two preceding scenes.
        full = xr.concat(
            parts,
            dim="time",
            join="exact",
            coords="minimal",
            compat="override"
        )

        full = full.sortby("time")

        # Calculate derived features while the preceding scenes
        # are still available.
        full = derived(full)

        # Remove the preceding scenes from the output.
        # They were included only to calculate cooling features.
        offset = first_index - batch_start

        daily = full.isel(
            time=slice(offset, None)
        )

        output_file = (
            output_directory / f"seviri_{day}.nc"
        )

        encoding = {
            variable: {
                "zlib": True,
                "complevel": 4
            }
            for variable in daily.data_vars
        }

        daily.to_netcdf(
            output_file,
            encoding=encoding
        )

        print(
            f"Written: {output_file.name} | "
            f"{daily.sizes['time']} scenes"
        )

        # Release memory before processing the next day.
        del parts
        del full
        del daily

    print("\nSEVIRI feature extraction completed.")
    print(f"Output directory: {output_directory}")


if __name__ == "__main__":
    main()


if __name__ == "__main__":
    main()