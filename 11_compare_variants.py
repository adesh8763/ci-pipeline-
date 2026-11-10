"""Step 11: do the conclusions survive changes to the CI DEFINITION itself (candidate threshold, precursor radius,
look-back, radar range)?  Collects claim verdicts from every data/processed/<tag>/contrasts.csv.

    python 11_compare_variants.py     -> data/processed/variant_comparison.csv
"""
import pandas as pd
from config import DATA, PRIMARY_LABEL, PRIMARY_LEARNER

rows = []
for f in sorted((DATA / "processed").glob("*/contrasts.csv")):
    tag = f.parent.name
    c = pd.read_csv(f)
    c = c[(c.label == PRIMARY_LABEL) & (c.learner == PRIMARY_LEARNER) & (c.metric == "AUC")]
    c["variant"] = tag
    rows.append(c[["variant", "claim", "lead_min", "delta", "lo", "hi", "verdict", "n", "n_pos", "n_days"]])
out = pd.concat(rows)
out.to_csv(DATA / "processed" / "variant_comparison.csv", index=False)
key = out[out.claim.isin(["atm adds beyond sat+radar", "sat adds beyond radar", "radar adds beyond sat", "imerg adds beyond M5"])]
print(key.pivot_table(index=["claim", "lead_min"], columns="variant", values="delta").round(3).to_string())
print("\nverdicts:")
print(key.pivot_table(index=["claim", "lead_min"], columns="variant", values="verdict", aggfunc="first").to_string())
