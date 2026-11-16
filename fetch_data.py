#!/usr/bin/env python
"""Fetch the finalised dataset set for the True-CI study. RUN ON YOUR OWN MACHINE.

SELECTION (see DATASETS_FINAL.md)
  Radar      : NAMMA NASA NPOL S-band radar, Kawsara, Senegal (GHRC DAAC)
  Satellite  : MSG SEVIRI High Rate L1.5, 0 degree (EUMETSAT Data Store)
  Atmosphere : ERA5 hourly pressure + single levels (Copernicus CDS)
  Optional   : IMERG Final V07 half-hourly
  Default period: 2006-08-19 .. 2006-09-30 (NPOL's full operating period)

Setup
  pip install cdsapi earthaccess eumdac            # plus satpy pyresample netCDF4 for --extract
  CDS       : account + ERA5 licence accepted, key in ~/.cdsapirc
  Earthdata : earthaccess.login() prompts once
  EUMETSAT  : EUMETSAT_CONSUMER_KEY / EUMETSAT_CONSUMER_SECRET

SIZE-CONTROL FLAGS
  --plan                 print the selection and size estimates; no network
  --pilot                first 5 days only (about 1/9 of everything): measure real sizes first
  --start/--end DATE     override the period (YYYY-MM-DD)
  --channels LIST        SEVIRI channels, comma separated (default 7; IR_108,WV_062,IR_039 is ~3)
  --step N               keep every Nth SEVIRI slot (1 = every 15 min, the full-quality default;
                         4 = hourly, which weakens CI timing: avoid for the main analysis)
  --tailor               SEVIRI: server-side region/channel subset via Data Tailor (smallest transfer)
  --extract              SEVIRI: download one full-disk file at a time, crop the box, DELETE the file
                         (disk stays tiny, but ~250 MB per slot is transferred)
  --max-gb G             stop before the data folder would exceed G gigabytes
  --min-free-gb G        stop if free disk falls below G gigabytes (default 20)
  --limit N              SEVIRI/IMERG: handle only the first N items (smoke test)
  --dry-run              print requests only
Completed SEVIRI slots are logged in data/logs/seviri_done.txt, so a stopped run resumes.

STATUS: not run against live services. Size numbers are estimates (NPOL's 29 GB is documented).
Items marked UNVERIFIED must be checked on first use.
"""
import argparse, datetime as dt, json, os, shutil, tempfile, zipfile

START = dt.datetime(2006, 8, 19, 0, 0)
END = dt.datetime(2006, 9, 30, 23, 45)
RADAR_BOX = dict(N=17.1, S=12.2, W=-19.54, E=-14.65)   # NPOL catalogue box; exact site UNVERIFIED
PAD = 2.0
BOX = dict(N=RADAR_BOX["N"] + PAD, S=RADAR_BOX["S"] - PAD,
           W=RADAR_BOX["W"] - PAD, E=RADAR_BOX["E"] + PAD)
OUT = "data/raw"
EXTRACT_DIR = "data/interim/seviri_box"
LOG_DIR = "data/logs"
#ALL_CHANNELS = ["IR_108", "WV_062", "WV_073", "IR_039", "IR_120", "IR_087", "VIS006"]
ALL_CHANNELS = [
    "channel_9",   # IR_108
    "channel_5",   # WV_062
    "channel_6",   # WV_073
    "channel_4",   # IR_039
    "channel_10",  # IR_120
    "channel_7",   # IR_087
    "channel_1",   # VIS006
]
GRID_DEG = 0.03                    # ~3 km extract grid (SEVIRI native sampling ~3 km at sub-satellite point)
# per-slot size ASSUMPTIONS (UNVERIFIED): replace with measured values after the pilot
FULL_DISK_MB, TAILORED_MB_7CH = 250.0, 1.5


def dir_gb(path):
    tot = 0
    for r, _, fs in os.walk(path):
        for f in fs:
            try:
                tot += os.path.getsize(os.path.join(r, f))
            except OSError:
                pass
    return tot / 1e9


def guard(args, need_gb=0.0):
    """Stop (raise) if the free-disk floor or the data-folder cap would be violated."""
    os.makedirs("data", exist_ok=True)
    free = shutil.disk_usage("data").free / 1e9
    if free - need_gb < args.min_free_gb:
        raise SystemExit(f"STOP: free disk {free:.1f} GB minus {need_gb:.2f} GB needed would fall below "
                         f"--min-free-gb {args.min_free_gb}")
    if args.max_gb and dir_gb("data") + need_gb > args.max_gb:
        raise SystemExit(f"STOP: data/ would exceed --max-gb {args.max_gb}")


def n_slots(args):
    return int(((END - START).total_seconds() / 900 + 1) // args.step)


def plan(args):
    ns, nc = n_slots(args), len(args.channels)
    days = (END.date() - START.date()).days + 1
    tailored = ns * TAILORED_MB_7CH * nc / 7 / 1000
    full = ns * FULL_DISK_MB / 1000
    print(json.dumps(dict(start=START.isoformat(), end=END.isoformat(), box_radar=RADAR_BOX,
                          box_padded=BOX, channels=args.channels, step=args.step), indent=2))
    print(f"\n{days} days, {ns} SEVIRI slots after --step {args.step}")
    print(f"SEVIRI via --tailor      : ~{tailored:.1f} GB transferred and stored (estimate)")
    print(f"SEVIRI via --extract     : ~{full:.0f} GB transferred, ~{ns * 0.0015 * nc / 7:.1f} GB stored (estimate)")
    print(f"SEVIRI full-disk, kept   : ~{full:.0f} GB stored (do not do this)")
    print(f"NPOL raw                 : ~29 GB for the whole campaign (documented; scales with days)")
    print(f"ERA5                     : ~{0.3 * days / 43:.2f} GB (estimate)")
    print(f"IMERG (optional)         : ~{days * 48 * 6 / 1000:.1f} GB (estimate)")


def month_days():
    d = (START - dt.timedelta(days=1)).date()
    cur = {}
    while d <= END.date():
        cur.setdefault((d.year, d.month), []).append(f"{d.day:02d}")
        d += dt.timedelta(days=1)
    for (y, m), days in cur.items():
        yield y, f"{m:02d}", days


# --- Radar -------------------------------------------------------------------------------
def radar(args):
    print("RADAR NAMMA NPOL", START.date(), END.date(), "(~29 GB for the full campaign)")
    if args.dry_run:
        return
    import earthaccess
    earthaccess.login()
    res = earthaccess.search_data(short_name="namnpol",      # short name guessed from catalogue id: UNVERIFIED
                                  temporal=(START.isoformat(), END.isoformat()))
    print(len(res), "granules found")
    if not res:
        print("No granules via CMR. Use the data link on https://ghrc.nsstc.nasa.gov/pub/doc/namma/namnpol/"
              "namnpol_dataset.html and download the daily folders (e.g. 060831/) manually.")
        return
    res = res[:args.limit] if args.limit else res
    guard(args, 0.0)
    os.makedirs(f"{OUT}/radar_npol", exist_ok=True)
    earthaccess.download(res, f"{OUT}/radar_npol")


# --- ERA5 --------------------------------------------------------------------------------
def era5(args):
    area = [BOX["N"], BOX["W"], BOX["S"], BOX["E"]]
    hours = [f"{h:02d}:00" for h in range(24)]
    pl = dict(product_type="reanalysis", data_format="grib", time=hours, area=area,
              variable=["temperature", "specific_humidity", "u_component_of_wind",
                        "v_component_of_wind", "vertical_velocity", "geopotential"],
              pressure_level=["1000", "925", "850", "700", "600", "500", "400", "300", "200"])
    sl = dict(product_type="reanalysis", data_format="grib", time=hours, area=area,
              variable=["convective_available_potential_energy", "convective_inhibition",
                        "total_column_water_vapour", "2m_temperature", "2m_dewpoint_temperature",
                        "surface_pressure", "10m_u_component_of_wind", "10m_v_component_of_wind",
                        "boundary_layer_height"])
    c = None
    for y, m, days in month_days():
        for name, ds, req in (("pressure_levels", "reanalysis-era5-pressure-levels", pl),
                              ("single_levels", "reanalysis-era5-single-levels", sl)):
            target = f"{OUT}/era5/{name}/{name}_{y}{m}.grib"
            print("ERA5", ds, y, m, f"{len(days)} days ->", target)
            if args.dry_run:
                continue
            guard(args, 0.2)
            if c is None:
                import cdsapi
                #import os

                url = os.getenv("CDSAPI_URL")
                key = os.getenv("CDSAPI_KEY")

                c = cdsapi.Client(url=url, key=key)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            if not os.path.exists(target):
                c.retrieve(ds, dict(req, year=str(y), month=m, day=days), target)


# --- IMERG (optional) --------------------------------------------------------------------

def imerg(args):
    import os
    import earthaccess

    out_dir = f"{OUT}/imerg"

    print(
        "IMERG GPM_3IMERGHH v07",
        START.date(),
        END.date(),
        f"(~{((END - START).days + 1) * 48 * 6 / 1000:.0f} GB est.)",
    )

    if args.dry_run:
        return

    # Authenticate with NASA Earthdata.
    earthaccess.login()

    # Find granules matching the study period and region.
    res = earthaccess.search_data(
        short_name="GPM_3IMERGHH",
        version="07",
        temporal=(START.isoformat(), END.isoformat()),
        bounding_box=(
            BOX["W"],
            BOX["S"],
            BOX["E"],
            BOX["N"],
        ),
    )

    # Apply an optional limit, if supplied.
    if args.limit:
        res = res[:args.limit]

    total = len(res)
    print(f"{total} granules found")

    if total == 0:
        print("No IMERG granules found. Check the dates, region, and Earthdata access.")
        return

    # Preserve the existing script's download-size guard.
    guard(args, total * 0.006)

    os.makedirs(out_dir, exist_ok=True)

    # Download manageable batches instead of submitting every granule at once.
    batch_size = 48
    threads = 2

    for start in range(0, total, batch_size):
        batch = res[start:start + batch_size]
        first = start + 1
        last = start + len(batch)

        print(
            f"\nDownloading granules {first}-{last} of {total}...",
            flush=True,
        )

        downloaded = earthaccess.download(
            batch,
            out_dir,
            threads=threads,
            show_progress=True,
        )

        print(
            f"Batch {first}-{last} finished. "
            f"Download results: {len(downloaded)}",
            flush=True,
        )

    print(f"\nIMERG download loop completed. Output directory: {out_dir}")



# --- SEVIRI ------------------------------------------------------------------------------
def extract_box(nat_path, out_nc, channels):
    """Crop one native SEVIRI file to BOX on a regular lat/lon grid and write netCDF (UNVERIFIED path)."""
    from satpy import Scene
    from pyresample.geometry import AreaDefinition
    w = round((BOX["E"] - BOX["W"]) / GRID_DEG)
    h = round((BOX["N"] - BOX["S"]) / GRID_DEG)
    area = AreaDefinition("box", "box", "box", {"proj": "longlat", "datum": "WGS84"}, w, h,
                          (BOX["W"], BOX["S"], BOX["E"], BOX["N"]))
    scn = Scene(filenames=[nat_path], reader="seviri_l1b_native")
    ir = [c for c in channels if not c.startswith("VIS") and c != "HRV"]
    vis = [c for c in channels if c.startswith("VIS")]
    if ir:
        scn.load(ir, calibration="brightness_temperature")
    if vis:
        scn.load(vis, calibration="reflectance")
    scn.resample(area, resampler="nearest").save_datasets(writer="cf", filename=out_nc)


def seviri(args):
    ns = n_slots(args)
    print("SEVIRI EO:EUM:DAT:MSG:HRSEVIRI", START, END, "step", args.step, "channels", args.channels)
    print(f"  expected slots: {ns}")
    if args.dry_run:
        return
    import eumdac
    tok = eumdac.AccessToken((os.environ["EUMETSAT_CONSUMER_KEY"], os.environ["EUMETSAT_CONSUMER_SECRET"]))
    coll = eumdac.DataStore(tok).get_collection("EO:EUM:DAT:MSG:HRSEVIRI")
    prods = sorted(coll.search(dtstart=START, dtend=END), key=str)
    print(len(prods), "products found (fewer than expected = archive gaps or not online for these dates)")
    if not prods:
        print("Nothing online for these dates. Order it from the EUMETSAT Data Centre via the product page.")
        return
    prods = prods[::args.step]
    prods = prods[:args.limit] if args.limit else prods
    os.makedirs(LOG_DIR, exist_ok=True)
    log = f"{LOG_DIR}/seviri_done.txt"
    done = set(open(log).read().split()) if os.path.exists(log) else set()
    todo = [p for p in prods if str(p) not in done]
    print(len(todo), "to do,", len(prods) - len(todo), "already done")

    if args.tailor:
        #Chain fields are UNVERIFIED; adjust if the service rejects them.
        dtl = eumdac.DataTailor(tok)
        chain = eumdac.tailor_models.Chain(
            product="HRSEVIRI", format="netcdf4", projection="geographic",
            roi={"NSWE": [BOX["N"], BOX["S"], BOX["W"], BOX["E"]]}, filter={"bands": args.channels})
        for p in todo:
            guard(args, 0.01)
            print("customisation", dtl.new_customisation(p, chain), "submitted for", p)
        print("Poll and download the results with the eumdac API/CLI when finished.")
        return

    os.makedirs(EXTRACT_DIR, exist_ok=True)
    for p in todo:
        guard(args, 0.3)                                   # one full-disk file at a time
        with tempfile.TemporaryDirectory(dir="data") as tmp:
            zpath = os.path.join(tmp, f"{p}.zip")
            with p.open() as src, open(zpath, "wb") as dst:
                shutil.copyfileobj(src, dst)
            if args.extract:
                with zipfile.ZipFile(zpath) as z:
                    z.extractall(tmp)
                nat = [os.path.join(tmp, n) for n in os.listdir(tmp) if n.endswith(".nat")]
                if not nat:
                    print("no .nat in", p, "- skipped"); continue
                extract_box(nat[0], f"{EXTRACT_DIR}/{p}.nc", args.channels)
            else:
                os.makedirs(f"{OUT}/seviri", exist_ok=True)
                shutil.move(zpath, f"{OUT}/seviri/{p}.zip")
        with open(log, "a") as f:
            f.write(str(p) + "\n")
        print("done", p)


def main():
    global START, END
    a = argparse.ArgumentParser(description="True-CI data fetcher", formatter_class=argparse.RawTextHelpFormatter)
    a.add_argument("--only", choices=["radar", "era5", "imerg", "seviri"])
    a.add_argument("--start"); a.add_argument("--end")
    a.add_argument("--pilot", action="store_true")
    a.add_argument("--channels", default=",".join(ALL_CHANNELS))
    a.add_argument("--step", type=int, default=1)
    a.add_argument("--tailor", action="store_true")
    a.add_argument("--extract", action="store_true")
    a.add_argument("--max-gb", type=float, default=0.0)
    a.add_argument("--min-free-gb", type=float, default=20.0)
    a.add_argument("--limit", type=int, default=0)
    a.add_argument("--dry-run", action="store_true")
    a.add_argument("--plan", action="store_true")
    x = a.parse_args()
    x.channels = [c.strip() for c in x.channels.split(",") if c.strip()]
    bad = [c for c in x.channels if c not in ALL_CHANNELS]
    if bad:
        raise SystemExit(f"unknown channels {bad}; choose from {ALL_CHANNELS}")
    if x.start:
        START = dt.datetime.fromisoformat(x.start)
    if x.end:
        END = dt.datetime.fromisoformat(x.end).replace(hour=23, minute=45)
    if x.pilot:
        END = START + dt.timedelta(days=5) - dt.timedelta(minutes=15)
    if x.step < 1:
        raise SystemExit("--step must be >= 1")
    if x.step > 1:
        print(f"WARNING: --step {x.step} keeps every {x.step * 15} min; CI timing at 30-60 min leads is degraded.")
    if x.plan:
        plan(x)
        return
    if x.only in (None, "radar"):
        radar(x)
    if x.only in (None, "era5"):
        era5(x)
    if x.only in (None, "imerg"):
        imerg(x)
    if x.only in (None, "seviri"):
        seviri(x)


if __name__ == "__main__":
    main()




#To download the eumetsat deviri data follow these steps :-
#export EUMETSAT_CONSUMER_KEY="jG0gvjCrzRbGU5N0rBCGO2dvCusa"
#export EUMETSAT_CONSUMER_SECRET="TFSZIVV2_HA0qXbzxPYRdiTE4Xka"
#export EUMETSAT_API_KEY="6df0faeb-575e-3075-9e3c-3e7f614f4368"
#nohup python -u seviri_fetch.py --max-gb 100 --workers 4 > seviri_full.log 2>&1 & tail -f seviri_full.log
