
#!/usr/bin/env python3
"""
Step 2: NPOL Cartesian reflectivity processing.

Reads gridded NPOL reflectivity products directly from:
    data/raw/radar_npol/*_gridded.tar

Processes files ending with:
    _cart_2.0kmdz.dat.gz

Each reflectivity scan contains:
    - A timestamp
    - Grid dimensions: nz, ny, nx
    - Vertical levels in km
    - Reflectivity values

Writes one NetCDF file per scan to:
    data/interim/radar_grids/

Output variables:
    dbz3d(z, y, x): 3D reflectivity
    cmax(y, x):     Maximum reflectivity over vertical levels

IMPORTANT:
    The horizontal geographic coordinates/projection have not yet
    been established. Therefore x and y are stored as grid indices.
    Do not spatially align these grids with SEVIRI until the radar
    geographic mapping is established.
"""

from __future__ import annotations

import argparse
import gzip
import io
import logging
import tarfile

from datetime import datetime
from pathlib import Path

import numpy as np
import xarray as xr

from config import RADAR_DIR, RADAR_GRID_DIR


# ============================================================
# CONFIGURATION
# ============================================================

REFLECTIVITY_SUFFIX = "_cart_2.0kmdz.dat.gz"

# Provisional missing-value handling.
# Values <= -80 dBZ are treated as missing.
MISSING_THRESHOLD = -80.0

COMPRESSION_LEVEL = 3

LOG_DIR = RADAR_GRID_DIR.parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

RADAR_GRID_DIR.mkdir(parents=True, exist_ok=True)

LOG_FILE = LOG_DIR / "02_radar_grid.log"


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger(__name__)


# ============================================================
# READ ONE REFLECTIVITY FILE
# ============================================================

def read_reflectivity(member_stream):
    """
    Read one compressed NPOL Cartesian reflectivity file.

    Expected header:

        MM DD YYYY HH MM
        nz ny nx
        z1 z2 z3 ...

    Returns
    -------
    timestamp : datetime
    dbz3d : numpy.ndarray
        Shape (nz, ny, nx).
    z_levels : numpy.ndarray
        Vertical levels in km.
    """

    # Open the gzip stream without extracting the archive member.
    with gzip.GzipFile(fileobj=member_stream, mode="rb") as gz:
        with io.TextIOWrapper(gz, encoding="ascii") as text:

            # ------------------------------------------------
            # Header line 1: date and time
            # ------------------------------------------------

            date_line = text.readline().strip()

            if not date_line:
                raise ValueError("Empty timestamp header")

            timestamp = datetime.strptime(
                date_line,
                "%m %d %Y %H %M"
            )

            # ------------------------------------------------
            # Header line 2: dimensions
            # ------------------------------------------------

            dimension_line = text.readline().strip()

            dimensions = [
                int(value)
                for value in dimension_line.split()
            ]

            if len(dimensions) != 3:
                raise ValueError(
                    f"Expected 3 grid dimensions, got {dimensions}"
                )

            nz, ny, nx = dimensions

            if min(nz, ny, nx) <= 0:
                raise ValueError(
                    f"Invalid grid dimensions: {dimensions}"
                )

            # ------------------------------------------------
            # Header line 3: vertical levels
            # ------------------------------------------------

            height_line = text.readline().strip()

            z_levels = np.fromstring(
                height_line,
                sep=" ",
                dtype=np.float32
            )

            if len(z_levels) != nz:
                raise ValueError(
                    f"Expected {nz} vertical levels, "
                    f"found {len(z_levels)}"
                )

            # ------------------------------------------------
            # Remaining content: reflectivity values
            # ------------------------------------------------

            data_text = text.read()

    values = np.fromstring(
        data_text,
        sep=" ",
        dtype=np.float32
    )

    expected_values = nz * ny * nx

    if values.size != expected_values:
        raise ValueError(
            f"Incorrect number of reflectivity values. "
            f"Expected {expected_values}, got {values.size}"
        )

    # Reshape into vertical, y, x dimensions.
    dbz3d = values.reshape((nz, ny, nx))

    # Convert provisional missing-value markers to NaN.
    dbz3d[dbz3d <= MISSING_THRESHOLD] = np.nan

    return timestamp, dbz3d, z_levels


# ============================================================
# CALCULATE COLUMN MAXIMUM
# ============================================================

def calculate_column_max(dbz3d):
    """
    Calculate maximum reflectivity through the vertical column.

    Input:
        dbz3d: (z, y, x)

    Output:
        cmax: (y, x)

    Columns containing only missing values remain NaN.
    """

    valid = np.isfinite(dbz3d)

    maximum = np.max(
        np.where(valid, dbz3d, -np.inf),
        axis=0
    )

    maximum[~np.any(valid, axis=0)] = np.nan

    return maximum.astype(np.float32)


# ============================================================
# SAVE NETCDF
# ============================================================

def save_netcdf(
    timestamp,
    dbz3d,
    cmax,
    z_levels,
    source_name,
    overwrite=False,
):
    """
    Save one radar scan as a NetCDF file.
    """

    output_name = timestamp.strftime("%Y%m%d_%H%M%S.nc")
    output_path = RADAR_GRID_DIR / output_name

    if output_path.exists() and not overwrite:
        return output_path, False

    nz, ny, nx = dbz3d.shape

    ds = xr.Dataset(
        data_vars={
            "dbz3d": (
                ("z", "y", "x"),
                dbz3d.astype(np.float32),
                {
                    "long_name": "3D radar reflectivity",
                    "units": "dBZ",
                },
            ),

            "cmax": (
                ("y", "x"),
                cmax.astype(np.float32),
                {
                    "long_name": "Column maximum reflectivity",
                    "units": "dBZ",
                },
            ),
        },

        coords={
            "time": np.datetime64(timestamp),
            "z": (
                "z",
                z_levels.astype(np.float32),
                {
                    "long_name": "Vertical height",
                    "units": "km",
                },
            ),
            "y": np.arange(ny, dtype=np.int32),
            "x": np.arange(nx, dtype=np.int32),
        },

        attrs={
            "title": "NASA NAMMA NPOL Cartesian Reflectivity",
            "source_file": source_name,
            "processing": "Direct processing of gridded NPOL archive",
            "horizontal_coordinates": (
                "Grid indices only; geographic mapping unresolved"
            ),
            "missing_value_rule": (
                f"Values <= {MISSING_THRESHOLD} dBZ converted to NaN"
            ),
        },
    )

    encoding = {
        "dbz3d": {
            "zlib": True,
            "complevel": COMPRESSION_LEVEL,
            "dtype": "float32",
            "_FillValue": np.float32(np.nan),
        },
        "cmax": {
            "zlib": True,
            "complevel": COMPRESSION_LEVEL,
            "dtype": "float32",
            "_FillValue": np.float32(np.nan),
        },
    }

    try:
        ds.to_netcdf(
            output_path,
            engine="netcdf4",
            encoding=encoding,
        )
    finally:
        ds.close()

    return output_path, True


# ============================================================
# PROCESS ONE TAR ARCHIVE
# ============================================================

def process_archive(
    archive_path,
    limit_scans=None,
    overwrite=False,
):
    """
    Process reflectivity scans from one TAR archive.

    limit_scans:
        Maximum number of reflectivity scans to examine
        in this archive. None means all scans.
    """

    examined = 0
    processed = 0
    skipped = 0
    failed = 0

    logger.info("Opening archive: %s", archive_path.name)

    try:
        with tarfile.open(archive_path, mode="r:*") as archive:

            # IMPORTANT:
            # Sort using member.name. TarInfo objects themselves
            # cannot be compared directly by Python.
            members = sorted(
                (
                    member
                    for member in archive.getmembers()
                    if member.isfile()
                    and member.name.endswith(REFLECTIVITY_SUFFIX)
                ),
                key=lambda member: member.name,
            )

            logger.info(
                "Reflectivity scans found: %d",
                len(members)
            )

            if limit_scans is not None:
                members = members[:limit_scans]

            for member in members:

                examined += 1

                logger.info(
                    "Processing scan %d: %s",
                    examined,
                    member.name,
                )

                try:
                    member_stream = archive.extractfile(member)

                    if member_stream is None:
                        raise IOError(
                            "Could not read archive member"
                        )

                    with member_stream:

                        timestamp, dbz3d, z_levels = (
                            read_reflectivity(member_stream)
                        )

                    cmax = calculate_column_max(dbz3d)

                    output_path, was_written = save_netcdf(
                        timestamp=timestamp,
                        dbz3d=dbz3d,
                        cmax=cmax,
                        z_levels=z_levels,
                        source_name=member.name,
                        overwrite=overwrite,
                    )

                    if was_written:
                        processed += 1

                        logger.info(
                            "Saved: %s | shape=%s",
                            output_path.name,
                            dbz3d.shape,
                        )

                    else:
                        skipped += 1

                        logger.info(
                            "Already exists, skipped: %s",
                            output_path.name,
                        )

                except Exception as exc:
                    failed += 1

                    logger.exception(
                        "Failed scan %s: %s",
                        member.name,
                        exc,
                    )

    except Exception as exc:
        logger.exception(
            "Could not process archive %s: %s",
            archive_path.name,
            exc,
        )

        # Archive-level failure.
        failed += 1

    return examined, processed, skipped, failed


# ============================================================
# MAIN
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description="Process NPOL Cartesian reflectivity archives"
    )

    parser.add_argument(
        "--limit-scans",
        type=int,
        default=None,
        help=(
            "Maximum scans to process per archive. "
            "Default: all scans."
        ),
    )

    parser.add_argument(
        "--limit-archives",
        type=int,
        default=None,
        help=(
            "Maximum number of archives to process. "
            "Default: all archives."
        ),
    )

    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing NetCDF outputs.",
    )

    args = parser.parse_args()

    if args.limit_scans is not None and args.limit_scans <= 0:
        parser.error("--limit-scans must be greater than zero")

    if args.limit_archives is not None and args.limit_archives <= 0:
        parser.error("--limit-archives must be greater than zero")

    print("=" * 60)
    print("NPOL CARTESIAN REFLECTIVITY PROCESSING")
    print("=" * 60)

    archive_paths = sorted(
        RADAR_DIR.glob("*_gridded.tar")
    )

    if not archive_paths:
        logger.error(
            "No gridded TAR archives found in %s",
            RADAR_DIR,
        )
        return

    if args.limit_archives is not None:
        archive_paths = archive_paths[:args.limit_archives]

    print(f"Archives found: {len(archive_paths)}")
    print(f"Output directory: {RADAR_GRID_DIR}")
    print()

    total_examined = 0
    total_processed = 0
    total_skipped = 0
    total_failed = 0

    for archive_path in archive_paths:

        print(f"Archive: {archive_path.name}")

        examined, processed, skipped, failed = process_archive(
            archive_path,
            limit_scans=args.limit_scans,
            overwrite=args.overwrite,
        )

        total_examined += examined
        total_processed += processed
        total_skipped += skipped
        total_failed += failed

        print(
            f"  Examined: {examined} | "
            f"Processed: {processed} | "
            f"Skipped: {skipped} | "
            f"Failed: {failed}"
        )
        print()

    print("=" * 60)
    print("PROCESSING SUMMARY")
    print("=" * 60)

    print(f"Archives processed: {len(archive_paths)}")
    print(f"Scans examined:     {total_examined}")
    print(f"Scans processed:    {total_processed}")
    print(f"Scans skipped:      {total_skipped}")
    print(f"Scans failed:       {total_failed}")

    print("=" * 60)

    logger.info(
        "Completed: examined=%d processed=%d skipped=%d failed=%d",
        total_examined,
        total_processed,
        total_skipped,
        total_failed,
    )


if __name__ == "__main__":
    main()
