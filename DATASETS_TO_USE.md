# Datasets to use: True-CI Conditional Information Framework

Date: 2026-10-10. Region and period are the provisional ones from `study.yaml` (10-15N, 15W-5E; JJAS 2022; core window 2022-08-01..14). The proposal does not fix them, so confirm them with your supervisor.

## Reconciliation with the proposal

| Proposal requirement | Status |
|---|---|
| Satellite, radar/precipitation, atmospheric data, aligned | Sources identified below. No data files exist in this workspace. |
| True/false CI via satellite tracking, verified by "radar reflectivity and/or precipitation" | IMERG precipitation satisfies the "and/or". Label it precipitation-verified, not radar-verified. |
| Predictors: moisture, temperature, CAPE/CIN, convergence, vertical motion, shear | All obtainable from ERA5 (variable names below). |
| Models M1-M6 | M2 "Radar" cannot be built without radar. See "Radar decision". |
| Lead times 180/120/90/60/30 min | Set in `study.yaml`. ERA5 is hourly, so it is up to 59 min stale at forecast time. |

**Missing from this workspace:** the scripts described in the status files (`ci_events.py`, `build_event_dataset.py`, `fetch_*.py`, `verify_files.py`, tests). Only the documents, configs, schema and manifest were uploaded. I have not seen that code, so I cannot vouch that it works. The new `fetch_data.py` below replaces the three fetch scripts.

**Not possible from here:** I cannot download anything. This sandbox blocked every data host (per your earlier logs), and all three services need your credentials. So there is no "final dataset" I can hand you, only the verified sources and a script to pull them on a machine with access.

## 1. ERA5 (atmosphere) - use these two

| Item | Value |
|---|---|
| Pressure levels | https://cds.climate.copernicus.eu/datasets/reanalysis-era5-pressure-levels (DOI 10.24381/cds.bd0915c6) |
| Single levels | https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels (DOI 10.24381/cds.adbb2d47, taken from your `study.yaml`, not re-checked) |
| Confirmed | Hourly, 0.25 deg, 37 pressure levels, 1940 to present, about 5-day latency (catalogue page) |
| Confirmed variables | `cape`, `cin`, `blh`, `t2m`, `d2m`, `u10`, `v10` exist in the ERA5 single-level variable list |
| Needs a licence click | Create a CDS account, accept the ERA5 licence, put your key in `~/.cdsapirc` |

**Do not use** the "ERA5 hourly time-series data on pressure levels" entry. It is 6-hourly, 13 levels, single-point oriented.

Convergence and shear are not stored fields. Derive them from u, v (850/925 hPa divergence; 925-500 hPa and 925-700 hPa shear).

## 2. IMERG Final Run V07 half-hourly (precipitation verification)

| Item | Value |
|---|---|
| Landing page | https://disc.gsfc.nasa.gov/datasets/GPM_3IMERGHH_07/summary |
| DOI | 10.5067/GPM/IMERG/3B-HH/07 |
| Confirmed | 0.1 deg, half-hourly, mm/h, from June 2000; Final Run latency about 3.5 months; V07B described as current |
| Alternative mirror | NCAR GDEX https://gdex.ucar.edu/datasets/d731000/ (same V07 Final half-hourly product) |
| AWS Open Data | https://registry.opendata.aws/nasa-gpm3imerghh (`s3://gesdisc-cumulus-prod-protected/GPM_L3/GPM_3IMERGHH.07/`). The bucket name says "protected", so expect to need Earthdata credentials. Not tested. |
| Access | Free NASA Earthdata login (https://urs.earthdata.nasa.gov) |

**Check before relying on V07:** the catalogue also lists an "IMERG V08 Transition Schedule". Look at the GES DISC page for whether V08 has replaced V07 for 2022, and record the version in every output.

## 3. SEVIRI L1.5 (satellite cloud evolution)

| Item | Value |
|---|---|
| Product page | https://data.eumetsat.int/product/EO:EUM:DAT:MSG:HRSEVIRI |
| Collection id | `EO:EUM:DAT:MSG:HRSEVIRI` (MSG 0 degree, covers West Africa) |
| Confirmed | 12 channels; data since 2004; quarter-hourly images for data older than 3 hours; Native format readable with satpy `seviri_l1b_native`; free EUMETSAT Earth Observation Portal registration needed |
| Size warning | Full-disk Native files are large (your 250 MB/file figure is unverified). 14 days x 96 slots is about 1,344 files, which would overwhelm a 31 GB disk. Subset with the Data Tailor service (region + channel) or process and delete each file as you go. |

## 4. Radar decision (needs your answer)

I found no public gridded radar archive for the Sahel in 2022. The radar material I found is the 2006 AMMA Niamey MIT C-band radar (papers only; I did not find or verify a data link, and it does not overlap 2022). Options:

1. **Precipitation-only (recommended, proposal-compliant):** call the second source "IMERG precipitation estimate" and rename M2 and M4/M5 accordingly. State clearly that nothing is radar-confirmed.
2. **Change period** to one with radar (e.g. AMMA 2006 around Niamey). This changes SEVIRI/IMERG/ERA5 requests too, and the area shrinks to the radar footprint.
3. **Supply radar** from a national met service by agreement.

One methodological caution: if IMERG both defines the label and supplies M2 predictors, M2 and M4/M5 results partly reflect the label source. Keep the pre-t0 precipitation features strictly causal (already in your EVENT_CRITERIA rules) and say so in the paper.

## 5. How to pull the data

Run `fetch_data.py` on a machine with internet and credentials (steps are in its header). Start with `--only era5`, then `--only imerg`, then `--only seviri --limit 4` as a smoke test. Afterwards upload `data/` samples or the manifest here and I can write the raw-to-canonical adapters against the real files and continue with P3 onward.

## Updated phase status

P0 partial (provisional). P1 blocked on access. P2 blocked on access/credentials and the radar decision. P3-P10 not started on real data; nothing in this workspace has run on observations.
