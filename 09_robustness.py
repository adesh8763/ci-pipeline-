"""Step 9: robustness of the SKILL conclusions (answers the supervisor's two main points).

 (A) Sensitivity of "useful lead time" to the usefulness thresholds
       -> useful_lead_grid.csv, useful_lead_gain_atm.csv
 (B) Are small score differences between models real AND operationally relevant?
       -> contrasts.csv (paired day-cluster bootstrap, Holm-adjusted, classified against a smallest meaningful
          difference), claim_stability.csv (how often each claim survives across labels/learners/leads/metrics),
          ops_translation.csv (differences converted to events / false alarms per season)
 (C) CV-partition noise -> cv_repeat_sd.csv, model_skill.csv (all metrics with CIs)

    python 09_robustness.py [--nboot 1000]
"""
import argparse
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from config import *
import robust_lib as R

# (name, A, B, meaning).  delta = metric(A) - metric(B);  "gain" means A is better.
CLAIMS = [
    ("sat adds beyond radar",            "M4",  "M2"),
    ("radar adds beyond sat",            "M4",  "M1"),
    ("atm adds beyond sat",              "M3",  "M1"),
    ("atm adds beyond sat+radar",        "M5",  "M4"),
    ("atm adds beyond sat+radar | ctx",  "M5c", "M4c"),
    ("atm vs placebo atm (sat+radar)",   "M5",  "M5_shufatm"),
    ("atm vs placebo atm (sat)",         "M3",  "M3_shufatm"),
    ("reduced atm M6 vs full M5",        "M6",  "M5"),
    ("imerg adds beyond sat+radar",      "M4P", "M4"),
    ("imerg adds beyond M5",             "M7",  "M5"),
    ("sat+radar beats diurnal baseline", "M4",  "M0"),
    ("M5 beats diurnal baseline",        "M5",  "M0"),
]
KEY_METRICS = ["AUC", "BSS", "POD@FAR0.4", "VALUE_AREA"]   # replaced by AUC/BSS/VALUE_AREA for the weighted whole-domain dataset
HIGHER_BETTER = {"AUC": True, "BSS": True, "POD@FAR0.4": True, "VALUE_AREA": True, "POD@FAR0.5": True, "NB@0.3": True,
                 "FAR@POD0.7": False, "LOGLOSS": False}


def criteria():
    """(metric column, label, threshold, tier). Tier decides how the choice is justified (see THRESHOLDS.md)."""
    c = [("BSS", f"BSS>={b}", b, "1 skill vs climatology" if b == 0 else "3 sensitivity grid") for b in USEFUL_BSS]
    c += [("VALUE_AREA", f"value>={v}", v, "2 economic value") for v in USEFUL_VALUE]
    c += [("AUC", f"AUC>={a}", a, "3 sensitivity grid") for a in USEFUL_AUC]
    c += [(f"POD@FAR{far}", f"POD>={pod}@FAR<={far}", pod, "3 sensitivity grid") for pod, far in USEFUL_POD_FAR]
    return c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nboot", type=int, default=N_BOOT)
    a = ap.parse_args()
    g, raw = R.load_oof(OOF_FILE)
    weighted = g["sw"].nunique() > 1
    global KEY_METRICS
    if weighted:     # base rate ~0.1%: FAR ratios are ~1 for every model, so rank-based and value metrics only
        KEY_METRICS = ["AUC", "BSS", "VALUE_AREA"]

    skill_rows, contrast_rows = [], []
    for label, learner, lead, y, day_idx, P, sw in R.iter_cells(g):
        W = R.boot_weights(day_idx, a.nboot, R.cell_seed(label, learner, lead), sw)
        M = {m: R.metrics_boot(y, p, W) for m, p in P.items()}
        n_days, n, n_pos = int(day_idx.max() + 1), len(y), int(y.sum())
        for m, mm in M.items():
            for met, arr in mm.items():
                pt, lo, hi = R.summarise(arr)
                skill_rows.append(dict(label=label, learner=learner, lead_min=lead, model=m, metric=met,
                                       value=pt, lo=lo, hi=hi, n=n, n_pos=n_pos, n_days=n_days))
        # ---- paired contrasts (claims + every one-atmospheric-group-removed ablation)
        claims = list(CLAIMS) + [(f"atm group '{m[6:]}' adds (M5 vs M5 without it)", "M5", m) for m in M if m.startswith("M6_no_")]
        for name, A, B in claims:
            if A not in M or B not in M:
                continue
            fam = []
            for met in KEY_METRICS + ([] if weighted else ["FAR@POD0.7"]):
                d = M[A][met] - M[B][met]
                hb = HIGHER_BETTER[met]
                smd = SMD["POD_at_FAR"] if met == "FAR@POD0.7" else R.smd_for(met)
                pt, lo, hi = R.summarise(d)
                fam.append(dict(label=label, learner=learner, lead_min=lead, claim=name, A=A, B=B, metric=met,
                                delta=pt, lo=lo, hi=hi, smd=smd, p_boot=R.boot_p(d),
                                prob_ge_smd=float(((d[1:] if hb else -d[1:]) >= smd).mean()),
                                verdict=R.verdict(d, smd, hb), n=n, n_pos=n_pos, n_days=n_days))
            contrast_rows += fam
        print(f"{label:<16}{learner:<6}lead {lead:>3}  n={n:>5} pos={n_pos:>4} days={n_days}", flush=True)

    skill = pd.DataFrame(skill_rows)
    con = pd.DataFrame(contrast_rows)
    # Holm adjustment across all claims inside each (label, learner, lead, metric) family
    con["p_holm"] = np.nan
    for _, idx in con.groupby(["label", "learner", "lead_min", "metric"]).groups.items():
        con.loc[idx, "p_holm"] = R.holm(con.loc[idx, "p_boot"].values)
    skill.to_csv(PROCESSED / "model_skill.csv", index=False)
    con.to_csv(PROCESSED / "contrasts.csv", index=False)

    # ------------------------------------------------------------------ (A) useful lead time vs thresholds
    rows = []
    crit = criteria()
    leads_sorted = sorted(skill.lead_min.unique())
    sk = skill.set_index(["label", "learner", "model", "metric", "lead_min"])
    for (label, learner, model), _ in skill.groupby(["label", "learner", "model"]):
        for metric, cname, thr, tier in crit:
            res = {}
            for bound in ("lo", "value"):
                ok = []
                for L in leads_sorted:
                    try:
                        ok.append(bool(sk.loc[(label, learner, model, metric, L), bound] >= thr))
                    except KeyError:
                        ok.append(False)
                longest_any = max([L for L, o in zip(leads_sorted, ok) if o], default=0)
                contig = 0
                for L, o in zip(leads_sorted, ok):      # contiguous from the shortest lead
                    if not o:
                        break
                    contig = L
                res[bound] = (contig, longest_any)
            rows.append(dict(label=label, learner=learner, model=model, criterion=cname, tier=tier, threshold=thr,
                             useful_lead_conservative=res["lo"][0], useful_lead_any_conservative=res["lo"][1],
                             useful_lead_pointest=res["value"][0]))
    ul = pd.DataFrame(rows)
    ul.to_csv(PROCESSED / "useful_lead_grid.csv", index=False)

    # does the atmosphere lengthen the useful lead? compare across the whole criteria grid
    piv = ul.pivot_table(index=["label", "learner", "criterion"], columns="model", values="useful_lead_conservative")
    gain_rows = []
    for A, B, name in (("M5", "M4", "atm adds (M5 vs M4)"), ("M5c", "M4c", "atm adds | ctx (M5c vs M4c)"),
                       ("M3", "M1", "atm adds to sat (M3 vs M1)"), ("M7", "M5", "imerg adds (M7 vs M5)"),
                       ("M6", "M5", "M6 vs M5")):
        if A in piv and B in piv:
            d = (piv[A] - piv[B]).dropna()
            gain_rows.append(dict(claim=name, n_criteria_x_settings=len(d), share_longer=float((d > 0).mean()),
                                  share_same=float((d == 0).mean()), share_shorter=float((d < 0).mean()),
                                  median_change_min=float(d.median())))
    pd.DataFrame(gain_rows).to_csv(PROCESSED / "useful_lead_gain_atm.csv", index=False)

    # ------------------------------------------------------------------ (B) stability of each claim
    stab = (con[con.metric.isin(KEY_METRICS)]
            .groupby(["claim", "verdict"]).size().unstack(fill_value=0))
    stab = stab.div(stab.sum(axis=1), axis=0).round(3)
    stab["n_tests"] = con[con.metric.isin(KEY_METRICS)].groupby("claim").size()
    stab.to_csv(PROCESSED / "claim_stability.csv")

    # ------------------------------------------------------------------ operational translation (primary setting)
    pr = con[(con.label == PRIMARY_LABEL) & (con.learner == PRIMARY_LEARNER)]
    n_true = skill[(skill.label == PRIMARY_LABEL) & (skill.learner == PRIMARY_LEARNER)].drop_duplicates("lead_min").set_index("lead_min")["n_pos"]
    ops = []
    for (claim, lead), c in pr.groupby(["claim", "lead_min"]):
        r = c.set_index("metric")
        if not weighted and "POD@FAR0.4" in r.index and "FAR@POD0.7" in r.index:
            nt = int(n_true.get(lead, 0))
            ops.append(dict(claim=claim, lead_min=lead, n_true_CI_events=nt,
                            dPOD_at_FAR04=r.loc["POD@FAR0.4", "delta"],
                            extra_events_detected=r.loc["POD@FAR0.4", "delta"] * nt,
                            extra_events_lo=r.loc["POD@FAR0.4", "lo"] * nt, extra_events_hi=r.loc["POD@FAR0.4", "hi"] * nt,
                            dFAR_at_POD07=r.loc["FAR@POD0.7", "delta"],
                            false_alarms_per_100_warnings=100 * r.loc["FAR@POD0.7", "delta"],
                            fa_lo=100 * r.loc["FAR@POD0.7", "lo"], fa_hi=100 * r.loc["FAR@POD0.7", "hi"],
                            verdict_POD=r.loc["POD@FAR0.4", "verdict"], verdict_AUC=r.loc["AUC", "verdict"]))
    pd.DataFrame(ops).to_csv(PROCESSED / "ops_translation.csv", index=False)

    # ------------------------------------------------------------------ (C) CV-partition noise
    rr = []
    for (label, learner, lead, model, rep), c in raw.groupby(["label", "learner", "lead_min", "model", "repeat"]):
        if c.y.nunique() == 2:
            rr.append(dict(label=label, learner=learner, lead_min=lead, model=model, repeat=rep, AUC=roc_auc_score(c.y, c.p)))
    rr = pd.DataFrame(rr)
    rr.groupby(["label", "learner", "lead_min", "model"]).AUC.agg(["mean", "std", "min", "max"]).reset_index() \
        .to_csv(PROCESSED / "cv_repeat_sd.csv", index=False)

    print("\nclaim stability (share of settings per verdict):")
    print(stab.to_string())
    print("\nuseful-lead sensitivity (atmosphere):")
    print(pd.DataFrame(gain_rows).round(2).to_string(index=False))
    print("\nwrote results to", PROCESSED)


if __name__ == "__main__":
    main()
