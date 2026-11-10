"""Step 12: WHOLE-DOMAIN, object-free dataset (Messori: "use whole-domain data without the need for centering on
tracked cloud objects").

The object-based dataset (06) asks: GIVEN a radar-detected candidate cell, will it become a true CI?  Its samples are
centred on cells that were already found, so the result can depend on the detection / tracking rules.
Here every sample is simply a  BOX x TIME WINDOW  anywhere in the radar domain:

    sample  = (box of DOMAIN_BOX_KM, window [T, T+DOMAIN_STEP_MIN))
    target  = label_domain_true : a TRUE CI (primary-label rule) starts in that box during the window
              label_domain_any  : any CI candidate (true or false) starts there
    predictors are taken at t_ref = T - lead, exactly as in 06 (same leakage rules)
    excluded: boxes that already contain echo >= FIRST_ECHO_DBZ at T (not an *initiation*), windows with radar gaps

No tracking, no object centring: the question becomes "where and when will true CI start?" (harder, base rate ~0.1 %).
Negatives are subsampled (DOMAIN_NEG_KEEP) and carry sampling weights `sw`, which 07-09b propagate so that every
score refers to the TRUE base rate.  NOTE: the lead here is measured to the WINDOW START; the actual first echo comes
0-DOMAIN_STEP_MIN later.

Run the object-based pipeline first (needs data/processed/main/ci_events.csv), then:
    CI_TAG=domain CI_PRIMARY_LABEL=domain_true python 12_domain_dataset.py
    CI_TAG=domain CI_PRIMARY_LABEL=domain_true python 07_models.py --quick --core --repeats 3
    CI_TAG=domain CI_PRIMARY_LABEL=domain_true python 08_information.py --skip-null
    CI_TAG=domain CI_PRIMARY_LABEL=domain_true python 09_robustness.py
    CI_TAG=domain CI_PRIMARY_LABEL=domain_true python 09b_ranking_equivalence.py
    CI_TAG=domain CI_PRIMARY_LABEL=domain_true python 10_figures_report.py
"""
import importlib
import numpy as np
import pandas as pd
import xarray as xr
from config import *

det = importlib.import_module("05_detect_ci")
bd = importlib.import_module("06_build_dataset")
TRUE_LABEL = "label_t35_w45"      # the object-based primary rule defines what counts as a TRUE CI


def seviri_loaded(sev, s_t, dy, dx, cache, t_ref):
    i = bd.latest_before(s_t, t_ref, bd.SEVIRI_LATENCY_MIN, bd.MAX_AGE_MIN["seviri"])
    if i is None:
        return None
    if i not in cache:
        cache.clear()                                   # t_ref is processed in time order -> keep one scan in memory
        sub = sev.isel(time=i).load()
        cache[i] = {v: np.asarray(sub[v].values, float) for v in sev.data_vars}
    return cache[i]


def sev_stats(arrs, iy, ix, w=SEVIRI_WIN_PX):
    out = {}
    for v, a2 in arrs.items():
        a = a2[max(iy - w, 0):iy + w + 1, max(ix - w, 0):ix + w + 1]
        if a.size and np.isfinite(a).any():
            out[f"seviri_{v}_mean"] = np.nanmean(a); out[f"seviri_{v}_min"] = np.nanmin(a); out[f"seviri_{v}_std"] = np.nanstd(a)
    return out


def main():
    rng = np.random.default_rng(RANDOM_SEED)
    times, cmax, m = det.load_stack()
    x, y = m["x"], m["y"]
    n = max(int(round(DOMAIN_BOX_KM / GRID_RES_KM)), 1)
    nby, nbx = cmax.shape[1] // n, cmax.shape[2] // n
    box = cmax[:, :nby * n, :nbx * n].reshape(len(times), nby, n, nbx, n).max(axis=(2, 4))      # box-max reflectivity
    xc = x[:nbx * n].reshape(nbx, n).mean(1); yc = y[:nby * n].reshape(nby, n).mean(1)
    XC, YC = np.meshgrid(xc, yc)
    RNG = np.hypot(XC, YC)
    inrange = RNG <= MAX_RANGE_KM
    x0, y0 = x[0] - GRID_RES_KM / 2, y[0] - GRID_RES_KM / 2

    # ---- target windows
    step = pd.Timedelta(minutes=DOMAIN_STEP_MIN)
    T0 = times[0].ceil(f"{DOMAIN_STEP_MIN}min")
    Ts = pd.date_range(T0, times[-1] - step, freq=step)
    valid_T, k_at = [], []
    for Ti, T in enumerate(Ts):
        ka = bd.latest_before(times, T, 0, 15)
        k0 = int(np.searchsorted(times.values, np.datetime64(T)))
        if ka is None or k0 >= len(times) or (times[k0] - T).total_seconds() > 900 or not det.window_ok(times, k0, DOMAIN_STEP_MIN):
            valid_T.append(False); k_at.append(-1)
        else:
            valid_T.append(True); k_at.append(ka)
    valid_T, k_at = np.array(valid_T), np.array(k_at)
    print(f"{len(Ts)} windows, {int(valid_T.sum())} with complete radar coverage; {int(inrange.sum())} boxes in range")

    # ---- labels from the object-based events
    ev = pd.read_csv(EVENTS_FROM, parse_dates=["time"])
    ev = ev[ev[TRUE_LABEL].notna()]
    ti = np.floor((ev.time - T0) / step).astype(int).values
    bx = np.floor((ev.x_km.values - x0) / DOMAIN_BOX_KM).astype(int); by = np.floor((ev.y_km.values - y0) / DOMAIN_BOX_KM).astype(int)
    ok = (ti >= 0) & (ti < len(Ts)) & (bx >= 0) & (bx < nbx) & (by >= 0) & (by < nby)
    true_set = set(zip(ti[ok & (ev[TRUE_LABEL].values == 1)], by[ok & (ev[TRUE_LABEL].values == 1)], bx[ok & (ev[TRUE_LABEL].values == 1)]))
    any_set = set(zip(ti[ok], by[ok], bx[ok]))

    samples, n_valid, n_dropped_pos = [], 0, 0
    for Ti in np.where(valid_T)[0]:
        free = inrange & (box[k_at[Ti]] < FIRST_ECHO_DBZ)              # no pre-existing echo: only NEW initiation counts
        iy, ix = np.where(free)
        n_valid += len(iy)
        is_true = np.array([(Ti, a, b) in true_set for a, b in zip(iy, ix)])
        is_any = np.array([(Ti, a, b) in any_set for a, b in zip(iy, ix)])
        keep = is_true | (rng.random(len(iy)) < DOMAIN_NEG_KEEP)
        for a, b, t_, an, kp in zip(iy, ix, is_true, is_any, keep):
            if kp:
                samples.append((Ti, a, b, t_, an))
    n_pos_all = len(true_set)
    n_pos = sum(s[3] for s in samples)
    print(f"valid (box,window) pairs: {n_valid}; kept samples: {len(samples)}; true-CI samples kept: {n_pos} of {n_pos_all} events "
          f"(rest fell on windows/boxes excluded by QC); base rate ~ {n_pos / max(n_valid, 1):.5f}")

    # ---- predictors
    sev = xr.open_mfdataset(sorted(SEVIRI_FEAT_DIR.glob("seviri_*.nc")), combine="by_coords")
    s_t = pd.DatetimeIndex(sev.time.values)
    dy, dx, loc = bd.seviri_locator(sev)
    era = xr.open_dataset(ERA5_FEAT_FILE).sortby("time").load()
    for c in ("latitude", "lat"):
        if c in era.coords:
            era = era.sortby(c)
    imerg = xr.open_dataset(IMERG_FEAT_FILE)["precip"].load() if IMERG_FEAT_FILE.exists() else None
    i_t = pd.DatetimeIndex(imerg.time.values) if imerg is not None else None
    rfiles = sorted(RADAR_GRID_DIR.glob("*.nc"))
    rtimes = pd.DatetimeIndex([pd.Timestamp(f.stem.replace("_", "T")) for f in rfiles])
    lat0, lon0 = m["lat0"], m["lon0"]
    w_neg = 1.0 / DOMAIN_NEG_KEEP

    jobs = [(Ts[s[0]] - pd.Timedelta(minutes=L), L, sid, s) for sid, s in enumerate(samples) for L in LEADS]
    jobs.sort(key=lambda j: j[0])                       # time order -> one SEVIRI scan in memory at a time
    cache, rows = {}, []
    for n_done, (t_ref, lead, sid, s) in enumerate(jobs):
        Ti, a, b, is_true, is_any = s
        T = Ts[Ti]
        ex, ey = float(XC[a, b]), float(YC[a, b])
        la, lo = lat0 + ey / 111.2, lon0 + ex / (111.2 * np.cos(np.radians(lat0)))
        row = dict(event_id=sid, lead_min=lead, t_ref=t_ref, day=T.strftime("%Y-%m-%d"), t_event=T, range_km=float(RNG[a, b]),
                   label_domain_true=float(is_true), label_domain_any=float(is_any), sw=1.0 if is_true else w_neg)
        hr = t_ref.hour + t_ref.minute / 60
        row.update(ctx_hour_sin=np.sin(2 * np.pi * hr / 24), ctx_hour_cos=np.cos(2 * np.pi * hr / 24), ctx_range_km=float(RNG[a, b]))
        arrs = seviri_loaded(sev, s_t, dy, dx, cache, t_ref)
        if arrs is not None:
            iy_, ix_ = loc(la, lo)
            row.update(sev_stats(arrs, iy_, ix_))
        row.update(bd.radar_features(rfiles, rtimes, t_ref, ex, ey))
        row.update(bd.era5_features(era, t_ref, la, lo))
        if imerg is not None:
            row.update(bd.imerg_features(imerg, i_t, t_ref, la, lo))
        rows.append(row)
        if (n_done + 1) % 5000 == 0:
            print(f"  {n_done + 1}/{len(jobs)} rows", flush=True)
    df = pd.DataFrame(rows).sort_values(["lead_min", "event_id"])
    df.to_csv(DATASET_FILE, index=False)
    print(df.shape, "->", DATASET_FILE)
    print(df.groupby("lead_min").apply(lambda d: pd.Series(dict(n=len(d), n_true=int(d.label_domain_true.sum()),
          weighted_base_rate=float((d.sw * d.label_domain_true).sum() / d.sw.sum()))), include_groups=False))


if __name__ == "__main__":
    main()
