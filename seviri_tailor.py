#!/usr/bin/env python
"""SEVIRI via EUMETSAT Data Tailor, a few jobs at a time: submit -> wait -> download -> delete.

Replaces the 'submit everything' --tailor path of fetch_data.py, which can overload Data Tailor
and never downloads the results. Standalone: does not import fetch_data.py.

Setup: pip install eumdac ; env vars EUMETSAT_CONSUMER_KEY and EUMETSAT_CONSUMER_SECRET.

Examples
  python seviri_tailor.py --cleanup                      # delete the 99+ jobs left from the stuck run
  python seviri_tailor.py --pilot --limit 4              # smoke test: 4 slots
  python seviri_tailor.py --pilot                        # 5 days
  python seviri_tailor.py                                # full period; rerun the same command to resume
Options: --batch N (jobs in flight, default 4), --channels, --box N S W E, --start/--end, --out DIR

Completed slots are logged to data/logs/seviri_tailor_done.txt, failed ones to ..._failed.txt.
STATUS: not run against the live service. The eumdac calls follow its documented API and are UNVERIFIED
here; the chain settings are the ones your earlier run was accepted with.
"""
import argparse, datetime as dt, os, shutil, sys, time

START = dt.datetime(2006, 8, 19, 0, 0)
END = dt.datetime(2006, 9, 30, 23, 45)
BOX = dict(N=19.1, S=10.2, W=-21.54, E=-12.65)        # match RADAR_BOX + 2 deg padding in your fetch_data.py
CHANNELS = ["channel_9", "channel_5", "channel_6", "channel_4", "channel_10", "channel_7", "channel_1"]
TERMINAL = {"DONE", "ERROR", "FAILED", "KILLED", "DELETED", "INACTIVE"}


def token():
    import eumdac
    return eumdac.AccessToken((os.environ["EUMETSAT_CONSUMER_KEY"], os.environ["EUMETSAT_CONSUMER_SECRET"]))


def cleanup():
    import eumdac
    dtl = eumdac.DataTailor(token())
    n = 0
    for c in dtl.customisations:
        try:
            if c.status in ("QUEUED", "RUNNING"):
                c.kill()
            c.delete()
            n += 1
        except Exception as e:
            print("could not remove", c, e)
    print("removed", n, "customisations")


def status(c):
    s = c.status
    return str(s).split(".")[-1].upper()


def log_of(c):
    try:
        return str(c.logfile)[-3000:]
    except Exception as e:
        return f"(no log available: {e})"


def diagnose(eumdac, dtl, product, box, channels):
    """Submit one product with several chain variants to find which setting the server rejects."""
    roi = {"NSWE": [box["N"], box["S"], box["W"], box["E"]]}
    variants = {
        "A current (netcdf4, geographic, roi, bands)": dict(product="HRSEVIRI", format="netcdf4",
                                                            projection="geographic", roi=roi,
                                                            filter={"bands": channels}),
        "B no roi": dict(product="HRSEVIRI", format="netcdf4", projection="geographic",
                         filter={"bands": channels}),
        "C no band filter": dict(product="HRSEVIRI", format="netcdf4", projection="geographic", roi=roi),
        "D no roi, no band filter": dict(product="HRSEVIRI", format="netcdf4", projection="geographic"),
        "E hdf5, no projection": dict(product="HRSEVIRI", format="hdf5"),
    }
    print("diagnosing with product", product)
    for name, kw in variants.items():
        try:
            c = dtl.new_customisation(product, eumdac.tailor_models.Chain(**kw))
        except Exception as e:
            print(f"{name}: REJECTED AT SUBMIT: {e}")
            continue
        t0, s = time.time(), status(c)
        while s not in TERMINAL and time.time() - t0 < 600:
            time.sleep(10)
            s = status(c)
        print(f"{name}: {s}")
        if s != "DONE":
            print("  log:", log_of(c)[-800:])
        try:
            c.delete()
        except Exception:
            pass


def main():
    global START, END
    a = argparse.ArgumentParser()
    a.add_argument("--start"); a.add_argument("--end")
    a.add_argument("--pilot", action="store_true")
    a.add_argument("--limit", type=int, default=0)
    a.add_argument("--batch", type=int, default=4)
    a.add_argument("--channels", default=",".join(CHANNELS))
    a.add_argument("--box", nargs=4, type=float, metavar=("N", "S", "W", "E"))
    a.add_argument("--out", default="data/raw/seviri_tailored")
    a.add_argument("--timeout-min", type=float, default=30.0, help="give up on a job after this long")
    a.add_argument("--cleanup", action="store_true", help="delete existing customisations, then exit")
    a.add_argument("--diagnose", action="store_true",
                   help="submit ONE product with 5 chain variants and print which fail and why, then exit")
    x = a.parse_args()

    if x.cleanup:
        cleanup()
        return
    if x.start:
        START = dt.datetime.fromisoformat(x.start)
    if x.end:
        END = dt.datetime.fromisoformat(x.end).replace(hour=23, minute=45)
    if x.pilot:
        END = START + dt.timedelta(days=5) - dt.timedelta(minutes=15)
    box = dict(zip("NSWE", x.box)) if x.box else BOX
    channels = [c.strip() for c in x.channels.split(",") if c.strip()]

    import eumdac
    tok = token()
    store = eumdac.DataStore(tok)
    dtl = eumdac.DataTailor(tok)
    prods = sorted(store.get_collection("EO:EUM:DAT:MSG:HRSEVIRI").search(dtstart=START, dtend=END), key=str)
    print(len(prods), "products found for", START, "..", END)

    os.makedirs("data/logs", exist_ok=True)
    os.makedirs(x.out, exist_ok=True)
    done_f, fail_f = "data/logs/seviri_tailor_done.txt", "data/logs/seviri_tailor_failed.txt"
    done = set(open(done_f).read().split()) if os.path.exists(done_f) else set()
    todo = [p for p in prods if str(p) not in done]
    n_done = len(prods) - len(todo)
    todo = todo[:x.limit] if x.limit else todo
    print(len(todo), "to do,", n_done, "already done; batch size", x.batch)

    if x.diagnose:
        diagnose(eumdac, dtl, prods[0], box, channels)
        return

    chain = eumdac.tailor_models.Chain(
        product="HRSEVIRI", format="netcdf4", projection="geographic",
        roi={"NSWE": [box["N"], box["S"], box["W"], box["E"]]}, filter={"bands": channels})

    ok = bad = 0
    for i in range(0, len(todo), x.batch):
        jobs = []
        for p in todo[i:i + x.batch]:
            try:
                jobs.append((p, dtl.new_customisation(p, chain)))
            except Exception as e:
                print("submit failed", p, e)
                open(fail_f, "a").write(f"{p} submit {e}\n")
                bad += 1
        t0 = time.time()
        pending = list(jobs)
        while pending and (time.time() - t0) < x.timeout_min * 60:
            time.sleep(10)
            for p, c in list(pending):
                s = status(c)
                if s not in TERMINAL:
                    continue
                pending.remove((p, c))
                if s == "DONE":
                    try:
                        for out in c.outputs:
                            with c.stream_output(out) as stream:
                                path = os.path.join(x.out, os.path.basename(stream.name))
                                with open(path, "wb") as f:
                                    shutil.copyfileobj(stream, f)
                        open(done_f, "a").write(str(p) + "\n")
                        ok += 1
                        print("downloaded", p)
                    except Exception as e:
                        print("download failed", p, e)
                        open(fail_f, "a").write(f"{p} download {e}\n")
                        bad += 1
                else:
                    msg = log_of(c)
                    print("job ended with", s, p)
                    print("  server log (last lines):", msg[-600:])
                    open(fail_f, "a").write(f"{p} {s}\n{msg}\n---\n")
                    bad += 1
                try:
                    c.delete()
                except Exception:
                    pass
        for p, c in pending:                              # timed out
            print("timeout", p)
            open(fail_f, "a").write(f"{p} timeout\n")
            bad += 1
            try:
                c.kill(); c.delete()
            except Exception:
                pass
        print(f"progress: {ok} ok, {bad} failed, {len(todo) - ok - bad} left")
    print("finished:", ok, "downloaded,", bad, "failed. Rerun to retry failures.")


if __name__ == "__main__":
    main()




# nohup python seviri_fetch.py --max-gb 100 --workers 4 > seviri_full.log 2>&1 &