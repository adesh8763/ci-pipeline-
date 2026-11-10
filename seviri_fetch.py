#!/usr/bin/env python
"""Large-volume SEVIRI fetcher: download one full-disk file at a time, crop to the study box, delete the original.

Why: each 2006 MSG1 full-disk file is about 133 MB (observed size listed by the Data Store), so the full
period is about 3,962 files = roughly 530 GB of TRANSFER, but only a few GB are kept on disk.

Features
  * access pre-check: reads 1 MB of one file first and stops at once with instructions if the server says 403
  * resume: finished slots are logged (data/logs/seviri_fetch_done.txt); rerun the same command to continue
  * disk guards: --min-free-gb (stop if free disk is low), --max-gb (cap on stored output)
  * integrity: zip test after each download; retries with back-off for transient errors (never for 403)
  * parallel workers (--workers, default 2), a failure log and a final summary
  * optional thinning (--step) and hour-of-day filter (--hours): both change the study design, so the
    defaults keep every 15-minute slot and every hour

Setup:  pip install eumdac satpy pyresample netCDF4 xarray
        env vars EUMETSAT_CONSUMER_KEY and EUMETSAT_CONSUMER_SECRET

Examples
  python seviri_fetch.py --plan                              # no network: slots, transfer and disk estimates
  python seviri_fetch.py --check-access                      # only the access pre-check
  python seviri_fetch.py --pilot --limit 4                   # smoke test
  python seviri_fetch.py --pilot                             # 5 days
  python seviri_fetch.py --max-gb 100                        # full period; rerun to resume
  python seviri_fetch.py --mode raw --limit 2                # keep the original zips (big!)

STATUS: not run against the live service. The pre-check will stop with a 403 message until the EUMETSAT
account is allowed to download this collection. The satpy cropping path is UNVERIFIED on 2006 files.
"""
import argparse, datetime as dt, os, shutil, sys, tempfile, threading, time, zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed

START = dt.datetime(2006, 8, 19, 0, 0)
END = dt.datetime(2006, 9, 30, 23, 45)
BOX = dict(N=19.1, S=10.2, W=-21.54, E=-12.65)      # NPOL catalogue box + 2 deg; update from the radar header
GRID_DEG = 0.03                                      # ~3 km regular lat/lon grid for the crop
COLLECTION = "EO:EUM:DAT:MSG:HRSEVIRI"
DEFAULT_CHANNELS = ["IR_108", "WV_062", "WV_073", "IR_039", "IR_120", "IR_087", "VIS006"]
FULL_FILE_MB = 133.0                                 # observed: product size 132,959 (KB) in the Data Store
CROPPED_MB_7CH = 1.5                                 # ASSUMPTION; measure after the pilot
OUT_DIR = "data/interim/seviri_box"
RAW_DIR = "data/raw/seviri"
TMP_DIR = "data/tmp_seviri"
LOG_DIR = "data/logs"

lock = threading.Lock()


def parse_hours(s):
    a, b = s.split("-")
    a, b = int(a), int(b)
    if not (0 <= a <= 23 and 0 <= b <= 23 and a <= b):
        raise SystemExit("--hours must look like 0-23 or 6-20 (UTC, inclusive)")
    return a, b


def est_slots(args):
    days = (END.date() - START.date()).days + 1
    h0, h1 = args.hours
    per_day = 96 * (h1 - h0 + 1) / 24
    return int(days * per_day / args.step)


def plan(args):
    n = est_slots(args)
    nch = len(args.channels)
    print(f"period {START} .. {END}  box {BOX}")
    print(f"channels {args.channels}  step {args.step}  hours (UTC) {args.hours[0]}-{args.hours[1]}")
    print(f"about {n} slots (the archive has roughly 4% fewer than nominal)")
    print(f"transfer  : ~{n * FULL_FILE_MB / 1000:.0f} GB  (133 MB per file, observed)")
    print(f"stored    : ~{n * CROPPED_MB_7CH * nch / 7 / 1000:.1f} GB cropped (assumption: {CROPPED_MB_7CH} MB per slot for 7 channels)")
    print(f"scratch   : ~{0.5 * args.workers:.1f} GB at any time (--workers {args.workers})")
    if args.step > 1 or args.hours != (0, 23):
        print("WARNING: thinning slots or hours changes the study design; keep the defaults for the main analysis.")


def token():
    import eumdac
    return eumdac.AccessToken((os.environ["EUMETSAT_CONSUMER_KEY"], os.environ["EUMETSAT_CONSUMER_SECRET"]))


def is_denied(e):
    s = str(e)
    return "403" in s or "Unauthor" in s or "Forbidden" in s


def check_access(coll):
    p = next(iter(coll.search(dtstart=START, dtend=START + dt.timedelta(minutes=30))))
    try:
        with p.open() as s:
            n = len(s.read(1024 * 1024))
        print(f"access OK: read {n} bytes of {p}")
        return True
    except Exception as e:
        print(f"ACCESS CHECK FAILED for {p}: {e}")
        if is_denied(e):
            print("\nYour account is not allowed to download this collection (403). Searching works, downloading does not.\n"
                  "Sign in at https://data.eumetsat.int with the same account, open the product page, accept any\n"
                  "licence/terms prompt and try one download there. If that is refused too, contact EUMETSAT user support\n"
                  "with the product id above. Nothing was downloaded.")
        return False


def extract_box(nat_path, out_nc, channels):
    """Crop one native SEVIRI file to BOX on a regular lat/lon grid and write compressed float32 netCDF (UNVERIFIED)."""
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
    enc = {c: {"zlib": True, "complevel": 4, "dtype": "float32"} for c in channels}
    scn.resample(area, resampler="nearest").save_datasets(writer="cf", filename=out_nc, encoding=enc)


def process(p, args, state):
    """Download, verify, crop and clean up one product. Returns (product, ok, bytes_downloaded, message)."""
    name = str(p)
    for attempt in range(3):
        work = tempfile.mkdtemp(dir=TMP_DIR)
        try:
            with state["lock"]:
                free = shutil.disk_usage("data").free / 1e9
                if free < args.min_free_gb + 0.4:
                    return p, False, 0, "STOP: low disk"
                if args.max_gb and state["stored"] / 1e9 >= args.max_gb:
                    return p, False, 0, "STOP: --max-gb reached"
            zpath = os.path.join(work, name + ".zip")
            with p.open() as src, open(zpath, "wb") as dst:
                shutil.copyfileobj(src, dst, length=1024 * 1024)
            nbytes = os.path.getsize(zpath)
            if zipfile.is_zipfile(zpath):
                with zipfile.ZipFile(zpath) as z:
                    if z.testzip() is not None:
                        raise IOError("corrupt zip")
                    if args.mode == "raw":
                        os.makedirs(RAW_DIR, exist_ok=True)
                        shutil.move(zpath, os.path.join(RAW_DIR, name + ".zip"))
                        with state["lock"]:
                            state["stored"] += nbytes
                        return p, True, nbytes, "raw kept"
                    z.extractall(work)
                nat = [os.path.join(r, f) for r, _, fs in os.walk(work) for f in fs if f.lower().endswith(".nat")]
            else:
                nat = [zpath]
                if args.mode == "raw":
                    os.makedirs(RAW_DIR, exist_ok=True)
                    shutil.move(zpath, os.path.join(RAW_DIR, name + ".nat"))
                    return p, True, nbytes, "raw kept"
            if not nat:
                return p, False, nbytes, "no .nat file in download"
            out = os.path.join(OUT_DIR, name + ".nc")
            extract_box(nat[0], out, args.channels)
            size = os.path.getsize(out)
            if size < 1000:
                raise IOError("output file suspiciously small")
            with state["lock"]:
                state["stored"] += size
            return p, True, nbytes, f"cropped {size / 1e6:.1f} MB"
        except Exception as e:
            if is_denied(e):
                return p, False, 0, f"DENIED: {e}"
            if attempt == 2:
                return p, False, 0, f"failed after 3 tries: {e}"
            time.sleep(5 * 2 ** attempt)
        finally:
            shutil.rmtree(work, ignore_errors=True)
    return p, False, 0, "unknown"


def main():
    global START, END
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    a.add_argument("--start"); a.add_argument("--end")
    a.add_argument("--pilot", action="store_true", help="first 5 days only")
    a.add_argument("--limit", type=int, default=0)
    a.add_argument("--mode", choices=["crop", "raw"], default="crop")
    a.add_argument("--channels", default=",".join(DEFAULT_CHANNELS), help="satpy names, comma separated")
    a.add_argument("--box", nargs=4, type=float, metavar=("N", "S", "W", "E"))
    a.add_argument("--step", type=int, default=1, help="keep every Nth slot (design change if > 1)")
    a.add_argument("--hours", default="0-23", help="UTC hours to keep, e.g. 6-20 (design change if narrowed)")
    a.add_argument("--workers", type=int, default=2)
    a.add_argument("--min-free-gb", type=float, default=20.0)
    a.add_argument("--max-gb", type=float, default=0.0, help="cap on stored output (0 = none)")
    a.add_argument("--plan", action="store_true")
    a.add_argument("--check-access", action="store_true")
    x = a.parse_args()
    x.channels = [c.strip() for c in x.channels.split(",") if c.strip()]
    x.hours = parse_hours(x.hours)
    if x.step < 1 or x.workers < 1:
        raise SystemExit("--step and --workers must be >= 1")
    if x.start:
        START = dt.datetime.fromisoformat(x.start)
    if x.end:
        END = dt.datetime.fromisoformat(x.end).replace(hour=23, minute=45)
    if x.pilot:
        END = START + dt.timedelta(days=5) - dt.timedelta(minutes=15)
    if x.box:
        BOX.update(dict(zip("NSWE", x.box)))
    if x.plan:
        plan(x)
        return

    import eumdac
    coll = eumdac.DataStore(token()).get_collection(COLLECTION)
    if not check_access(coll):
        sys.exit(2)
    if x.check_access:
        return

    prods = sorted(coll.search(dtstart=START, dtend=END), key=str)
    h0, h1 = x.hours
    prods = [p for p in prods if h0 <= p.sensing_start.hour <= h1][::x.step]
    os.makedirs(LOG_DIR, exist_ok=True)
    for d in (OUT_DIR, TMP_DIR):
        os.makedirs(d, exist_ok=True)
    done_f, fail_f = f"{LOG_DIR}/seviri_fetch_done.txt", f"{LOG_DIR}/seviri_fetch_failed.txt"
    done = set(open(done_f).read().split()) if os.path.exists(done_f) else set()
    todo = [p for p in prods if str(p) not in done]
    n_found, n_done = len(prods), len(prods) - len(todo)
    todo = todo[:x.limit] if x.limit else todo
    print(f"{n_found} products in scope, {n_done} already done, {len(todo)} to do this run, workers {x.workers}")

    state = {"lock": threading.Lock(), "stored": 0}
    ok = bad = 0
    transferred = 0
    t0 = time.time()
    stop = False
    with ThreadPoolExecutor(max_workers=x.workers) as ex:
        futs = [ex.submit(process, p, x, state) for p in todo]
        for f in as_completed(futs):
            p, good, nb, msg = f.result()
            transferred += nb
            if good:
                ok += 1
                with lock:
                    open(done_f, "a").write(str(p) + "\n")
            else:
                bad += 1
                with lock:
                    open(fail_f, "a").write(f"{p}\t{msg}\n")
                if msg.startswith(("STOP", "DENIED")) and not stop:
                    stop = True
                    print(msg, "- cancelling remaining work")
                    for g in futs:
                        g.cancel()
            el = time.time() - t0
            rate = ok / el if el > 0 else 0
            left = len(todo) - ok - bad
            eta = f"{left / rate / 60:.0f} min" if rate > 0 else "?"
            print(f"[{ok} ok, {bad} failed, {left} left, {transferred / 1e9:.1f} GB transferred, stored {state['stored'] / 1e9:.2f} GB, eta {eta}] {p}: {msg}")
    print(f"finished: {ok} ok, {bad} failed. Failures are in {fail_f}; rerun the same command to retry them.")


if __name__ == "__main__":
    main()
