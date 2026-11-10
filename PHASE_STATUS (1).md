# PHASE STATUS: True CI Conditional Information Framework

Last updated: 2026-10-10 (data-readiness phase). Legend: **NOT STARTED** = no artefact found; **UNVERIFIED** = cannot be assessed; **BLOCKED** = cannot proceed; nothing here is marked complete. The original audit version of this file is kept at `ci_project/docs/PHASE_STATUS_2026-10-10_audit_original.md`.

> No proposal or repository is in this workspace (re-checked 2026-10-10: still only the three audit files). The region (10-15N, 15W-5E), period (JJAS 2022; core window 2022-08-01..14) and products (SEVIRI, IMERG, ERA5) are **user-proposed and provisional**, recorded in `ci_project/config/study.yaml`. Statuses reflect evidence in this workspace, not your actual progress elsewhere.

## Phase table

| # | Phase | Status | Evidence | Blocked by |
|---|---|---|---|---|
| P0 | Source-of-truth capture (proposal, region, period, products, definitions) | **PARTIAL / PROVISIONAL**: region, period, products and lead times recorded from your message in `config/study.yaml`; proposal itself still absent; CI event definitions not set | `ci_project/config/study.yaml` | Proposal (for event definitions and to confirm the provisional settings) |
| P1 | Environment and data-access readiness | **PARTIAL**: venv `ci_project/.venv` with cdsapi, eumdac, earthaccess, xarray, netCDF4, h5py, cfgrib, eccodes installed and importable; **all 10 candidate data hosts denied by sandbox egress policy**; no credentials present | `logs/access_checks.jsonl`, `docs/DATA_COVERAGE_REPORT.md` section 2 | Egress allowlist or an environment with access; CDS, Earthdata and EUMETSAT credentials |
| P2 | Data acquisition (satellite, radar/precip, atmosphere) | **BLOCKED: 0 files acquired.** Manifest, volume estimates, dry-run fetch scripts, checksum/readability checker built; scripts not yet run against live services. No radar source identified. | `manifest/data_manifest.csv`, `scripts/` | P1 (access), radar decision |
| P3 | Event construction (true-CI, false-CI) | **NOT STARTED / UNVERIFIED** | No event table or labels found | P0, P2 |
| P4 | Predictor extraction at 180/120/90/60/30 min lead times | **NOT STARTED / UNVERIFIED** | None | P2, P3 |
| P5 | Dataset assembly, QC, train/validation/test split design | **NOT STARTED / UNVERIFIED** | None | P3, P4 |
| P6 | Information analysis: MI and CMI (atmosphere conditional on satellite+radar) | **NOT STARTED / UNVERIFIED** | None | P5 |
| P7 | Models M1 to M6 | **NOT STARTED / UNVERIFIED** | None | P5 (M6 also needs P6 for group selection) |
| P8 | Evaluation: detection skill, calibration, useful warning lead time | **NOT STARTED / UNVERIFIED** | None | P7 |
| P9 | Robustness checks (where data permit) | **NOT STARTED / UNVERIFIED** | None | P7, P8 |
| P10 | Reporting: figures, tables, write-up | **NOT STARTED / UNVERIFIED** | None | P6, P8, P9 |

## Model definitions to preserve (from brief; not yet implemented anywhere I can see)

- M1 satellite only
- M2 radar only
- M3 satellite + atmosphere
- M4 satellite + radar
- M5 satellite + radar + atmosphere
- M6 full model with selected atmospheric groups removed

Key comparisons: M4 vs M5 (unique atmospheric value beyond satellite+radar); M1 vs M3 and M2 vs M5 (atmosphere added to a single source); M5 vs M6 (which atmospheric groups carry the information).

## Dependency map

```
P0 proposal/definitions
 ├─> P1 environment + access checks
 │     └─> P2 data acquisition ──┐
 └───────────────────────────────┤
                                 ▼
                       P3 true/false CI events
                                 ▼
                 P4 predictors at 180/120/90/60/30 min
                                 ▼
                 P5 dataset assembly + QC + split design
                     ├─────────────────────┐
                     ▼                     ▼
              P6 MI / CMI            P7 models M1..M5
                     │                     │
                     └──> M6 group selection ──> P7 (M6)
                                           ▼
                           P8 detection / calibration / lead time
                                           ▼
                                   P9 robustness
                                           ▼
                                   P10 reporting
```

Critical path: P0 → P2 → P3 → P4 → P5 → P7 → P8 → P10. P6 (MI/CMI) is on the path only for M6's choice of removed groups.
Cross-cutting risks: event labels (P3) determine everything downstream; leakage controls (e.g. no predictor after lead time, spatial/temporal split in P5) must be fixed before P6/P7.

## Update 2026-10-10: data-readiness phase

**Done (verified in this workspace):**
- Inventory repeated: no proposal, repo, datasets, scripts or event lists exist; nothing to reuse.
- Provisional study configuration written (`config/study.yaml`), including lead-time alignment rules.
- Product documentation checked for ERA5, IMERG Final V07 half-hourly and SEVIRI L1.5; verified vs unverified facts are separated in the manifest and `docs/DATA_COVERAGE_REPORT.md`.
- Manifest, volume estimate (`docs/volume_estimate.json`), access probe, fetch scripts (dry-run tested), checksum and readability checker (tested on synthetic fixtures only; no real data).

**Not done / blocked:**
- No satellite, precipitation or atmospheric file has been downloaded, so no checksums exist and no coverage, completeness or event-count statement can be made.
- ERA5 CAPE/CIN, 2 m and divergence variable names are not confirmed; SEVIRI resolution, archive start and channel ids are not confirmed.
- Live code paths of the fetch scripts (CDS names, Data Tailor chain, Earthdata search) are unvalidated.
- True-CI/false-CI definitions are not set; the published PyFLEXTRKR MCS dataset ends in 2020 so it cannot label 2022.
- No radar source identified; IMERG-based labels would be precipitation-based, not radar-confirmed.

**Ready for event construction:** nothing. **Blocked:** everything downstream of P2. No MI/CMI or model results exist.

## Next action (revised)

Pick one: (a) run `ci_project/scripts/fetch_era5.py`, `fetch_imerg.py`, `fetch_seviri.py --execute` somewhere with access and credentials, then `verify_files.py` and `build_manifest.py`; (b) upload region-subset ERA5, IMERG and SEVIRI files for the core window; or (c) have the sandbox allowlist extended. Also confirm the provisional region/period, the SEVIRI core window, and the radar question. The earlier next-action text is retained below for reference.

## Earlier next action (from the audit)

The audit cannot proceed to a repository-specific recommendation until the proposal and repository are available here.

**Step 1.** Provide, in one of these ways:
- attach the proposal (PDF/DOCX/MD) and, if it exists, the repository (zip, or a GitHub `owner/repo` that this session can attach), or
- paste the proposal text into the chat and list the files in your repo (`ls -R` or `tree`) plus the contents of `README`, `init.py` and any phase notes.

**Step 2.** Then run this prompt:

```
Re-run the project audit. The proposal and repository are now attached. Read the proposal first, then inspect the repo (README, configs, init.py without executing it, scripts, notebooks, data, logs, figures, phase notes). Update PROJECT_AUDIT.md and PHASE_STATUS.md in place: replace the "unknown" entries with what the files establish (region, period, products, event definitions, modelling decisions), classify each task as complete / incomplete / failed / unverified with evidence, say whether init.py has been run and what it does, and give the exact next command. Do not execute the pipeline.
```
