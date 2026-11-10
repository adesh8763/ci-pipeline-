"""Step 10: figures + an auto-generated robustness report (all numbers come straight from the result tables).

    python 10_figures_report.py
"""
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from config import *

# colour-blind-safe categorical order (Okabe-Ito), fixed per model so colours never move between figures
COL = {"M0": "#7f7f7f", "M1": "#0072B2", "M2": "#D55E00", "M4": "#009E73", "M5": "#CC79A7", "M7": "#E69F00", "M6": "#56B4E9"}
plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
                     "grid.alpha": .25, "figure.dpi": 130, "savefig.bbox": "tight"})
P = PROCESSED
sk = pd.read_csv(P / "model_skill.csv")
con = pd.read_csv(P / "contrasts.csv")
prim = sk[(sk.label == PRIMARY_LABEL) & (sk.learner == PRIMARY_LEARNER)]


def md(df, floatfmt="{:.2f}"):
    df = df.copy()
    cols = [str(c) for c in df.columns]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for vals in df.astype(object).values:
        lines.append("| " + " | ".join(floatfmt.format(v) if isinstance(v, (float, np.floating)) else str(v) for v in vals) + " |")
    return "\n".join(lines)


# ---------------------------------------------------------------- Fig 1: skill vs lead with CIs
def fig_skill(metric="AUC"):
    fig, ax = plt.subplots(figsize=(6, 3.8))
    for m in ["M0", "M1", "M2", "M4", "M5", "M7"]:
        d = prim[(prim.model == m) & (prim.metric == metric)].sort_values("lead_min")
        if d.empty:
            continue
        ax.fill_between(d.lead_min, d.lo, d.hi, color=COL[m], alpha=.15, lw=0)
        ax.plot(d.lead_min, d.value, color=COL[m], lw=1.8, marker="o", ms=4)
        ax.annotate(m, (d.lead_min.min(), d.value.iloc[0]), xytext=(-4, 0), textcoords="offset points", ha="right", va="center", color=COL[m], fontsize=8)
    ax.axhline(0.5 if metric == "AUC" else 0, color="k", lw=.8, ls=":")
    ax.invert_xaxis(); ax.set_xlabel("lead time before first echo (min)"); ax.set_ylabel(f"{metric} (out-of-fold, 95% day-bootstrap CI)")
    ax.set_title(f"Skill vs lead time - {PRIMARY_LABEL}, {PRIMARY_LEARNER}", loc="left")
    fig.savefig(FIGDIR / f"fig1_skill_vs_lead_{metric}.png"); plt.close(fig)


# ---------------------------------------------------------------- Fig 2: useful lead vs threshold
def fig_useful():
    ul = pd.read_csv(P / "useful_lead_grid.csv")
    ul = ul[(ul.label == PRIMARY_LABEL) & (ul.learner == PRIMARY_LEARNER)]
    models = [m for m in ["M0", "M1", "M2", "M4", "M5", "M7"] if m in ul.model.unique()]
    order = list(dict.fromkeys(ul.criterion))
    z = ul.pivot(index="criterion", columns="model", values="useful_lead_conservative").loc[order, models]
    fig, ax = plt.subplots(figsize=(1.0 + 0.8 * len(models), 0.35 * len(order) + 1.2))
    im = ax.imshow(z.values, cmap="Blues", vmin=0, vmax=max(LEADS), aspect="auto")
    ax.set_xticks(range(len(models))); ax.set_xticklabels(models); ax.set_yticks(range(len(order))); ax.set_yticklabels(order)
    ax.grid(False)
    for i in range(z.shape[0]):
        for j in range(z.shape[1]):
            v = z.values[i, j]
            ax.text(j, i, "-" if v == 0 else int(v), ha="center", va="center", fontsize=8, color="white" if v > 100 else "black")
    ax.set_title("Useful lead time (min) vs usefulness criterion\n(lower 95% CI bound must clear the threshold; '-' = never useful)", loc="left", fontsize=9)
    fig.savefig(FIGDIR / "fig2_useful_lead_sensitivity.png"); plt.close(fig)


# ---------------------------------------------------------------- Fig 3: paired differences vs SMD
def fig_forest(metric="AUC"):
    c = con[(con.label == PRIMARY_LABEL) & (con.learner == PRIMARY_LEARNER) & (con.metric == metric)]
    claims = [x for x in c.claim.unique() if not x.startswith("atm group")]
    leads = sorted(c.lead_min.unique())
    fig, axes = plt.subplots(1, len(leads), figsize=(2.0 * len(leads) + 3, 0.38 * len(claims) + 1.4), sharey=True, sharex=True)
    axes = np.atleast_1d(axes)
    smd = SMD.get(metric, 0.02)
    for ax, L in zip(axes, leads):
        ax.axvspan(-smd, smd, color="#999", alpha=.2, lw=0)
        ax.axvline(0, color="k", lw=.8)
        for i, cl in enumerate(claims):
            r = c[(c.claim == cl) & (c.lead_min == L)]
            if r.empty:
                continue
            r = r.iloc[0]
            ax.plot([r.lo, r.hi], [i, i], color="#0072B2", lw=2)
            ax.plot(r.delta, i, "o", color="#0072B2", ms=4)
        ax.set_title(f"{L} min", fontsize=8)
    axes[0].set_yticks(range(len(claims))); axes[0].set_yticklabels(claims, fontsize=7); axes[0].invert_yaxis()
    fig.supxlabel(f"paired difference in {metric} (A - B), 95% CI; grey band = smallest meaningful difference (+/-{smd})", fontsize=8)
    fig.savefig(FIGDIR / f"fig3_paired_differences_{metric}.png"); plt.close(fig)


# ---------------------------------------------------------------- Fig 4: claim stability
def fig_stability():
    st = pd.read_csv(P / "claim_stability.csv", index_col=0)
    order = ["meaningful gain", "negligible gain", "equivalent", "inconclusive", "negligible loss", "meaningful loss"]
    colors = ["#08519c", "#6baed6", "#d9d9d9", "#969696", "#fdae6b", "#d94801"]
    st = st[[c for c in order if c in st.columns] + ["n_tests"]]
    fig, ax = plt.subplots(figsize=(7, 0.32 * len(st) + 1.4))
    left = np.zeros(len(st))
    for c, col in zip([c for c in order if c in st.columns], colors):
        ax.barh(range(len(st)), st[c].values, left=left, color=col, edgecolor="white", label=c, height=.75)
        left += st[c].values
    ax.set_yticks(range(len(st))); ax.set_yticklabels(st.index, fontsize=7); ax.invert_yaxis()
    ax.set_xlabel("share of settings (labels x learners x leads x metrics)"); ax.grid(False)
    ax.legend(ncol=3, fontsize=7, loc="upper center", bbox_to_anchor=(0.4, -0.12), frameon=False)
    ax.set_title("How robust is each claim?", loc="left")
    fig.savefig(FIGDIR / "fig4_claim_stability.png"); plt.close(fig)


# ---------------------------------------------------------------- Fig 5: conditional information
def fig_cmi():
    cm = pd.read_csv(P / "info_group_cmi.csv")
    cm = cm[(cm.label == PRIMARY_LABEL) & (cm.learner == PRIMARY_LEARNER)]
    nullf = P / "info_group_null.csv"
    nl = pd.read_csv(nullf) if nullf.exists() else None
    show = ["sat | radar", "radar | sat", "atm | sat+radar", "atm | sat+radar+ctx", "PLACEBO atm | sat+radar", "imerg | sat+radar+atm"]
    show = [s for s in show if s in cm.contrast.unique()]
    fig, axes = plt.subplots(1, len(show), figsize=(2.3 * len(show), 3), sharey=True)
    axes = np.atleast_1d(axes)
    for ax, s in zip(axes, show):
        d = cm[cm.contrast == s].sort_values("lead_min")
        ax.axhline(0, color="k", lw=.8)
        ax.errorbar(d.lead_min, d.CMI_bits, yerr=[d.CMI_bits - d.lo, d.hi - d.CMI_bits], fmt="o-", color="#0072B2", ms=4, lw=1.4, capsize=2)
        if nl is not None:
            q = nl[(nl.contrast == s) & (nl.scope == "within_day")].sort_values("lead_min")
            if not q.empty:
                ax.plot(q.lead_min, q.null_q95, color="#999", ls="--", lw=1)
        ax.invert_xaxis(); ax.set_title(s, fontsize=8); ax.set_xlabel("lead (min)")
    axes[0].set_ylabel("conditional information (bits/event)")
    fig.suptitle("I(X; CI | Z): blue = estimate with 95% CI; dashed = 95th pct of within-day permutation null", fontsize=8, x=0.01, ha="left")
    fig.savefig(FIGDIR / "fig5_conditional_information.png"); plt.close(fig)


# ---------------------------------------------------------------- report
def report():
    L = [f"# Robustness report ({TAG})", "",
         f"Primary setting: label `{PRIMARY_LABEL}`, learner `{PRIMARY_LEARNER}`, out-of-fold predictions from "
         f"{N_CV_REPEATS}x repeated {N_CV_FOLDS}-fold day-blocked CV; CIs from a {N_BOOT}-resample day-cluster bootstrap.", ""]
    n = prim.drop_duplicates("lead_min")[["lead_min", "n", "n_pos", "n_days"]].sort_values("lead_min", ascending=False)
    L += ["## Sample size", md(n.assign(prevalence=(n.n_pos / n.n).round(2)), "{:.2f}"), "",
          "Effective sample size is the number of *days*, not events; read every interval with that in mind.", ""]
    main_models = ["M0", "M1", "M2", "M3", "M4", "M5", "M5c", "M5_shufatm", "M6", "M7"]
    t = prim[(prim.metric == "AUC") & prim.model.isin(main_models)].assign(txt=lambda d: d.apply(lambda r: f"{r.value:.3f} [{r.lo:.3f},{r.hi:.3f}]", axis=1))
    L += ["## AUC by model and lead [95% CI]", md(t.pivot(index="model", columns="lead_min", values="txt").reset_index()), ""]
    ul = pd.read_csv(P / "useful_lead_grid.csv")
    u = ul[(ul.label == PRIMARY_LABEL) & (ul.learner == PRIMARY_LEARNER) & ul.model.isin(["M1", "M2", "M4", "M5", "M7"])]
    s = u.groupby(["tier", "model"]).useful_lead_conservative.agg(["min", "median", "max"]).reset_index()
    L += ["## Useful lead time by criterion tier (conservative: lower CI bound; tiers explained in THRESHOLDS.md)",
          md(s, "{:.0f}"), "",
          "Tier 1/2 are justified criteria; tier 3 is a sensitivity grid, NOT literature thresholds. "
          "If min and max differ a lot, the 'useful lead time' is a statement about the threshold, not about the data.", ""]
    rs, es = P / "ranking_stability.csv", P / "equivalence_summary.csv"
    if rs.exists():
        r = pd.read_csv(rs); r = r[(r.label == PRIMARY_LABEL) & (r.learner == PRIMARY_LEARNER)].sort_values("lead_min", ascending=False)
        L += ["## Is the model ranking robust to the criterion? (09b)",
              md(r[["lead_min", "n_criteria", "n_distinct_top_models", "top_model_shares", "mean_kendall_tau", "share_top_agrees_with_AUC"]], "{:.2f}"), "",
              "Several different 'best' models across criteria = the ranking is NOT robust; report the models as operationally indistinguishable.", ""]
    if es.exists():
        e = pd.read_csv(es); e = e[(e.label == PRIMARY_LABEL) & (e.learner == PRIMARY_LEARNER) & (e.metric == "AUC")].sort_values("lead_min", ascending=False)
        L += ["## Share of model pairs that are operationally equivalent (AUC difference CI inside +/-SMD)",
              md(e[["lead_min", "n_pairs", "share_equivalent", "share_negligible", "share_inconclusive", "share_meaningful"]], "{:.2f}"), ""]
    g = pd.read_csv(P / "useful_lead_gain_atm.csv")
    L += ["## Does adding variables lengthen the useful lead time? (share of criteria x settings)", md(g), ""]
    st = pd.read_csv(P / "claim_stability.csv")
    L += ["## Claim stability (share of settings per verdict)", md(st), ""]
    ops = pd.read_csv(P / "ops_translation.csv")
    ops = ops[ops.claim.isin(["atm adds beyond sat+radar", "sat adds beyond radar", "imerg adds beyond M5", "reduced atm M6 vs full M5"])]
    L += ["## Operational translation (primary setting)",
          "Positive extra events = more CI events caught at fixed false-alarm ratio 0.4; false-alarm change is per 100 warnings at POD 0.7 (negative = fewer false alarms).",
          md(ops[["claim", "lead_min", "n_true_CI_events", "extra_events_detected", "extra_events_lo", "extra_events_hi", "false_alarms_per_100_warnings", "verdict_POD"]]), ""]
    nf = P / "info_group_null.csv"
    if nf.exists():
        nl = pd.read_csv(nf)
        L += ["## Permutation null for conditional information (bits/event)",
              md(nl[nl.scope == "within_day"][["lead_min", "contrast", "CMI_bits_obs", "null_q95", "p_perm"]], "{:.3f}"), ""]
    L += ["## Caveats to state in the paper",
          "- ERA5 (0.25 deg, hourly) is coarse relative to a single cell: a small atmospheric contribution may reflect representativeness, not physics.",
          "- ~6 weeks of one radar: results describe coastal Senegal in this period; generalisation needs other seasons/sites.",
          "- Radar features at lead <= LOOKBACK_MIN are truncated by the detection rule (no >= first-echo dBZ within 15 km), so they cannot reveal an already-growing cell.",
          "- IMERG is itself partly satellite-IR derived and coarse (0.1 deg/30 min): treat it as a coarse wet-surface/cross-check variable.",
          "- Operating-point metrics (POD@FAR) are evaluated on the pooled OOF predictions; thresholds are not tuned on held-out data.", ""]
    (P / "robustness_report.md").write_text("\n".join(L))
    print("wrote", P / "robustness_report.md")


if __name__ == "__main__":
    fig_skill("AUC"); fig_skill("BSS"); fig_useful(); fig_forest("AUC"); fig_forest("POD@FAR0.4"); fig_stability(); fig_cmi(); report()
    print("figures in", FIGDIR)
