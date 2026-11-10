#!/usr/bin/env bash
# Full v2 pipeline. Run from the project root (the folder that contains data/):
#   bash ci_pipeline_v2/run_all.sh            # main run
#   bash ci_pipeline_v2/run_all.sh variants   # + label/candidate-definition sensitivity runs (steps 5-10 only)
set -euo pipefail
S="$(cd "$(dirname "$0")" && pwd)"
cd "$(pwd)"
export PYTHONPATH="$S"

python "$S/00_inventory.py"          # look at the output once; fix channel / variable names if needed
python "$S/variables.py"             # variable catalogue (paper's data section)
python "$S/01_seviri_features.py"
python "$S/02_radar_grid.py" --workers 4
python "$S/03_era5_features.py"
python "$S/04_imerg_features.py"
python "$S/05_detect_ci.py"
python "$S/06_build_dataset.py"
python "$S/07_models.py"             # slow step; --quick for a smoke test
python "$S/08_information.py"        # --skip-null for a fast pass
python "$S/09_robustness.py"
python "$S/09b_ranking_equivalence.py"
python "$S/10_figures_report.py"

if [ "${1:-}" = "variants" ]; then
  # candidate-definition and QC sensitivity: each variant writes to data/processed/<tag>/
  for spec in "fe20 CI_FIRST_ECHO=20" "fe30 CI_FIRST_ECHO=30" "range100 CI_MAX_RANGE_KM=100" \
              "prec10 CI_PRECURSOR_KM=10" "prec20 CI_PRECURSOR_KM=20" "look45 CI_LOOKBACK_MIN=45"; do
    tag="${spec%% *}"; var="${spec#* }"
    echo "=== variant $tag ($var) ==="
    for s in 05_detect_ci 06_build_dataset 07_models 08_information 09_robustness 09b_ranking_equivalence 10_figures_report; do
      env CI_TAG="$tag" "$var" python "$S/$s.py" $( [ "$s" = 07_models ] && echo "--quick" ) $( [ "$s" = 08_information ] && echo "--skip-null" )
    done
  done
  python "$S/11_compare_variants.py"
fi

if [ "${1:-}" = "domain" ] || [ "${1:-}" = "variants" ]; then
  # whole-domain (object-free) analysis; needs data/processed/main/ci_events.csv from the main run
  export CI_TAG=domain CI_PRIMARY_LABEL=domain_true
  python "$S/12_domain_dataset.py"
  python "$S/07_models.py" --quick --core --repeats 3
  python "$S/08_information.py" --skip-null
  python "$S/09_robustness.py"
  python "$S/09b_ranking_equivalence.py"
  python "$S/10_figures_report.py"
fi
