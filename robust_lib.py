"""Shared statistics for the robustness analysis (no I/O side effects).

All metrics are computed on OUT-OF-FOLD probabilities. Uncertainty comes from a DAY-CLUSTER bootstrap: whole days
are resampled with replacement (events within a day are strongly dependent, so resampling events would give
over-confident intervals). The SAME resamples are applied to every model within a (label, learner, lead) cell, which
makes differences between models PAIRED (much tighter than comparing two independent intervals).

Sampling weights `sw` (whole-domain dataset, where negatives are subsampled) are carried through every metric so that
POD / FAR / value refer to the TRUE base rate, not the subsampled one.
"""
import numpy as np
import pandas as pd
from config import CI_LEVEL, N_BOOT, RANDOM_SEED, SMD

LN2 = np.log(2.0)
FAR_LEVELS = (0.3, 0.4, 0.5, 0.6, 0.7)
POD_LEVELS = (0.5, 0.6, 0.7, 0.8, 0.9)
NB_THRESH = (0.3,)
ALPHAS = tuple(np.round(np.arange(0.05, 0.501, 0.05), 2))     # cost/loss ratios for relative economic value
FAR_DENSE = tuple(np.round(np.arange(0.20, 0.951, 0.05), 2))
POD_DENSE = tuple(np.round(np.arange(0.40, 0.951, 0.05), 2))


# ----------------------------------------------------------------------------------------------- data cells
def load_oof(path):
    """Average the repeated-CV OOF probabilities per event (each is out-of-fold) -> one probability per event."""
    d = pd.read_csv(path)
    if "sw" not in d:
        d["sw"] = 1.0
    keys = ["label", "lead_min", "learner", "model", "event_id"]
    g = d.groupby(keys, as_index=False).agg(p=("p", "mean"), y=("y", "first"), day=("day", "first"), sw=("sw", "first"))
    return g, d


def iter_cells(g):
    """Yield (label, learner, lead, y, day_idx, {model: p}, sw) with identical event order for every model."""
    for (label, learner, lead), c in g.groupby(["label", "learner", "lead_min"]):
        wide = c.pivot(index="event_id", columns="model", values="p")
        meta = c.drop_duplicates("event_id").set_index("event_id").loc[wide.index]
        wide = wide.dropna(axis=1, how="any")
        _, day_idx = np.unique(meta["day"].values, return_inverse=True)
        yield (label, learner, lead, meta["y"].values.astype(int), day_idx,
               {m: wide[m].values for m in wide.columns}, meta["sw"].values.astype(float))


def boot_weights(day_idx, n_boot, seed, sw=None):
    """(n_boot+1, n_events) matrix of resampling weights; row 0 = the point estimate (all ones x sampling weight)."""
    rng = np.random.default_rng(seed)
    nd = day_idx.max() + 1
    counts = np.stack([np.bincount(rng.integers(0, nd, nd), minlength=nd) for _ in range(n_boot)])
    W = np.vstack([np.ones((1, len(day_idx))), counts[:, day_idx].astype(float)])
    if sw is not None:
        W = W * sw[None, :]
    return W


# ----------------------------------------------------------------------------------------------- metrics
def _key(prefix, v):
    return f"{prefix}{round(float(v), 2)}"


def metrics_boot(y, p, W, dense=False):
    """All metrics for one model over all resamples. Returns {metric: array(n_boot+1)}.
    dense=True adds POD@FAR / FAR@POD on a fine grid and value at every cost/loss ratio (used for ranking stability)."""
    eps = 1e-6
    pc = np.clip(p, eps, 1 - eps)
    n_pos = W @ y
    n_neg = W @ (1 - y)
    out = {}
    wsum = W.sum(1)
    ybar = n_pos / wsum
    bs = (W @ ((p - y) ** 2)) / wsum
    out["BSS"] = 1 - bs / np.maximum(ybar * (1 - ybar), 1e-12)
    out["LOGLOSS"] = (W @ (-(y * np.log(pc) + (1 - y) * np.log(1 - pc)))) / wsum
    o = np.argsort(-p, kind="stable")
    ys, Ws = y[o], W[:, o]
    TP = np.cumsum(Ws * ys, axis=1)
    FP = np.cumsum(Ws * (1 - ys), axis=1)
    out["AUC"] = (Ws * (1 - ys) * TP).sum(1) / np.maximum(n_pos * n_neg, 1e-12)
    with np.errstate(divide="ignore", invalid="ignore"):
        FAR = np.where(TP + FP > 0, FP / (TP + FP), 1.0)     # false-alarm RATIO = FP / (TP + FP)
        POD = TP / np.maximum(n_pos[:, None], 1e-12)         # probability of detection
        POFD = FP / np.maximum(n_neg[:, None], 1e-12)        # false-alarm RATE (needed for economic value)
    for far in (FAR_DENSE if dense else FAR_LEVELS):
        out[_key("POD@FAR", far)] = np.where(FAR <= far, POD, 0.0).max(1)
    for pod in (POD_DENSE if dense else POD_LEVELS):
        out[_key("FAR@POD", pod)] = np.where(POD >= pod, FAR, 1.0).min(1)
    for pt in NB_THRESH:
        flag = (p >= pt)
        tp = W @ (y * flag); fp = W @ ((1 - y) * flag)
        out[f"NB@{pt}"] = (tp - fp * pt / (1 - pt)) / wsum
    # ---- potential relative economic value (Richardson 2000): best threshold for each cost/loss ratio alpha
    s = (n_pos / wsum)[:, None]
    vals = []
    for a in ALPHAS:
        E = POFD * a * (1 - s) - POD * s * (1 - a) + s           # expected expense per unit loss, by threshold
        E = np.minimum(E, np.minimum(a, s))                      # may always/never warn -> value never below 0
        Ecl, Ep = np.minimum(a, s), s * a
        v = ((Ecl - E) / np.maximum(Ecl - Ep, 1e-12)).max(1)
        vals.append(v)
        if dense or a in (0.1, 0.3):
            out[_key("V@", a)] = v
    out["VALUE_AREA"] = np.mean(vals, axis=0)
    return out


def summarise(arr, level=CI_LEVEL):
    a = (1 - level) / 2
    return arr[0], np.quantile(arr[1:], a), np.quantile(arr[1:], 1 - a)


def smd_for(metric):
    if metric.startswith("POD@"):
        return SMD["POD_at_FAR"]
    if metric in SMD:
        return SMD[metric]
    if metric.startswith("FAR@"):
        return SMD["POD_at_FAR"]
    if metric.startswith("V") :
        return SMD["BSS"]
    return SMD.get("AUC", 0.02)


def verdict(delta_arr, smd, higher_better=True):
    """Classify a paired difference A-B (positive = A better when higher_better).
    meaningful gain  : CI above 0 and point estimate >= SMD
    negligible gain  : CI above 0 but point estimate < SMD     (statistically detectable, operationally small)
    equivalent       : whole CI inside +/-SMD                   (can be declared 'no practical difference')
    inconclusive     : CI spans 0 and extends beyond +/-SMD     (data cannot tell)
    negligible loss / meaningful loss : mirror images
    """
    d = delta_arr if higher_better else -delta_arr
    pt, lo, hi = summarise(d)
    if lo > 0:
        return "meaningful gain" if pt >= smd else "negligible gain"
    if hi < 0:
        return "meaningful loss" if pt <= -smd else "negligible loss"
    if lo >= -smd and hi <= smd:
        return "equivalent"
    return "inconclusive"


def boot_p(delta_arr):
    d = delta_arr[1:]
    return float(min(1.0, 2 * min((d <= 0).mean(), (d >= 0).mean()) + 1.0 / len(d)))


def holm(pvals):
    p = np.asarray(pvals, float)
    order = np.argsort(p)
    adj = np.empty_like(p)
    run = 0.0
    for rank, i in enumerate(order):
        run = max(run, (len(p) - rank) * p[i])
        adj[i] = min(1.0, run)
    return adj


def cell_seed(label, learner, lead):
    import zlib
    return RANDOM_SEED + zlib.crc32(f"{label}|{learner}|{lead}".encode()) % 10_000_000
