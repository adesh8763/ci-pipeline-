"""Step 0: inventory every data folder (file counts, extensions, sizes, time span, variables).
Run this first and send me the output so the loaders in the next scripts can be matched to your exact files.

    python 00_inventory.py
"""
import collections
from config import *


def human(n):
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} PB"


def scan(folder):
    exts, size, files = collections.Counter(), 0, []
    for p in sorted(folder.rglob("*")):
        if p.is_file():
            exts[p.suffix.lower() or "(none)"] += 1
            size += p.stat().st_size
            files.append(p)
    print(f"\n=== {folder.relative_to(ROOT)} ===")
    print(f"files: {len(files)}   size: {human(size)}   types: {dict(exts)}")
    for p in files[:3] + (["..."] if len(files) > 6 else []) + files[-3:]:
        print("   ", p.name if p != "..." else "...")
    return files


def peek_netcdf(path):
    try:
        import xarray as xr
        try:
            ds_ctx = xr.open_dataset(path)
        except Exception:
            ds_ctx = xr.open_dataset(path, group="Grid")   # IMERG HDF5 keeps its data in /Grid
        with ds_ctx as ds:
            print(f"  [{path.name}] dims={dict(ds.sizes)}")
            print(f"  vars={list(ds.data_vars)[:15]}")
            for k in ("time", "valid_time", "t"):
                if k in ds.coords:
                    t = ds[k].values
                    print(f"  {k}: {t.min()} -> {t.max()} (n={t.size})")
                    break
    except Exception as e:
        print(f"  could not open {path.name} with xarray: {e}")


def peek_radar(path):
    try:
        import pyart
        r = pyart.io.read(str(path))
        print(f"  [{path.name}] sweeps={r.nsweeps} rays={r.nrays} gates={r.ngates} fields={list(r.fields)}")
        print(f"  start={r.time['units']}  lat/lon={r.latitude['data'][0]:.3f},{r.longitude['data'][0]:.3f}")
    except Exception as e:
        print(f"  pyart could not read {path.name}: {e}")


if __name__ == "__main__":
    for d in (ERA5_DIR, IMERG_DIR, RADAR_DIR, SEVIRI_DIR, SEVIRI_BOX):
        if not d.exists():
            print(f"\n!! missing: {d}")
            continue
        files = scan(d)
        if not files:
            continue
        f0 = files[0]
        if f0.suffix.lower() in (".nc", ".nc4", ".h5", ".hdf5"):
            peek_netcdf(f0)
        elif d == RADAR_DIR:
            peek_radar(f0)
    print("\nlogs:", sorted(p.name for p in LOGS.glob("*"))[:10])
