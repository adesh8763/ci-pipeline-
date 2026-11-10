# TASK / DEPENDENCY CHECKLIST (audit 2026-10-10)

`[ ]` = not verified done. Nothing is ticked: no project artefacts were found. Arrows show what each task blocks.

## Gate: inputs
- [ ] Proposal available to the assistant  -> blocks everything
- [ ] Repository (README, configs, scripts, notebooks, data, logs, figures, phase notes) available  -> blocks status classification
- [ ] Region, study period, products, CI definitions recorded from the proposal  -> blocks P2 to P5
- [ ] `init.py` (or equivalent) located, read, and its run-state determined  -> blocks any "run it" recommendation

## Environment
- [x] Python 3.13.16 present (measured)
- [x] numpy, pandas, scipy, scikit-learn, matplotlib, requests, pyyaml present (measured)
- [ ] Geospatial / NetCDF stack decided from chosen products (xarray, netCDF4, etc. currently missing)  -> blocks P2/P4
- [ ] Access to the proposal's actual data sources confirmed (GOES-16 S3 host was policy-denied; others unverified)  -> blocks P2
- [ ] Storage budget estimated against ~31 GB free  -> blocks P2

## Pipeline
- [ ] P2 data acquisition  -> blocks P3, P4
- [ ] P3 true-CI / false-CI events  -> blocks P4
- [ ] P4 predictors at 180/120/90/60/30 min  -> blocks P5
- [ ] P5 dataset assembly, QC, leakage-safe split  -> blocks P6, P7
- [ ] P6 MI and CMI  -> blocks M6 group selection
- [ ] P7 M1 satellite, M2 radar, M3 sat+atm, M4 sat+radar, M5 sat+radar+atm  -> blocks P8
- [ ] P7 M6 full model minus selected atmospheric groups (needs P6)  -> blocks P8
- [ ] P8 detection skill, calibration, useful warning lead time  -> blocks P9, P10
- [ ] P9 robustness (where data permit)  -> blocks P10
- [ ] P10 figures, tables, write-up
