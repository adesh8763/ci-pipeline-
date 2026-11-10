# Data coverage and missing-variable report

Date: 2026-10-10. Study configuration is **provisional**: region (10-15N, 15W-5E), period (JJAS 2022, short core window 2022-08-01..14) and the three product choices come from the user's message of 2026-10-10, not from the original proposal, which is not in this workspace. See `config/study.yaml` and `manifest/data_manifest.csv`.

## 1. Bottom line

- **Files acquired: 0.** Every candidate data host is refused by this sandbox's egress policy (HTTP 403 on CONNECT, recorded in `logs/access_checks.jsonl` and the proxy status log). Nothing was retried or routed around.
- **Documentation was checked, data were not.** Product facts below come from public documentation pages. No file has been opened, so no coverage, completeness or event-count claim can be made yet.
- **Credentials are also needed** for all three products (CDS account, NASA Earthdata login, EUMETSAT account), and none are present.
- **No radar source** has been identified. Precipitation verification can only be IMERG-based unless the user supplies radar.

## 2. Reachability (header-only probes, 2026-10-10)

| Host(s) | Result |
|---|---|
| cds.climate.copernicus.eu | Denied by policy (403) |
| cmr.earthdata.nasa.gov, urs.earthdata.nasa.gov, gpm1.gesdisc.eosdis.nasa.gov | Denied by policy (403) |
| api.eumetsat.int, data.eumetsat.int, navigator.eumetsat.int | Denied by policy (403) |
| storage.googleapis.com (ARCO-ERA5 mirror), era5-pds.s3.amazonaws.com, rda.ucar.edu | Denied by policy (403) |
| Public documentation pages (web fetch tool) | Readable; this is how product facts below were obtained |

## 3. Product facts: verified vs not

| Item | ERA5 | IMERG Final HH | SEVIRI L1.5 |
|---|---|---|---|
| Identifier | reanalysis-era5-pressure-levels / -single-levels (DOI 10.24381/cds.bd0915c6 for pressure levels) | GPM_3IMERGHH, DOI 10.5067/GPM/IMERG/3B-HH/07 | EO:EUM:DAT:MSG:HRSEVIRI |
| Version | ERA5; ERA5T (preliminary) has about 5-day latency and may differ from final 2-3 months later. 2022 is older than that window. | V07; the record says 07B is current. Exact version must be read from file metadata. | Not stated |
| Temporal resolution | Hourly (verified) | Half-hourly (verified) | 15 min nominal; the fetched catalogue text is ambiguous, so treat as unconfirmed |
| Spatial resolution | 0.25 deg (verified) | 0.1 deg (verified) | Not confirmed from fetched pages |
| Coverage | 1940-01-01 to 2026-10-03 per catalogue entry | June 2000 to present; Final run lags by roughly 2.5-4 months (sources differ) | Archive start for this collection not confirmed |
| Format | GRIB (verified); NetCDF not confirmed | Not confirmed on fetched pages | HRIT per catalogue record; NetCDF only via Data Tailor (unvalidated) |
| Access | Account, licence acceptance, API key | NASA Earthdata login | EUMETSAT account and API key/secret |
| Volume estimate for the prototype | about 1.3 GB (assumption-based) | about 4 GB whole files for the 14-day core window; about 35 GB for all of JJAS (per-file size unverified) | about 2 GB for the core window if region/channel-subset; hundreds of GB if full disk (unverified) |

Volume figures use unverified per-file size assumptions listed in `config/study.yaml` (`limits.assumptions`) and in `docs/volume_estimate.json`. Replace them with measured sizes after the first real download. Free disk is about 31 GB, so whole IMERG granules for all of JJAS would not fit comfortably, and full-disk SEVIRI is not feasible. This is why the plan uses server-side subsetting.

## 4. Variable availability (nothing is claimed beyond what was seen)

| Intended predictor | Planned source variable | Status |
|---|---|---|
| Temperature | ERA5 `temperature` (pressure levels), `2m_temperature` | Pressure-level name confirmed in an ECMWF doc page for a related 6-hourly, 13-level product; **hourly 37-level product not confirmed**. 2 m field **not confirmed**. |
| Moisture | ERA5 `specific_humidity`, `total_column_water_vapour`, `2m_dewpoint_temperature` | Specific humidity name confirmed as above; the other two **not confirmed**. |
| Winds, shear | ERA5 `u_component_of_wind`, `v_component_of_wind` on levels | Names confirmed as above. Shear is a derived quantity. |
| Vertical motion | ERA5 `vertical_velocity` (Pa s-1) | Name and unit confirmed as above. |
| Convergence | Derived from ERA5 u, v | Divergence and vorticity fields **not confirmed**; derive from winds and document the grid-scale limitation. |
| CAPE, CIN | ERA5 `convective_available_potential_energy`, `convective_inhibition` (single levels) | **Not confirmed** in any fetched documentation. Must be checked on the first authenticated request. |
| Satellite cloud evolution | SEVIRI IR/WV channels | Product has 12 spectral channels per catalogue record. Channel names, units and calibration **not verified**. |
| Radar features | none | **No source identified.** |
| Precipitation | IMERG `precipitation` | Variable described in GPM documentation; units documented as mm/hr; confirm from file attributes. |

## 5. Event construction (true CI / false CI): what can and cannot be said now

- **Observations sufficiency: unknown.** No satellite or precipitation file has been opened, so scan gaps, missing half-hours and usable-day counts are not known. A catalogue listing is not evidence of completeness.
- **Published event datasets.** The PyFLEXTRKR Global MCS Tracking Dataset (Feng et al., Zenodo 10.5281/zenodo.10023498, CC BY 4.0) is built from IMERG precipitation and merged IR brightness temperature, covers 60S-60N, and **ends in December 2020**. It therefore cannot supply labels for the 2022 prototype. It tracks MCSs rather than true-CI/false-CI cases, and its fields for initiation were not confirmed. It could at most inform 2018-2020 expansion or cross-checks. Other items that appeared in searches (a convection-permitting Sahel initiation study and a West African convection paper) were **not read** and are not used.
- **Labelling rules to carry forward** (to be enforced in event construction, not yet implemented):
  - Missing or poorly observed periods become "unknown/excluded", never false CI.
  - Labels from IMERG are precipitation-based verification, not radar-confirmed convection, and must be named as such.
  - Predictors for lead L use only data with valid time <= t0 - L.
  - ERA5 is hourly: use the latest hour <= t0 - L. For L = 90 and 30 min the ERA5 field can be up to 59 min old at forecast time.
  - ERA5 is a reanalysis. Its assimilation window can include observations after the valid time, which is a possible leakage source for a real-time-warning claim. This should be reviewed against the proposal.
  - IMERG half-hour window start/end convention and SEVIRI per-scan time must be read from file metadata before alignment.

## 6. What is ready for event construction, and what is blocked

**Ready:** configuration (`config/study.yaml`), manifest (`manifest/data_manifest.csv`), volume estimator, access probe, three fetch scripts in dry-run, checksum and readability checker (tested on synthetic fixtures only, which are not data and are outside the manifest).

**Blocked (no data):** event construction, predictor extraction, coverage statistics, any variable-availability confirmation from files.

**Fetch scripts have not run against live services.** Their dry-run paths work. The live paths, including the SEVIRI Data Tailor chain fields and the CDS variable names, are unvalidated and will probably need small adjustments on first use.

## 7. Smallest scientifically defensible path forward

1. **Run the acquisition where the sources are reachable and credentialed** (your machine or another environment), using `scripts/fetch_*.py --execute`, starting with ERA5 (about 1.3 GB), then IMERG for the 14-day core window, then SEVIRI with `--limit 4` as a smoke test. Then upload `manifest/` plus small samples, or the files themselves if they fit.
2. **Or upload region-subset files directly.** The smallest useful set is ERA5 pressure-level and single-level GRIB/NetCDF for the study box and core window, IMERG half-hourly for the same box, and SEVIRI IR channels for the same box.
3. **Or ask for the sandbox allowlist to include** the hosts in section 2.
4. **Decision needed on radar.** If no radar is available, the study should state that verification is precipitation-based (IMERG) and cannot be called radar-confirmed.
5. Do not substitute another region. Do not use ERA5 as a verification source for convection.
