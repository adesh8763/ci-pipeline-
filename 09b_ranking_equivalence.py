"""Step 9b: is the MODEL RANKING (and the "which model is best at 90 min?" conclusion) robust, or an artefact of
the particular POD / FAR / AUC / value criterion?  And are the differences operationally relevant at all?

For every (label, learner, lead) cell and the headline models M1..M7:
  1. ranking_by_criterion.csv   rank + bootstrap P(best) under ~45 criteria: AUC, BSS, log-loss, mean economic value,
                                value at each cost/loss ratio, POD at FAR 0.20..0.95, FAR at POD 0.40..0.95
  2. ranking_stability.csv      how many different models come out on top, rank correlation (Kendall tau) between
                                criteria, share of criteria that agree with the AUC ranking
  3. pairwise_order_share.csv   for each model pair: share of criteria where A beats B (point estimate) and where the
                                bootstrap says so with >= 95 % probability -> "unresolved" share = ranking is NOT robust
  4. equivalence_pairs.csv      paired difference classified against the smallest meaningful difference:
                                equivalent / negligible / inconclusive / meaningful   (answers "operationally equivalent?")
  5. equivalence_summary.csv    share of model pairs that are operationally equivalent, per lead
  fig6_ranking_L<lead>.png, fig7_equivalence_L<lead>.png (primary label + learner)

    python 09b_ranking_equivalence.py [--nboot 1000]
"""
import argparse
import itertools
import numpy as np
import pandas as pd
from scipy.stats import kendalltau, rankdata
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from config import *
import robust_lib as R

HEAD = ["M1", "M2", "M3", "M4", "M5", "M6", "M7"]
EQ_METRICS = ["AUC", "VALUE_AREA", "POD@FAR0.4"]
LOWER_BETTER = lambda k: k.startswith("FAR@") or k == "LOGLOSS"


def family(k):
    for f in ("POD@FAR", "FAR@POD", "V@", "VALUE_AREA", "AUC", "BSS", "LOGLOSS"):
        if k.startswith(f):
            return f
    return k


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nboot", type=int, default=N_BOOT)
    a = ap.parse_args()
    g, _ = R.load_oof(OOF_FILE)
    weighted = g["sw"].nunique() > 1
    eq_metrics = [m for m in EQ_METRICS if not (weighted and m.startswith("POD@"))]
    rk_rows, st_rows, pw_rows, eq_rows, eqs_rows = [], [], [], [], []
    keep = {}

    for label, learner, lead, y, day_idx, P, sw in R.iter_cells(g):
        models = [m for m in HEAD if m in P]
        if len(models) < 3:
            continue
        W = R.boot_weights(day_idx, a.nboot, R.cell_seed(label, learner, lead), sw)
        M = {m: R.metrics_boot(y, P[m], W, dense=True) for m in models}
        crit = [k for k in M[models[0]] if family(k) in ("POD@FAR", "FAR@POD", "V@", "VALUE_AREA", "AUC", "BSS", "LOGLOSS")]
        S = {k: np.stack([(-M[m][k] if LOWER_BETTER(k) else M[m][k]) for m in models]) for k in crit}   # higher = better

        informative, tops, rank_vecs = [], [], {}
        for k in crit:
            pt = S[k][:, 0]
            if pt.max() - pt.min() < 1e-9:
                continue                                                 # criterion cannot separate models (e.g. POD=0 for all)
            ranks = rankdata(-pt, method="average")
            pbest = np.bincount(np.argmax(S[k][:, 1:], axis=0), minlength=len(models)) / (S[k].shape[1] - 1)
            informative.append(k); rank_vecs[k] = ranks; tops.append(models[int(np.argmax(pt))])
            for i, m in enumerate(models):
                rk_rows.append(dict(label=label, learner=learner, lead_min=lead, criterion=k, family=family(k), model=m,
                                    value=float(M[m][k][0]), rank=ranks[i], p_best=pbest[i]))
        if not informative:
            continue
        # ---- rank stability
        taus = [kendalltau(rank_vecs[c1], rank_vecs[c2])[0] for c1, c2 in itertools.combinations(informative, 2)]
        taus = [t for t in taus if np.isfinite(t)]
        auc_top = tops[informative.index("AUC")] if "AUC" in informative else None
        counts = pd.Series(tops).value_counts()
        st_rows.append(dict(label=label, learner=learner, lead_min=lead, n_criteria=len(informative),
                            n_distinct_top_models=int(counts.size), top_model_shares="; ".join(f"{m}:{c/len(tops):.2f}" for m, c in counts.items()),
                            mean_kendall_tau=float(np.mean(taus)) if taus else np.nan, min_kendall_tau=float(np.min(taus)) if taus else np.nan,
                            share_top_agrees_with_AUC=float(np.mean([t == auc_top for t in tops])) if auc_top else np.nan))
        # ---- pairwise order share
        for A, B in itertools.combinations(models, 2):
            ia, ib = models.index(A), models.index(B)
            better = conf_a = conf_b = 0
            for k in informative:
                pa = float((S[k][ia, 1:] > S[k][ib, 1:]).mean())
                better += S[k][ia, 0] > S[k][ib, 0]
                conf_a += pa >= 0.95; conf_b += pa <= 0.05
            n = len(informative)
            pw_rows.append(dict(label=label, learner=learner, lead_min=lead, A=A, B=B, n_criteria=n,
                                share_A_better_point=better / n, share_A_better_conf95=conf_a / n, share_B_better_conf95=conf_b / n,
                                share_unresolved=1 - (conf_a + conf_b) / n))
        # ---- equivalence of every pair on the key metrics
        for A, B in itertools.combinations(models, 2):
            for met in eq_metrics:
                if met not in M[A]:
                    continue
                d = M[A][met] - M[B][met]
                smd = R.smd_for(met)
                pt, lo, hi = R.summarise(d)
                eq_rows.append(dict(label=label, learner=learner, lead_min=lead, A=A, B=B, metric=met, delta=pt, lo=lo, hi=hi,
                                    smd=smd, verdict=R.verdict(d, smd, True), prob_within_smd=float((np.abs(d[1:]) <= smd).mean())))
        if label == PRIMARY_LABEL and learner == PRIMARY_LEARNER:
            keep[lead] = (models, S, informative, M)
        print(f"{label:<16}{learner:<6}lead {lead:>3}: {len(informative)} informative criteria, {counts.size} distinct 'best' models", flush=True)

    pd.DataFrame(rk_rows).to_csv(PROCESSED / "ranking_by_criterion.csv", index=False)
    st = pd.DataFrame(st_rows); st.to_csv(PROCESSED / "ranking_stability.csv", index=False)
    pd.DataFrame(pw_rows).to_csv(PROCESSED / "pairwise_order_share.csv", index=False)
    eq = pd.DataFrame(eq_rows); eq.to_csv(PROCESSED / "equivalence_pairs.csv", index=False)
    for (label, learner, lead, met), c in eq.groupby(["label", "learner", "lead_min", "metric"]):
        v = c.verdict.value_counts(normalize=True)
        eqs_rows.append(dict(label=label, learner=learner, lead_min=lead, metric=met, n_pairs=len(c),
                             share_equivalent=v.get("equivalent", 0), share_negligible=v.get("negligible gain", 0) + v.get("negligible loss", 0),
                             share_inconclusive=v.get("inconclusive", 0), share_meaningful=v.get("meaningful gain", 0) + v.get("meaningful loss", 0)))
    eqs = pd.DataFrame(eqs_rows); eqs.to_csv(PROCESSED / "equivalence_summary.csv", index=False)

    # ------------------------------------------------------------------ figures (primary label + learner)
    for lead, (models, S, informative, M) in keep.items():
        order = [k for f in ("AUC", "BSS", "VALUE_AREA", "V@", "POD@FAR", "FAR@POD") for k in informative if family(k) == f]
        Rk = np.array([[rankdata(-S[k][:, 0])[i] for k in order] for i in range(len(models))])
        fig, ax = plt.subplots(figsize=(0.28 * len(order) + 2, 0.45 * len(models) + 1.6))
        ax.imshow(Rk, cmap="Blues_r", vmin=1, vmax=len(models), aspect="auto")
        ax.set_yticks(range(len(models))); ax.set_yticklabels(models)
        ax.set_xticks(range(len(order))); ax.set_xticklabels([k.replace("POD@FAR", "POD|F").replace("FAR@POD", "FAR|P") for k in order], rotation=90, fontsize=6)
        for i in range(Rk.shape[0]):
            for j in range(Rk.shape[1]):
                ax.text(j, i, int(round(Rk[i, j])), ha="center", va="center", fontsize=6, color="white" if Rk[i, j] > len(models) / 2 else "black")
        ax.grid(False)
        ax.set_title(f"Model rank under each criterion, lead {lead} min (1 = best); {PRIMARY_LABEL}, {PRIMARY_LEARNER}", loc="left", fontsize=8)
        fig.savefig(FIGDIR / f"fig6_ranking_L{lead}.png"); plt.close(fig)

        e = eq[(eq.label == PRIMARY_LABEL) & (eq.learner == PRIMARY_LEARNER) & (eq.lead_min == lead) & (eq.metric == "AUC")]
        n = len(models); Dm = np.full((n, n), np.nan); Cm = np.zeros((n, n))
        cmap = {"equivalent": 0, "negligible gain": 1, "negligible loss": 1, "inconclusive": 2, "meaningful gain": 3, "meaningful loss": 3}
        for _, r in e.iterrows():
            i, j = models.index(r.A), models.index(r.B)
            Dm[i, j], Dm[j, i] = r.delta, -r.delta
            Cm[i, j] = Cm[j, i] = cmap[r.verdict]
        fig, ax = plt.subplots(figsize=(0.75 * n + 2, 0.7 * n + 1.2))
        ax.imshow(Cm, cmap=matplotlib.colors.ListedColormap(["#c7e9c0", "#f7f7f7", "#d9d9d9", "#fdae6b"]), vmin=0, vmax=3)
        for i in range(n):
            for j in range(n):
                if i != j:
                    ax.text(j, i, f"{Dm[i, j]:+.3f}", ha="center", va="center", fontsize=7)
        ax.set_xticks(range(n)); ax.set_xticklabels(models); ax.set_yticks(range(n)); ax.set_yticklabels(models); ax.grid(False)
        ax.set_title(f"AUC(row) - AUC(col), lead {lead} min\ngreen = equivalent (CI within +/-{SMD['AUC']}), white = negligible, grey = inconclusive, orange = meaningful", loc="left", fontsize=8)
        fig.savefig(FIGDIR / f"fig7_equivalence_L{lead}.png"); plt.close(fig)

    p = st[(st.label == PRIMARY_LABEL) & (st.learner == PRIMARY_LEARNER)].sort_values("lead_min", ascending=False)
    print("\nranking stability (primary setting):")
    print(p[["lead_min", "n_criteria", "n_distinct_top_models", "top_model_shares", "mean_kendall_tau", "share_top_agrees_with_AUC"]].round(2).to_string(index=False))
    q = eqs[(eqs.label == PRIMARY_LABEL) & (eqs.learner == PRIMARY_LEARNER) & (eqs.metric == "AUC")].sort_values("lead_min", ascending=False)
    print("\nshare of model pairs that are operationally equivalent / negligible / inconclusive / meaningful (AUC):")
    print(q[["lead_min", "n_pairs", "share_equivalent", "share_negligible", "share_inconclusive", "share_meaningful"]].round(2).to_string(index=False))


if __name__ == "__main__":
    main()
