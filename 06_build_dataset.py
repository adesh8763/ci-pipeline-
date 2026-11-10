"""Step 6: build the model-ready long table: one row per (CI event x lead time).

STRICT NO-LEAKAGE RULE: every predictor is timestamped at or before  t_ref = t_event - lead.
  SEVIRI : latest scan whose nominal time + SEVIRI_LATENCY_MIN <= t_ref   (scan needs ~15 min to complete)
  radar  : latest volume <= t_ref
  ERA5   : latest hourly field <= t_ref  (bilinear in space)
  IMERG  : only 30-min slots that END at or before t_ref
The IMERG-confirmed LABEL (rain after the event) is the only place post-event IMERG data are used.

Output: data/processed/<tag>/ci_dataset.csv
    python 06_build_dataset.py
"""
import numpy as np
import pandas as pd
import xarray as xr
from config import *

SEVIRI_LATENCY_MIN = 15
MAX_AGE_MIN = {"seviri": 30, "radar": 15}


def latest_before(index, t, delay_min=0, max_age_min=None):
    """Position of the last stamp s with s + delay <= t (and not older than max_age), else None."""
    ok = np.where(index + pd.Timedelta(minutes=delay_min) <= t)[0]
    if ok.size == 0:
        return None
    i = int(ok[-1])
    if max_age_min is not None and (t - index[i]).total_seconds() / 60 > max_age_min + delay_min:
        return None
    return i


# ------------------------------------------------------------------ SEVIRI
def seviri_locator(sev):
    lat_n = next(c for c in ("lat", "latitude") if c in sev.coords)
    lon_n = next(c for c in ("lon", "longitude") if c in sev.coords)
    lat, lon = sev[lat_n], sev[lon_n]
    if lat.ndim == 1:
        dy, dx = lat.dims[0], lon.dims[0]
        latv, lonv = lat.values, lon.values

        def loc(la, lo):
            return int(np.abs(latv - la).argmin()), int(np.abs(lonv - lo).argmin())
    else:
        dy, dx = lat.dims
        latv, lonv = lat.values, lon.values

        def loc(la, lo):
            d = (latv - la) ** 2 + ((lonv - lo) * np.cos(np.radians(la))) ** 2
            return tuple(int(i) for i in np.unravel_index(np.nanargmin(d), d.shape))
    return dy, dx, loc


def seviri_features(sev, s_t, dy, dx, loc, t_ref, la, lo):
    i = latest_before(s_t, t_ref, SEVIRI_LATENCY_MIN, MAX_AGE_MIN["seviri"])
    if i is None:
        return {}
    iy, ix = loc(la, lo)
    w = SEVIRI_WIN_PX
    sub = sev.isel(time=i, **{dy: slice(max(iy - w, 0), iy + w + 1), dx: slice(max(ix - w, 0), ix + w + 1)})
    out = {}
    for v in sev.data_vars:
        a = np.asarray(sub[v].values, dtype=float)
        if a.size and np.isfinite(a).any():
            out[f"seviri_{v}_mean"] = np.nanmean(a)
            out[f"seviri_{v}_min"] = np.nanmin(a)
            out[f"seviri_{v}_std"] = np.nanstd(a)
    return out


# ------------------------------------------------------------------ radar
def radar_features(rfiles, rtimes, t_ref, ex, ey):
    i = latest_before(rtimes, t_ref, 0, MAX_AGE_MIN["radar"])
    if i is None:
        return {}
    with xr.open_dataset(rfiles[i]) as r:
        xs, ys = r.x.values / 1000, r.y.values / 1000
        m = ((xs[None, :] - ex) ** 2 + (ys[:, None] - ey) ** 2) <= RADAR_WIN_KM ** 2
        a = np.nan_to_num(r.cmax.values[m], nan=-99.0)
    if a.size == 0:
        return {}
    valid = a > -90
    return dict(radar_cmax_max=float(a.max()) if valid.any() else -30.0,
                radar_cmax_mean=float(a[valid].mean()) if valid.any() else -30.0,
                radar_frac_gt0=float((a > 0).mean()), radar_frac_gt10=float((a > 10).mean()))


# ------------------------------------------------------------------ ERA5
def era5_features(era, t_ref, la, lo):
    ln = "latitude" if "latitude" in era.coords else "lat"
    lg = "longitude" if "longitude" in era.coords else "lon"
    try:
        pt = era.sel(time=t_ref, method="pad").interp({ln: la, lg: lo})
    except Exception:
        return {}
    return {f"era5_{v}": float(pt[v]) for v in era.data_vars}


# ------------------------------------------------------------------ IMERG
def imerg_features(imerg, i_t, t_ref, la, lo):
    b = IMERG_BOX_DEG
    slot_end = i_t + pd.Timedelta(minutes=30)
    k = np.where(slot_end <= t_ref)[0]
    if k.size == 0 or (t_ref - slot_end[k[-1]]).total_seconds() > 3600:
        return {}
    k = k[-1]
    box = imerg.sel(lat=slice(la - b, la + b), lon=slice(lo - b, lo + b))
    last = box.isel(time=k).values
    n_slots = int(IMERG_ACCUM_H * 2)
    hist = box.isel(time=slice(max(k - n_slots + 1, 0), k + 1)).mean(("lat", "lon")).values
    if not np.isfinite(last).any():
        return {}
    return dict(imerg_p_last=float(np.nanmean(last)), imerg_p_max=float(np.nanmax(last)),
                imerg_frac_wet=float(np.nanmean(last >= 0.1)),
                imerg_p_accum=float(np.nansum(hist) * 0.5))


def imerg_label(imerg, i_t, t_event, la, lo):
    b = IMERG_BOX_DEG
    sel = np.where((i_t > t_event - pd.Timedelta(minutes=30)) & (i_t <= t_event + pd.Timedelta(minutes=60)))[0]
    if sel.size < 2:
        return np.nan
    box = imerg.sel(lat=slice(la - b, la + b), lon=slice(lo - b, lo + b)).isel(time=sel).values
    if not np.isfinite(box).any():
        return np.nan
    return float(np.nanmax(box) >= IMERG_RAIN_MMH)


def main():
    ev = pd.read_csv(EVENTS_FILE, parse_dates=["time"])
    sev = xr.open_mfdataset(sorted(SEVIRI_FEAT_DIR.glob("seviri_*.nc")), combine="by_coords")
    s_t = pd.DatetimeIndex(sev.time.values)
    dy, dx, loc = seviri_locator(sev)
    era = xr.open_dataset(ERA5_FEAT_FILE).sortby("time")
    for c in ("latitude", "lat"):
        if c in era.coords:
            era = era.sortby(c)
    imerg = xr.open_dataset(IMERG_FEAT_FILE)["precip"].load() if IMERG_FEAT_FILE.exists() else None
    i_t = pd.DatetimeIndex(imerg.time.values) if imerg is not None else None
    rfiles = sorted(RADAR_GRID_DIR.glob("*.nc"))
    rtimes = pd.DatetimeIndex([pd.Timestamp(f.stem.replace("_", "T")) for f in rfiles])

    label_cols = [c for c in ev.columns if c.startswith("label_")]
    rows = []
    for n, (_, e) in enumerate(ev.iterrows()):
        lab_im = imerg_label(imerg, i_t, e.time, e.lat, e.lon) if imerg is not None else np.nan
        for lead in LEADS:
            t = e.time - pd.Timedelta(minutes=lead)
            row = dict(event_id=int(e.event_id), lead_min=lead, t_ref=t, day=e.day, t_event=e.time,
                       range_km=e.range_km, **{c: e[c] for c in label_cols}, **{f"label_{LABEL_IMERG}": lab_im})
            hr = t.hour + t.minute / 60
            row.update(ctx_hour_sin=np.sin(2 * np.pi * hr / 24), ctx_hour_cos=np.cos(2 * np.pi * hr / 24), ctx_range_km=e.range_km)
            row.update(seviri_features(sev, s_t, dy, dx, loc, t, e.lat, e.lon))
            row.update(radar_features(rfiles, rtimes, t, e.x_km, e.y_km))
            row.update(era5_features(era, t, e.lat, e.lon))
            if imerg is not None:
                row.update(imerg_features(imerg, i_t, t, e.lat, e.lon))
            rows.append(row)
        if (n + 1) % 100 == 0:
            print(f"  {n+1}/{len(ev)} events")
    df = pd.DataFrame(rows)
    df.to_csv(DATASET_FILE, index=False)

    # --- coverage report: which predictor groups are missing how often (drives honest reporting)
    from variables import group_of
    print(df.shape, "->", DATASET_FILE)
    feat = [c for c in df.columns if group_of(c) != "other"]
    miss = df[feat].isna().mean().groupby(group_of).mean()
    print("mean missing fraction by group:\n", miss.round(3).to_string())
    print(df.groupby("lead_min")[f"label_{PRIMARY_LABEL}"].agg(["count", "mean"]).rename(columns={"mean": "prevalence"}))
    if imerg is not None:
        a, b = df[f"label_{PRIMARY_LABEL}"], df[f"label_{LABEL_IMERG}"]
        ok = a.notna() & b.notna()
        print(f"agreement radar-label vs IMERG-confirmed: {(a[ok] == b[ok]).mean():.3f} (n={int(ok.sum())})")


if __name__ == "__main__":
    main()
