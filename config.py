"""Central configuration for the v2 (robustness-first) CI pipeline.

Run every script from the project root (the folder that contains data/) or set CI_ROOT.
Variants for sensitivity analysis are produced by setting environment variables, e.g.
    CI_TAG=fe20 CI_FIRST_ECHO=20 python 05_detect_ci.py
Outputs of each variant go to data/processed/<tag>/ so variants never overwrite each other.
"""
import os
from pathlib import Path

ROOT = Path(os.environ.get("CI_ROOT", Path.cwd()))
DATA = ROOT / "data"
RAW, INTERIM, LOGS = DATA / "raw", DATA / "interim", DATA / "logs"
TAG = os.environ.get("CI_TAG", "main")
PROCESSED = DATA / "processed" / TAG
FIGDIR = PROCESSED / "figures"

ERA5_DIR, IMERG_DIR = RAW / "era5", RAW / "imerg"
RADAR_DIR, SEVIRI_DIR = RAW / "radar_npol", RAW / "seviri_tailored"
SEVIRI_BOX = INTERIM / "seviri_box"

SEVIRI_FEAT_DIR = INTERIM / "seviri_features"
RADAR_GRID_DIR = INTERIM / "radar_grids"
ERA5_FEAT_FILE = INTERIM / "era5_features.nc"
IMERG_FEAT_FILE = INTERIM / "imerg_precip.nc"

EVENTS_FILE = PROCESSED / "ci_events.csv"
EVENTS_FROM = DATA / "processed" / os.environ.get("CI_EVENTS_FROM", "main") / "ci_events.csv"  # events used by the domain dataset
DATASET_FILE = PROCESSED / "ci_dataset.csv"
OOF_FILE = PROCESSED / "oof_predictions.csv.gz"

for _p in (INTERIM, PROCESSED, FIGDIR, LOGS, SEVIRI_FEAT_DIR, RADAR_GRID_DIR):
    _p.mkdir(parents=True, exist_ok=True)

# ----------------------------------------------------------------------------- study period
START, END = "2006-08-19", "2006-09-30"

# ----------------------------------------------------------------------------- radar grid
GRID_HALF_KM, GRID_RES_KM = 150, 2.0
GRID_Z = (500, 15500, 16)  # m: start, stop, n levels

# ----------------------------------------------------------------------------- CI candidate detection
FIRST_ECHO_DBZ = float(os.environ.get("CI_FIRST_ECHO", 25))   # candidate = new cell reaching this
PRECURSOR_KM = float(os.environ.get("CI_PRECURSOR_KM", 15))   # no echo>=FIRST_ECHO within this radius ...
LOOKBACK_MIN = float(os.environ.get("CI_LOOKBACK_MIN", 30))   # ... during this many minutes before
MIN_AREA_PX = int(os.environ.get("CI_MIN_AREA_PX", 2))
TRACK_KM = float(os.environ.get("CI_TRACK_KM", 25))           # radius around the initiation point searched for growth
MAX_RANGE_KM = float(os.environ.get("CI_MAX_RANGE_KM", 120)) # drop candidates beyond this radar range
MAX_SCAN_GAP_MIN = 15                                         # a window with a larger radar gap is "incomplete" -> excluded
WINDOWS_MIN = (30, 45, 60)                                    # growth windows evaluated for labelling

# ----------------------------------------------------------------------------- label definitions
# TRUE CI = cell reaches `true_dbz` within `window` minutes of first echo.
# The primary definition is used for the headline results; ALL others are used for sensitivity.
PRIMARY_LABEL = os.environ.get("CI_PRIMARY_LABEL", "t35_w45")   # "domain_true" for the whole-domain dataset (12_domain_dataset.py)
TRUE_DBZ_GRID = (30, 35, 40)
WINDOW_GRID = WINDOWS_MIN
LABEL_DEFS = {f"t{d}_w{w}": (d, w) for d in TRUE_DBZ_GRID for w in WINDOW_GRID}
# IMERG-confirmed label: surface rain >= IMERG_RAIN mm/h within +/-IMERG_BOX_DEG of the event
# during the 60 min after first echo. Independent of the radar -> cross-check on the radar rule.
IMERG_RAIN_MMH, IMERG_BOX_DEG = 2.0, 0.15
LABEL_IMERG = "imerg_confirmed"

# ----------------------------------------------------------------------------- predictors
LEADS = [180, 120, 90, 60, 30]       # minutes BEFORE first echo; every predictor is timestamped <= t_event - lead
SEVIRI_WIN_PX = 5                    # half-width of SEVIRI window (pixels, ~3 km each)
RADAR_WIN_KM = 15
IMERG_ACCUM_H = 3                    # hours of precipitation history

# ----------------------------------------------------------------------------- models / CV
# Atmospheric sub-groups (see variables.py) removed in the reduced model M6.
M6_DROP_ATM_GROUPS = ["dynamics", "pbl"]       # PROVISIONAL - replaced by the data-driven ablations in 07_models.py
LEARNERS = ["logit", "hgb", "rf"]
PRIMARY_LEARNER = "hgb"
N_CV_REPEATS = int(os.environ.get("CI_REPEATS", 5))
N_CV_FOLDS = 5                                  # folds are blocks of DAYS (never split a day)
RANDOM_SEED = 42

# ----------------------------------------------------------------------------- whole-domain (object-free) dataset
DOMAIN_BOX_KM = 12            # box size (multiple of GRID_RES_KM); every box x time is a sample, no storm tracking needed
DOMAIN_STEP_MIN = 30          # forecast-target windows [T, T+STEP): predict "true CI starts in this box in this window"
DOMAIN_NEG_KEEP = 0.02        # keep this fraction of negatives (all positives kept); sampling weights restore the true base rate

# ----------------------------------------------------------------------------- robustness analysis
N_BOOT = int(os.environ.get("CI_NBOOT", 1000))  # day-cluster bootstrap resamples
CI_LEVEL = 0.95
# Smallest score differences regarded as operationally meaningful. PLACEHOLDERS - see THRESHOLDS.md for how to set them
# (e.g. from the CV-repeat noise in cv_repeat_sd.csv and from the economic-value analysis).
SMD = {"AUC": 0.02, "BSS": 0.02, "POD_at_FAR": 0.03}

# "Useful" criteria. Each tier has a different justification (THRESHOLDS.md). The lower CI bound must clear the level.
#  tier 1  skill vs climatology      : BSS > 0                      (convention; ECMWF skill-horizon idea; SII-NowNet)
#  tier 2  economic value            : mean relative value V over cost/loss 0.05-0.5 >= level  (Richardson 2000, Murphy 1977)
#  tier 3  SENSITIVITY GRID ONLY     : AUC / BSS / POD-FAR levels. NOT taken from ECMWF or another centre: they span the
#                                      plausible range so the conclusion can be shown to be insensitive (or not) to them.
USEFUL_BSS = (0.00, 0.05, 0.10, 0.15, 0.20)
USEFUL_AUC = (0.60, 0.65, 0.70, 0.75, 0.80)
USEFUL_VALUE = (0.02, 0.05, 0.10)
USEFUL_POD_FAR = ((0.6, 0.5), (0.7, 0.5), (0.6, 0.4), (0.7, 0.4), (0.8, 0.5), (0.5, 0.7), (0.7, 0.6), (0.8, 0.7))  # (min POD, max FAR)
