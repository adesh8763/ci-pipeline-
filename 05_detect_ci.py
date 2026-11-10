"""Step 5: detect convective-initiation (CI) candidates in the radar grids and compute everything needed to
label them under MANY definitions (so the labelling rule itself can be stress-tested).

For each candidate (a NEW cell: column-max reflectivity first reaches FIRST_ECHO_DBZ with no such echo within
PRECURSOR_KM during the previous LOOKBACK_MIN) we store
  peak_dbz_w30 / w45 / w60 : maximum column-max reflectivity within TRACK_KM of the initiation point during the
                             following 30 / 45 / 60 minutes
  complete_w*               : False if the radar had a scan gap > MAX_SCAN_GAP_MIN inside that window or the
                             record ends before it -> such events are EXCLUDED rather than mislabelled "false"
  range_km, time, lat, lon, area_px, precursor_max_dbz
Label columns  label_t{30,35,40}_w{30,45,60}  are then derived (see config.LABEL_DEFS).

Output: data/processed/<tag>/ci_events.csv
    python 05_detect_ci.py
"""
import numpy as np
import pandas as pd
import xarray as xr
from scipy import ndimage as ndi
from config import *


def load_stack():
    files = sorted(RADAR_GRID_DIR.glob("*.nc"))
    if not files:
        raise SystemExit("Run 02_radar_grid.py first.")
    times, cmax = [], []
    meta = {}
    for f in files:
        with xr.open_dataset(f) as d:
            times.append(pd.Timestamp(d.time.values))
            cmax.append(d.cmax.values.astype("float32"))
            if not meta:
                meta = dict(x=d.x.values / 1000.0, y=d.y.values / 1000.0, lat0=d.attrs["radar_lat"], lon0=d.attrs["radar_lon"])
    order = np.argsort(times)
    times = pd.DatetimeIndex(np.array(times)[order])
    cmax = np.nan_to_num(np.stack(cmax)[order], nan=-99.0)
    return times, cmax, meta


def window_ok(times, k, minutes):
    """True if radar covers [t_k, t_k+minutes] without gaps larger than MAX_SCAN_GAP_MIN."""
    t_end = times[k] + pd.Timedelta(minutes=minutes)
    if times[-1] < t_end - pd.Timedelta(minutes=MAX_SCAN_GAP_MIN):
        return False
    idx = [j for j in range(k, len(times)) if times[j] <= t_end]
    ts = times[idx]
    gaps = np.diff(ts.values).astype("timedelta64[s]").astype(float) / 60
    tail = (t_end - ts[-1]).total_seconds() / 60
    return bool((gaps.size == 0 or gaps.max() <= MAX_SCAN_GAP_MIN) and tail <= MAX_SCAN_GAP_MIN)


def main():
    times, cmax, m = load_stack()
    x, y = m["x"], m["y"]
    X, Y = np.meshgrid(x, y)
    px = GRID_RES_KM
    rp = max(int(PRECURSOR_KM / px), 1)
    yy, xx = np.ogrid[-rp:rp + 1, -rp:rp + 1]
    disk = (xx ** 2 + yy ** 2) <= rp ** 2
    n_t = len(times)
    events = []
    for k in range(1, n_t):
        mask = cmax[k] >= FIRST_ECHO_DBZ
        if not mask.any():
            continue
        past = [j for j in range(k) if 0 < (times[k] - times[j]).total_seconds() / 60 <= LOOKBACK_MIN]
        if not past:
            continue
        # require the lookback to be covered (a missing scan could hide a precursor)
        if (times[k] - times[past[0]]).total_seconds() / 60 < LOOKBACK_MIN - MAX_SCAN_GAP_MIN:
            continue
        prev = ndi.binary_dilation(np.any([cmax[j] >= FIRST_ECHO_DBZ for j in past], axis=0), structure=disk)
        lab, n = ndi.label(mask & ~prev)
        for i in range(1, n + 1):
            area = int((lab == i).sum())
            if area < MIN_AREA_PX:
                continue
            cy, cx = ndi.center_of_mass(lab == i)
            iy, ix = int(round(cy)), int(round(cx))
            rng = float(np.hypot(x[ix], y[iy]))
            if rng > MAX_RANGE_KM:
                continue
            near = (X - x[ix]) ** 2 + (Y - y[iy]) ** 2 <= TRACK_KM ** 2
            row = dict(time=times[k], x_km=x[ix], y_km=y[iy], range_km=rng, area_px=area,
                       lat=m["lat0"] + y[iy] / 111.2,
                       lon=m["lon0"] + x[ix] / (111.2 * np.cos(np.radians(m["lat0"]))),
                       precursor_max_dbz=float(cmax[max(k - 1, 0)][near].max()))
            for w in WINDOWS_MIN:
                js = [j for j in range(k, n_t) if (times[j] - times[k]).total_seconds() / 60 <= w]
                row[f"peak_dbz_w{w}"] = float(max(cmax[j][near].max() for j in js))
                row[f"complete_w{w}"] = window_ok(times, k, w)
            events.append(row)
    df = pd.DataFrame(events)
    if df.empty:
        raise SystemExit("No CI candidates found - check thresholds / radar grids.")
    df.insert(0, "event_id", np.arange(len(df)))
    df["day"] = df.time.dt.strftime("%Y-%m-%d")
    for name, (dbz, w) in LABEL_DEFS.items():
        df[f"label_{name}"] = np.where(df[f"complete_w{w}"], (df[f"peak_dbz_w{w}"] >= dbz).astype(float), np.nan)
    df.to_csv(EVENTS_FILE, index=False)
    p = f"label_{PRIMARY_LABEL}"
    print(f"{len(df)} candidates on {df.day.nunique()} days | primary label {PRIMARY_LABEL}: "
          f"true={int((df[p] == 1).sum())} false={int((df[p] == 0).sum())} excluded(incomplete)={int(df[p].isna().sum())}")
    print("label prevalence across definitions:")
    print(df[[f"label_{n}" for n in LABEL_DEFS]].mean().round(3).to_string())
    print("saved", EVENTS_FILE)


if __name__ == "__main__":
    main()
