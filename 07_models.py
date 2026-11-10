"""Step 7: fit all models with REPEATED, DAY-BLOCKED cross-validation and save out-of-fold (OOF) probabilities.
Everything downstream (information gain, bootstrap CIs, lead-time sensitivity, operational relevance) is computed from
these OOF predictions, so no result ever comes from data a model was trained on.

Models (feature sets)                                          purpose
  M0   ctx                          diurnal cycle + radar range  baseline: how much skill is just time-of-day?
  M1   sat        M2   radar        M3   sat+atm      M4   sat+radar     (proposal models)
  M5   sat+radar+atm              M6   M5 - ATM_DROP groups   (proposal)
  A    atm only   RA   radar+atm   P    imerg only
  M7   M5 + imerg                 M4P  sat+radar+imerg
  M4c  M4 + ctx   M5c  M5 + ctx    confounder-controlled versions (atm test is M5c vs M4c)
  M6_no_<g>   M5 minus ONE atmospheric sub-group g (data-driven replacement for the hand-picked M6)
  M5_shufatm, M3_shufatm   atmosphere replaced by that of a RANDOM OTHER DAY at the same hour (placebo control)

Scope: PRIMARY label x all learners; every other label definition x PRIMARY learner only.
Folds are blocks of whole days (so cells from one day never straddle train/test); each repeat re-draws the blocks.

    python 07_models.py [--repeats 5] [--quick]
"""
import argparse
import warnings
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from config import *
from variables import columns, atm_columns, ATM_SUBGROUPS, atm_subgroup

warnings.filterwarnings("ignore")


def make_learner(name, seed):
    if name == "logit":
        return make_pipeline(SimpleImputer(strategy="median"), StandardScaler(),
                             LogisticRegression(C=0.1, max_iter=2000))
    if name == "hgb":
        return HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=150, l2_regularization=1.0,
                                              min_samples_leaf=15, random_state=seed)
    if name == "rf":
        return make_pipeline(SimpleImputer(strategy="median"),
                             RandomForestClassifier(300, min_samples_leaf=5, max_features="sqrt", n_jobs=-1, random_state=seed))
    raise ValueError(name)


def feature_sets(df):
    sat, rad, atm = columns(df, "sat"), columns(df, "radar"), columns(df, "atm")
    prc, ctx = columns(df, "precip"), columns(df, "ctx")
    drop = atm_columns(df, M6_DROP_ATM_GROUPS)
    fs = {"M0": ctx, "M1": sat, "M2": rad, "M3": sat + atm, "M4": sat + rad, "M5": sat + rad + atm,
          "M6": sat + rad + [a for a in atm if a not in drop], "A": atm, "RA": rad + atm,
          "M4c": sat + rad + ctx, "M5c": sat + rad + atm + ctx}
    if prc:
        fs.update({"P": prc, "M7": sat + rad + atm + prc, "M4P": sat + rad + prc})
    present = sorted({atm_subgroup(c) for c in atm})
    for g in present:
        fs[f"M6_no_{g}"] = sat + rad + [a for a in atm if atm_subgroup(a) != g]
    fs["M5_shufatm"] = sat + rad + atm   # columns replaced by placebo values below
    fs["M3_shufatm"] = sat + atm
    return {k: v for k, v in fs.items() if v}


def placebo_atm(d, rng):
    """For each row take the ERA5 vector of a random row from a DIFFERENT day within +/-1 h of the same hour."""
    atm = columns(d, "atm")
    hour = np.arctan2(d["ctx_hour_sin"].values, d["ctx_hour_cos"].values) % (2 * np.pi) * 24 / (2 * np.pi)
    days = d["day"].values
    out = d[atm].copy()
    for i in range(len(d)):
        dh = np.abs(((hour - hour[i]) + 12) % 24 - 12)
        cand = np.where((dh <= 1.0) & (days != days[i]))[0]
        if cand.size == 0:
            cand = np.where(days != days[i])[0]
        out.iloc[i] = d[atm].iloc[rng.choice(cand)].values
    return out


def prior_correct(p, q):
    """Negatives were kept with probability q (positives all kept). Training on the subsample inflates the odds of a
    positive by 1/q; undo it (King & Zeng 2001 prior correction). Equivalent to weighting, but ~15x faster to fit."""
    return q * p / (q * p + (1 - p)) if q < 1 else p


CORE = {"M0", "M1", "M2", "M3", "M4", "M5", "M6", "M7", "M4c", "M5c", "A", "RA", "P", "M4P"}


def day_folds(days, n_folds, rng):
    ud = np.unique(days)
    rng.shuffle(ud)
    fold_of = {d: i % n_folds for i, d in enumerate(ud)}
    return np.array([fold_of[d] for d in days])


def run_one(d, label, lead, learner, repeats, models, shuf_cache):
    y = d[f"label_{label}"].values.astype(int)
    sw = d["sw"].values.astype(float) if "sw" in d else np.ones(len(d))
    q = 1.0 / sw[y == 0].mean() if (sw.max() > 1) else 1.0           # negative keep-rate implied by the sampling weights
    if y.min() == y.max() or len(np.unique(d["day"])) < N_CV_FOLDS:
        return []
    rows = []
    for name, cols in models.items():
        X = d[cols].copy()
        if name.endswith("_shufatm"):
            X[columns(d, "atm")] = shuf_cache
        Xv = X.values.astype(float)
        for r in range(repeats):
            rng = np.random.default_rng(RANDOM_SEED + 1000 * r)
            fold = day_folds(d["day"].values, N_CV_FOLDS, rng)
            p = np.full(len(d), np.nan)
            for f in range(N_CV_FOLDS):
                tr, te = fold != f, fold == f
                if len(np.unique(y[tr])) < 2:
                    p[te] = prior_correct(np.array([y[tr].mean()]), q)[0]; continue
                clf = make_learner(learner, RANDOM_SEED + r).fit(Xv[tr], y[tr])
                p[te] = prior_correct(clf.predict_proba(Xv[te])[:, 1], q)
            rows.append(pd.DataFrame(dict(label=label, lead_min=lead, learner=learner, model=name, repeat=r,
                                          event_id=d["event_id"].values, day=d["day"].values, y=y, sw=sw, p=p)))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeats", type=int, default=N_CV_REPEATS)
    ap.add_argument("--quick", action="store_true", help="primary label + primary learner only")
    ap.add_argument("--core", action="store_true", help="only the core models (skip ablations / placebo) - use for the big whole-domain dataset")
    a = ap.parse_args()
    df = pd.read_csv(DATASET_FILE)
    labels = [PRIMARY_LABEL] + ([] if a.quick else [n for n in LABEL_DEFS if n != PRIMARY_LABEL])
    if f"label_{LABEL_IMERG}" in df and not a.quick:
        labels.append(LABEL_IMERG)
    out = []
    for lead, dl in df.groupby("lead_min"):
        models = feature_sets(dl)
        if a.core:
            models = {k: v for k, v in models.items() if k in CORE}
        for label in labels:
            if f"label_{label}" not in dl:
                continue
            d = dl[dl[f"label_{label}"].notna()].reset_index(drop=True)
            if len(d) < 50:
                continue
            shuf = placebo_atm(d, np.random.default_rng(RANDOM_SEED)) if (columns(d, "atm") and "M5_shufatm" in models) else None
            learners = LEARNERS if (label == PRIMARY_LABEL and not a.quick) else [PRIMARY_LEARNER]
            for learner in learners:
                out += run_one(d, label, lead, learner, a.repeats, models, shuf)
                print(f"lead {lead:>3} | {label:<16} | {learner:<5} | n={len(d)} | prev={d[f'label_{label}'].mean():.2f}", flush=True)
    res = pd.concat(out, ignore_index=True)
    res.to_csv(OOF_FILE, index=False)
    print("saved", OOF_FILE, res.shape)


if __name__ == "__main__":
    main()
