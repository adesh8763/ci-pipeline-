# CI pipeline v2 - robustness-first, with IMERG

Same data layout as before (`data/raw/{era5,imerg,radar_npol,seviri_tailored}`, `data/interim/seviri_box`).
Run from the folder that contains `data/` (or set `CI_ROOT`). `pip install -r requirements.txt`.

```
python 00_inventory.py        # send me the output if any loader needs adjusting
python variables.py           # variable catalogue -> data/processed/main/variable_catalogue.{csv,md}
01_seviri_features  02_radar_grid  03_era5_features  04_imerg_features   # data -> interim
05_detect_ci        06_build_dataset                                      # events + labels -> table
07_models           08_information   09_robustness   10_figures_report   # analysis
bash run_all.sh [variants]
```
Smoke-test the statistics without real data: `CI_ROOT=/tmp/t python make_synthetic.py && python 07_models.py --quick && python 09_robustness.py && python 10_figures_report.py`.

## How each of Prof. Messori's points is handled

| Comment | What the pipeline does | Where |
|---|---|---|
| "Useful" lead time never tested against the score thresholds | A grid of 15 usefulness criteria (AUC 0.60-0.80, BSS 0-0.20, POD/FAR pairs). A lead is "useful" only if the **lower 95 % CI bound** clears the threshold. Reports the useful lead for every model under every criterion, and whether adding the atmosphere lengthens it in how many criteria. | 09 -> `useful_lead_grid.csv`, `useful_lead_gain_atm.csv`, fig 2 |
| Very small score differences between models: operational relevance? | Paired day-cluster bootstrap of every model difference, Holm-adjusted, classified against a **smallest meaningful difference** (`SMD` in config; set it with your supervisor): *meaningful gain / negligible gain / equivalent / inconclusive / loss*. Differences are converted to extra events caught and false alarms per 100 warnings, plus net benefit. | 09 -> `contrasts.csv`, `ops_translation.csv`, fig 3 |
| Too clear-cut on atmospheric variables | Five independent checks: (1) ctx-controlled test (M5c vs M4c: diurnal cycle + radar range); (2) **placebo atmosphere** (ERA5 from a random other day, same hour); (3) leave-one-atmospheric-group-out ablations instead of a hand-picked M6; (4) conditional information with permutation nulls, *global* and *within-day* (event-specific info beyond the day regime); (5) claim stability across 3 learners x 10 label definitions x 5 leads x 3 metrics. | 07, 08, 09, fig 4-5 |
| "Variables?" | `variables.py` is the single catalogue (source, variable, units, role) and writes a ready-to-paste table. | `variable_catalogue.md` |
| Literature / wording comments | Not code - paper text. The pipeline's output is designed to support more cautious phrasing (see report caveats). | - |

## What IMERG does here
1. **Predictor group** `imerg_*` (rain rate, 3 h accumulation, wet fraction in a 0.3 deg box), only from half-hours that *end* before the forecast time. Models `P`, `M4P` (sat+radar+IMERG), `M7` (M5+IMERG).
2. **Independent label cross-check** `label_imerg_confirmed` (rain >= 2 mm/h in the 60 min after first echo): agreement with the radar rule is printed in step 6, and the same models are run against this label.
3. IMERG is *not* used as a stand-in for radar; it is coarse (0.1 deg, 30 min) and partly IR-derived.

## Robustness design (summary)
* **Splits**: folds are blocks of whole *days*; 5 repeats with re-drawn blocks; no imputation or scaling outside the training fold.
* **Uncertainty**: bootstrap over *days* (not events), identical resamples for all models -> paired differences.
* **Labels**: 3 reflectivity thresholds x 3 growth windows + IMERG-confirmed; events with radar gaps in the growth window are *excluded*, not called "false". Candidate-definition variants (first-echo 20/30 dBZ, precursor radius, look-back, max range 100 km) via `run_all.sh variants` + `11_compare_variants.py`.
* **Learners**: logistic regression, gradient boosting, random forest (primary label).
* **Leakage**: SEVIRI scan + 15 min latency, radar/ERA5 latest <= t_ref, IMERG slot end <= t_ref.
* **Controls with known answers**: `make_synthetic.py` (sat/radar informative, ERA5 day-level only, IMERG noise) - the pipeline recovers this truth.

## Things you must set / know
* `config.py`: `SMD` (smallest meaningful differences) and the CI rules are **placeholders** - take them from the proposal.
* Effective sample size = number of *days* (~43). Intervals are wide by design; do not narrow them by pooling events.
* Radar features at lead <= 30 min are truncated by the detection rule (no echo >= first-echo dBZ within 15 km before the event).
* Step 7 is the slow step (several thousand fits). `--quick` = primary label + learner only; `CI_REPEATS=3` lowers cost.

## Update 2 - second round of comments (thresholds, ranking at 90 min, equivalence, whole-domain)

| Comment | Response | Where |
|---|---|---|
| Are the thresholds from ECMWF / another centre? Cite each source. | No - the first grid was generic. Now tiered: (1) BSS > 0 vs climatology, (2) relative economic value, (3) the old POD/FAR/AUC grid kept only as a labelled sensitivity range. Every choice is listed with its source and status. | `THRESHOLDS.md`, `config.py`, `useful_lead_grid.csv` (column `tier`) |
| 90-min scores are close; a small change in POD/FAR could change the ranking - verify. | Ranking under ~45 criteria (AUC, BSS, value at each cost/loss ratio, POD at FAR 0.20-0.95, FAR at POD 0.40-0.95): number of distinct "best" models, Kendall tau between criteria, share of criteria where A beats B with >= 95 % bootstrap probability ("unresolved" share). | `09b_ranking_equivalence.py` -> `ranking_stability.csv`, `pairwise_order_share.csv`, fig 6 |
| Are the differences at 90 min relevant, or are the models operationally equivalent? | Every model pair classified (equivalent / negligible / inconclusive / meaningful) against the smallest meaningful difference; share of equivalent pairs per lead. | `equivalence_pairs.csv`, `equivalence_summary.csv`, fig 7 |
| Test the conclusion's robustness further. | Claim stability now also over value metric; candidate-definition variants; whole-domain dataset (below). | `claim_stability.csv`, `run_all.sh variants` |
| Use whole-domain data, without centring on tracked cloud objects. | `12_domain_dataset.py`: every 12 km box x 30 min window in the radar domain is a sample (target = a true CI starts there). Negatives subsampled with exact prior correction, weights carried into every metric. | `12_domain_dataset.py` |
| "Where does the dimensionality come in?" | Paper-text question (see the reply in chat). In the pipeline, conditional information is estimated with classifier log-loss differences + permutation nulls instead of density estimation in the joint space of all predictors. | `08_information.py` |

Whole-domain run (after the object-based pipeline): see the header of `12_domain_dataset.py` (needs `CI_TAG=domain CI_PRIMARY_LABEL=domain_true`).
At a base rate of ~0.1 % the false-alarm RATIO is ~1 for any model, so for this dataset only AUC, BSS and economic value are reported.
