"""Step 8: information analysis (MI / CMI) with proper nulls and uncertainty.

 (a) VARIABLE level: kNN mutual information I(x; CI) for every predictor, with two permutation nulls
       global     : labels shuffled across all events       -> "any information at all?"
       within-day : labels shuffled inside each day         -> "information beyond the day's regime?"
     p-values are Benjamini-Hochberg adjusted across variables.            -> info_variable_mi.csv
 (b) GROUP level conditional information  I(X; CI | Z) estimated as the out-of-fold log-loss reduction
         CMI(X;Y|Z) ~ LL(Z-model) - LL(X+Z-model)       (bits per event; negative = no information, over-fitting)
     with day-cluster bootstrap CIs, from the OOF predictions of 07_models.py.      -> info_group_cmi.csv
 (c) PERMUTATION NULL for the headline contrasts, refitting the model with the X-block shuffled
       global / within-day (event-specific information beyond the day regime).      -> info_group_null.csv
     A real contribution must beat the null; a "gain" inside the null is noise.

    python 08_information.py [--n-perm 30] [--skip-null]
"""
import argparse
import warnings
import numpy as np
import pandas as pd
from sklearn.feature_selection import mutual_info_classif
from config import *
from variables import columns, group_of, atm_columns, atm_subgroup
import robust_lib as R
import importlib

warnings.filterwarnings("ignore")
models_mod = importlib.import_module("07_models")

# (X group added, Z conditioning set, name, Z-model, XZ-model)
CONTRASTS = [
    ("sat | radar", "M2", "M4"), ("radar | sat", "M1", "M4"),
    ("sat | atm", "A", "M3"), ("atm | sat", "M1", "M3"),
    ("radar | atm", "A", "RA"), ("atm | radar", "M2", "RA"),
    ("atm | sat+radar", "M4", "M5"), ("atm | sat+radar+ctx", "M4c", "M5c"),
    ("PLACEBO atm | sat+radar", "M4", "M5_shufatm"),
    ("imerg | sat+radar", "M4", "M4P"), ("imerg | sat+radar+atm", "M5", "M7"),
]


def bh(p):
    p = np.asarray(p, float); n = len(p); o = np.argsort(p)
    adj = np.empty(n); run = 1.0
    for rank, i in zip(range(n, 0, -1), o[::-1]):
        run = min(run, p[i] * n / rank); adj[i] = run
    return adj


def variable_mi(df, n_perm, rng):
    rows = []
    d = df[df[f"label_{PRIMARY_LABEL}"].notna()]
    feats = [c for c in d.columns if group_of(c) in ("sat", "radar", "atm", "precip")]
    for lead, dl in d.groupby("lead_min"):
        X = dl[feats].apply(lambda s: s.fillna(s.median())).values
        keep = np.nanstd(X, 0) > 0
        y = dl[f"label_{PRIMARY_LABEL}"].values.astype(int)
        days = dl["day"].values
        obs = np.zeros(len(feats)); obs[keep] = mutual_info_classif(X[:, keep], y, n_neighbors=5, random_state=0)
        ge_g, ge_w = np.ones(len(feats)), np.ones(len(feats))
        for _ in range(n_perm):
            yg = rng.permutation(y)
            yw = y.copy()
            for dd in np.unique(days):
                ix = np.where(days == dd)[0]; yw[ix] = rng.permutation(y[ix])
            for yy, ge in ((yg, ge_g), (yw, ge_w)):
                m = np.zeros(len(feats)); m[keep] = mutual_info_classif(X[:, keep], yy, n_neighbors=5, random_state=0)
                ge += (m >= obs)
        for j, f in enumerate(feats):
            rows.append(dict(lead_min=lead, variable=f, group=group_of(f), subgroup=atm_subgroup(f), MI_nats=obs[j],
                             p_global=ge_g[j] / (n_perm + 1), p_withinday=ge_w[j] / (n_perm + 1)))
    out = pd.DataFrame(rows)
    for c in ("p_global", "p_withinday"):
        out[c + "_BH"] = out.groupby("lead_min")[c].transform(lambda s: bh(s.values))
    return out


def group_cmi(g, nboot):
    rows = []
    for label, learner, lead, y, day_idx, P, sw in R.iter_cells(g):
        W = R.boot_weights(day_idx, nboot, R.cell_seed(label, learner, lead), sw)
        LL = {m: R.metrics_boot(y, p, W)["LOGLOSS"] for m, p in P.items()}
        pairs = list(CONTRASTS) + [(f"atm group '{m[6:]}' | rest", m, "M5") for m in P if m.startswith("M6_no_")]
        for name, z, xz in pairs:
            if z in LL and xz in LL:
                d = (LL[z] - LL[xz]) / R.LN2           # bits / event
                pt, lo, hi = R.summarise(d)
                rows.append(dict(label=label, learner=learner, lead_min=lead, contrast=name, CMI_bits=pt, lo=lo, hi=hi,
                                 ci_excludes_0=bool(lo > 0), p_boot=R.boot_p(d)))
    return pd.DataFrame(rows)


def oof_ll(Xv, y, fold, learner, seed):
    p = np.zeros(len(y))
    for f in np.unique(fold):
        tr, te = fold != f, fold == f
        p[te] = models_mod.make_learner(learner, seed).fit(Xv[tr], y[tr]).predict_proba(Xv[te])[:, 1]
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).mean())


def perm_null(df, n_perm, rng, learner="hgb"):
    rows = []
    d0 = df[df[f"label_{PRIMARY_LABEL}"].notna()]
    for lead, dl in d0.groupby("lead_min"):
        dl = dl.reset_index(drop=True)
        fs = models_mod.feature_sets(dl)
        y = dl[f"label_{PRIMARY_LABEL}"].values.astype(int)
        fold = models_mod.day_folds(dl["day"].values, N_CV_FOLDS, np.random.default_rng(RANDOM_SEED))
        days = dl["day"].values
        for name, z, xz in CONTRASTS:
            if name.startswith("PLACEBO") or z not in fs or xz not in fs:
                continue
            zc, xzc = fs[z], fs[xz]
            xcols = [c for c in xzc if c not in zc]
            if not xcols:
                continue
            ll_z = oof_ll(dl[zc].values.astype(float), y, fold, learner, RANDOM_SEED)
            full = dl[xzc].copy()
            obs = (ll_z - oof_ll(full.values.astype(float), y, fold, learner, RANDOM_SEED)) / R.LN2
            for scope in ("global", "within_day"):
                null = []
                for _ in range(n_perm):
                    if scope == "global":
                        perm = rng.permutation(len(dl))
                    else:
                        perm = np.arange(len(dl))
                        for dd in np.unique(days):
                            ix = np.where(days == dd)[0]; perm[ix] = rng.permutation(ix)
                    Xp = full.copy()
                    Xp[xcols] = full[xcols].values[perm]
                    null.append((ll_z - oof_ll(Xp.values.astype(float), y, fold, learner, RANDOM_SEED)) / R.LN2)
                null = np.array(null)
                rows.append(dict(lead_min=lead, contrast=name, scope=scope, CMI_bits_obs=obs, null_mean=null.mean(),
                                 null_q95=np.quantile(null, 0.95), p_perm=(1 + (null >= obs).sum()) / (n_perm + 1)))
        print(f"null done for lead {lead}", flush=True)
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-perm", type=int, default=30)
    ap.add_argument("--nboot", type=int, default=N_BOOT)
    ap.add_argument("--skip-null", action="store_true")
    a = ap.parse_args()
    rng = np.random.default_rng(RANDOM_SEED)
    df = pd.read_csv(DATASET_FILE)
    if "sw" in df and df["sw"].nunique() > 1:      # subsampled-negatives dataset: kNN-MI and refit nulls are not weight-aware
        print("weighted (subsampled) dataset: skipping variable-level MI and permutation nulls; group CMI uses sampling weights")
        a.skip_null = True
    else:
        variable_mi(df, a.n_perm, rng).to_csv(PROCESSED / "info_variable_mi.csv", index=False)
    g, _ = R.load_oof(OOF_FILE)
    cm = group_cmi(g, a.nboot)
    cm.to_csv(PROCESSED / "info_group_cmi.csv", index=False)
    if not a.skip_null:
        perm_null(df, a.n_perm, rng).to_csv(PROCESSED / "info_group_null.csv", index=False)
    pr = cm[(cm.label == PRIMARY_LABEL) & (cm.learner == PRIMARY_LEARNER)]
    print(pr.pivot(index="contrast", columns="lead_min", values="CMI_bits").round(3).to_string())


if __name__ == "__main__":
    main()
