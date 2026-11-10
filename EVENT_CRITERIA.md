# Event criteria, alignment rules and limitations (PROVISIONAL)

Machine-readable settings: `config/events.yaml`. Code: `scripts/ci_events.py`, `scripts/build_event_dataset.py`. Test: `tests/test_synthetic_pipeline.py`.

## Status

- **Authored by the assistant, not taken from the research proposal.** The proposal is not in this workspace. These definitions and every numeric threshold are placeholders to be replaced by the proposal's definitions and calibrated on real data. They are not claimed to come from a verified publication.
- **No real data exist yet** (0 files; `manifest/data_manifest.csv`), so nothing here has been run on observations and no real labels, counts or class balance exist.
- **No radar is used.** Precipitation confirmation is an IMERG satellite-derived estimate. No label is, or may be described as, radar-confirmed convection.

## Definitions

Unit of analysis: a **candidate initiation object**.

- **t0 (reference time):** first SEVIRI 15-min slot where a *new* connected cold-cloud object (IR10.8 BT < 245 K, at least 4 connected pixels) appears. "New" means no cold cloud (< 245 K) within 0.3 deg during the previous 45 min.
- **Outcome window:** (t0, t0 + 60 min], evaluated in a fixed 0.4 deg disc around the object centroid at t0.
  - (a) core reached: at least 4 pixels with BT < 235 K in the disc, in any slot of the window.
  - (b) precipitation estimate: any IMERG half-hour window overlapping the outcome window with a value of at least 2 mm/h in the disc.

| Label | Rule | Used for modelling |
|---|---|---|
| `true_ci` | (a) and (b) | yes |
| `false_ci` | not (a), and (b) is *completely observed* and below threshold | yes |
| `ambiguous` | (a) and (b) disagree | no |
| `unknown` | any outcome observation incomplete (SEVIRI slot missing, IMERG window missing or too few valid pixels) and no positive exceedance seen | no |
| `excluded_missing_history` | history needed to establish "new" is incomplete (or t0 is at the start of the record) | no |

**Missing or poorly observed cases are never `false_ci`.** A false label requires complete satellite and precipitation observations over the whole outcome window.

## Lead-time samples (180, 120, 90, 60, 30 min)

For each modelled event and lead L: `t_forecast = t0 - L`.

- Predictor code only receives arrays truncated at `t_forecast` (future values are absent, not masked). Verified by a test that scrambles all data after `t_forecast` and checks all predictors are unchanged, at all five leads.
- **SEVIRI:** needs slots `t_forecast ... t_forecast - 60 min` all valid and enough valid pixels in the footprint. Features: footprint BT mean/min/10th percentile, 30- and 60-min mean-BT trends, fraction below 270 K.
- **IMERG:** time is the *end* of the half-hour window, so only windows ended at or before `t_forecast` are used.
- **ERA5:** latest hourly field with valid time at or before `t_forecast`; `era5_age_min` (0-59) is recorded. For 90 and 30 min leads the field is generally 30 min old.
- Every row carries `valid_sat`, `valid_precip`, `valid_era5`, `valid_all`; features are NaN where invalid. Rows are kept so single-source model variants can use them.

## Known limitations (all unresolved until real data and the proposal are available)

1. **Definitions and thresholds are uncalibrated placeholders.** The balance between classes, and what "false CI" means scientifically, depend on them. Because the label combines a cold-core criterion with precipitation, `false_ci` is partly "weak or short-lived cold cloud", which may make the problem easier or different from the intended one.
2. **Pixel-count thresholds assume the canonical grid spacing** (the synthetic test used 0.1 deg). They must be re-tied to the real SEVIRI-derived grid.
3. **Precipitation is a 0.1 deg, 30-min satellite estimate.** Short-lived or small cells can be missed or smeared; this is why a cold core without precipitation is `ambiguous`, not `false_ci`. It remains a weaker verification than radar.
4. **Fixed footprint, no advection tracking.** Fast-moving Sahelian systems can leave the 0.4 deg disc within the window.
5. **New cells within 0.3 deg / 45 min of existing cold cloud are treated as part of that system** and are not candidates. This excludes some real initiation near existing storms (found by the synthetic test).
6. **`excluded_missing_history` counts are upper bounds.**
7. **Retrospective design:** the predictor footprint is centred on a location known only because the object appeared at t0. Any claim of real-time warning skill must say so.
8. **Time resolution:** t0 has 15-min resolution; leads must be multiples of 15 min. SEVIRI scan time within the slot is not used (to be checked from file metadata).
9. **ERA5 is a reanalysis;** its assimilation window may include observations after the valid time (possible leakage for a real-time claim).
10. **Model M2 ("radar only") cannot be built** without radar. A precipitation-estimate-only model would be a different, renamed model.
11. **Adapters from raw files to the canonical inputs** (SEVIRI projection to lat/lon, IMERG window-time convention, ERA5 GRIB to hourly NetCDF) are **not written**: the real file layouts are unknown and cannot be inspected.
12. Samples from the same system or day are not independent. Splits must be blocked by time and space (P5).

## What the synthetic test does and does not show

It shows the code assigns labels as specified on planted cases (true, false, missing satellite, missing precipitation, ambiguous, persistent cloud), never converts missing data to `false_ci`, aligns ERA5 and IMERG causally, and cannot leak future data into predictors. It shows nothing about real-data label quality, class balance or event counts. Example outputs are in `tests/example_output_SYNTHETIC/`.
