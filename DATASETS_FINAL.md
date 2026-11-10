# Final dataset selection (supersedes the provisional 2022 / 10-15N, 15W-5E setup)

Date: 2026-10-10. Chosen by the assistant at your request; confirm with your supervisor.

## Decision

| Role | Dataset | Time | Why |
|---|---|---|---|
| **Radar** | NAMMA NASA NPOL S-band polarimetric Doppler radar, Kawsara, Senegal (GHRC DAAC) | 2006-08-19 to 2006-09-30 | The only openly shared ground radar I could verify for West Africa with a continuous, documented period. Volume scan about every 15 min, matching SEVIRI. Reflectivity, velocity and polarimetric fields. |
| **Satellite** | MSG SEVIRI High Rate L1.5, 0 degree (EUMETSAT Data Store) | Same dates, 15-min slots (4,128) | Covers West Africa, 12 channels, archive since 2004. Same sampling as the radar. |
| **Atmosphere** | ERA5 hourly, pressure + single levels | Same dates plus the previous day | CAPE, CIN, moisture, winds, vertical velocity. |
| Optional | IMERG Final V07 half-hourly | Same dates | Cross-check of radar labels and robustness, no longer the label source. |

Region: the NPOL range, catalogue box N 17.10, S 12.21, E -14.65, W -19.54, plus 2 deg padding for ERA5, SEVIRI and IMERG. The old 10-15N, 15W-5E box and the 2022 period are dropped, because no radar exists for them.

Sources: [NPOL catalogue](https://earthdata.nasa.gov/data/catalog/ghrc-daac-namnpol-1), [NPOL dataset docs](https://ghrc.nsstc.nasa.gov/pub/doc/namma/namnpol/namnpol_dataset.html), [SEVIRI L1.5](https://data.eumetsat.int/product/EO:EUM:DAT:MSG:HRSEVIRI), [ERA5 pressure levels](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-pressure-levels), [ERA5 single levels](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels), [IMERG V07](https://disc.gsfc.nasa.gov/datasets/GPM_3IMERGHH_07/summary).

## What this fixes

- M2 (radar only), M4 and M5 can now be built as the proposal defines them.
- Labels come from radar, so they are no longer circular with IMERG-based predictors.

## NPOL facts (from the dataset docs)

- Volume scans: 150 km range, 19 tilts. Surveillance scans: 270 km. About 7,200 scans, 29 GB in total.
- Files: gzipped UF volumes (`NAMMA_NPOL_QC_060831_0900.uf.gz`, daily folders), plus gridded reflectivity at 2, 4, 6, 8, 10 and 12 km and rain rate at 2 km as gzipped netCDF (2 km grid).
- Grid flags: -88 means out of range, -99 means in range with no echo. Treat both as non-events, but only -99 as "observed no echo".
- Fields: reflectivity, Doppler velocity, spectral width, ZDR, KDP, PhiDP, RhoHV.
- Open use with citation. Cite the dataset (P.I. Paul A. Kucera) per EOSDIS guidance.

## Limits you must state in the study

1. **Short record:** about 43 days. MI/CMI and M1-M6 will have few events and wide uncertainty. Use blocked cross-validation by day, and consider adding AMMA 2006 data later.
2. **Region:** the coastal Senegal Sahel edge, not the interior Sahel. Results do not automatically generalise.
3. **Radar footprint:** events only inside the 150 km volume range (270 km for coarse checks). Predictors must use the same footprint.
4. **Retrospective ERA5:** reanalysis may include later observations, so frame results as information content, not real-time skill.
5. **Single season:** no seasonal or regional robustness test is possible.

## Not verified

- The NPOL **download route**. The docs page lists no URL. The script tries NASA's search for short name `namnpol` (guessed from the catalogue id) and tells you if nothing is found. The file listing at `https://ghrc.nsstc.nasa.gov/pub/namma/namnpol/` could not be opened from here; if it works in your browser, that is likely the manual route.rustup show 
Default host: x86_64-unknown-linux-gnu
rustup home:  /home/adesh/.rustup

installed toolchains
--------------------
stable-x86_64-unknown-linux-gnu (active, default)

active toolchain
----------------
name: stable-x86_64-unknown-linux-gnu
active because: it's the default toolchain
installed targets:
  x86_64-unknown-linux-gnu

adesh in ~
❯ python3 --version 
Python 3.13.5

adesh in ~
❯ cmake --version 
cmake version 3.31.6

CMake suite maintained and supported by Kitware (kitware.com/cmake).

adesh in ~
❯ cargo --version 
cargo 1.99.0 (5f94df478 2026-08-27)
- The exact **radar position** (read it from the file headers).
- SEVIRI **2006 availability online**. The archive starts in 2004, but whether 2006 is downloadable or must be ordered is unconfirmed. The script reports how many products it finds (expect about 4,128).
- Which Meteosat satellite served the 0 degree service in 2006. Read it from file metadata.
- The Data Tailor chain fields (`--tailor`) are unvalidated.

## Run order

```
python fetch_data.py --plan
python fetch_data.py --only radar
python fetch_data.py --only era5
python fetch_data.py --only seviri --limit 4
```

Then upload a sample day of radar (`060831`), the SEVIRI files and the ERA5 GRIB, and I will write the adapters and update the event definitions to use radar (the current `events.yaml` is IMERG-based).
