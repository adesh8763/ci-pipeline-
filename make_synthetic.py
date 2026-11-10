"""Make a SYNTHETIC ci_dataset.csv so the statistics stages (07-10) can be tested before / without real data.
The synthetic world has a KNOWN truth: satellite and radar carry signal, ERA5 carries only weak day-level signal,
IMERG is pure noise, so a correct pipeline must say: sat/radar matter, atmosphere = negligible/inconclusive,
placebo-atmosphere = no different from real atmosphere, IMERG = no gain.

    CI_ROOT=/some/test/dir python make_synthetic.py
"""
import numpy as np
import pandas as pd
from config import *

rng = np.random.default_rng(7)
days = pd.date_range(START, END)
rows, eid = [], 0
day_regime = {d: rng.normal() for d in days}                 # large-scale wetness of the day (shared by all events)
for d in days:
    for _ in range(rng.poisson(14)):
        hour = np.clip(rng.normal(16, 3), 8, 23)
        z = rng.normal()                                      # latent "true updraught strength"
        t_event = d + pd.Timedelta(hours=float(hour))
        base = dict(event_id=eid, day=str(d.date()), t_event=t_event, range_km=rng.uniform(20, 120))
        lab = {}
        for name, (dbz, w) in LABEL_DEFS.items():
            lab[f"label_{name}"] = float(z + 0.35 * day_regime[d] + 0.8 * rng.normal() > 0.15 * (dbz - 35) / 5 * 3 - 0.0)
        lab[f"label_{LABEL_IMERG}"] = float(rng.random() < 0.5)
        for lead in LEADS:
            vis = np.exp(-lead / 110.0)                       # signal fades with lead time
            r = dict(base, lead_min=lead, t_ref=t_event - pd.Timedelta(minutes=lead), **lab)
            hr = hour - lead / 60
            r.update(ctx_hour_sin=np.sin(2 * np.pi * hr / 24), ctx_hour_cos=np.cos(2 * np.pi * hr / 24), ctx_range_km=base["range_km"])
            r.update(seviri_d_BT108_15min_mean=-2 * vis * z + rng.normal(), seviri_d_BT108_15min_min=-2.5 * vis * z + rng.normal(),
                     seviri_BT_IR108_mean=270 - 6 * vis * z + 4 * rng.normal(), seviri_BTD_62_73_mean=rng.normal() + 0.8 * vis * z,
                     seviri_BTD_108_120_std=abs(rng.normal()) + 0.2 * vis * z)
            r.update(radar_cmax_max=10 + 6 * vis * z + 5 * rng.normal(), radar_cmax_mean=2 + 3 * vis * z + 4 * rng.normal(),
                     radar_frac_gt0=np.clip(0.3 + 0.1 * vis * z + 0.1 * rng.normal(), 0, 1), radar_frac_gt10=np.clip(0.1 + 0.05 * vis * z + 0.07 * rng.normal(), 0, 1))
            r.update(era5_CAPE=1500 + 400 * day_regime[d] + 300 * rng.normal(), era5_CIN=-50 + 20 * rng.normal(),
                     era5_TCWV=45 + 3 * day_regime[d] + 2 * rng.normal(), era5_RH_700=55 + 5 * day_regime[d] + 8 * rng.normal(),
                     era5_SHEAR_925_600=8 + 3 * rng.normal(), era5_OMEGA_700=-0.1 + 0.1 * rng.normal(),
                     era5_BLH=1200 + 200 * rng.normal(), era5_T2M=301 + rng.normal())
            r.update(imerg_p_last=abs(rng.normal()), imerg_p_accum=abs(rng.normal()) * 2, imerg_frac_wet=rng.random(), imerg_p_max=abs(rng.normal()) * 2)
            if rng.random() < 0.05:
                r["seviri_BT_IR108_mean"] = np.nan             # realistic missingness
            rows.append(r)
        eid += 1
df = pd.DataFrame(rows)
df.to_csv(DATASET_FILE, index=False)
print(df.shape, "->", DATASET_FILE, "| events", eid, "| prevalence", df[f"label_{PRIMARY_LABEL}"].mean().round(2))
